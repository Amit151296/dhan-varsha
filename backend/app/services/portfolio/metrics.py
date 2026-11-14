"""Fetches screener.in metrics for just the companies a user holds.

screener.in has no "compare these tickers" page, so each holding's industry
listing (the same tables the Dashboard's sector tool reads) is fetched and
only the rows for held companies are kept.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, models
from app.exceptions import ScreenerFetchError
from app.services.company.analyzer import canonical_company_key
from app.services.portfolio.prices import ticker_from_url
from app.services.screener.fetcher import get_fetcher, get_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://www.screener.in"
PAGE_SIZE = 50
MAX_PAGES = 10
REQUEST_SPACING_SECONDS = 0.5

_INDUSTRY_LINK = re.compile(r'<a[^>]*href="(/market/[^"]*)"[^>]*title="Industry"')


def tickers_for_holdings(holdings: list) -> dict[str, str]:
    """Maps ticker -> canonical company URL for every holding that has a matched company."""
    found = {}
    for h in holdings:
        ticker = ticker_from_url(h.resolved_url) if h.resolved_url else None
        if ticker:
            found.setdefault(ticker, canonical_company_key(h.resolved_url))
    return found


def _industry_url(company_url: str) -> str | None:
    session = config.SCREENER_SESSIONS[0]
    headers = {"Cookie": f"csrftoken={session['csrf_token']}; sessionid={session['session_id']}"}
    try:
        response = get_with_retry(f"{BASE_URL}{company_url}", headers, config.SCREENER_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Could not look up the industry for %s", company_url, exc_info=True)
        return None
    match = _INDUSTRY_LINK.search(response.text)
    return f"{BASE_URL}{match.group(1)}" if match else None


def _industry_urls(db: Session, company_urls: list[str]) -> list[str | None]:
    """Industry page per company: from the database when known, otherwise looked up once and saved."""
    cached = {
        row.company_url: row.industry_url
        for row in db.query(models.CompanyIndustryLink).filter(models.CompanyIndustryLink.company_url.in_(company_urls))
    }
    for company_url in company_urls:
        if company_url in cached:
            continue
        url = _industry_url(company_url)
        time.sleep(REQUEST_SPACING_SECONDS)
        if url:
            cached[company_url] = url
            db.add(models.CompanyIndustryLink(company_url=company_url, industry_url=url))
            db.commit()
    return [cached.get(company_url) for company_url in company_urls]


def _collapse_duplicate_columns(table: pd.DataFrame) -> pd.DataFrame:
    """Merge columns that share a header (both sessions send Company, CMP, ...), keeping the first value present."""
    return table.T.groupby(level=0, sort=False).first().T


def _save_page(db: Session, table: pd.DataFrame, industry_url: str, now: datetime) -> set[str]:
    """Stores every company row on a listing page as a shared snapshot; returns the tickers saved."""
    row_tickers = table.attrs.get("tickers", [])
    table = _collapse_duplicate_columns(table.reset_index(drop=True))
    records = json.loads(table.to_json(orient="records"))

    page_tickers = {t for t in row_tickers if t}
    existing = {
        s.ticker: s
        for s in db.query(models.CompanyMetricSnapshot).filter(models.CompanyMetricSnapshot.ticker.in_(page_tickers))
    }
    saved = set()
    for ticker, record in zip(row_tickers, records):
        if not ticker:
            continue
        name = record.get("Company") or ticker
        snapshot = existing.get(ticker)
        if snapshot is None:
            db.add(
                models.CompanyMetricSnapshot(
                    ticker=ticker, name=name, industry_url=industry_url, raw=record, fetched_at=now
                )
            )
        else:
            snapshot.name, snapshot.industry_url, snapshot.raw, snapshot.fetched_at = name, industry_url, record, now
        saved.add(ticker)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # another request saved the same company a moment ago
        return set()
    return saved


def _refresh_snapshots(db: Session, stale: dict[str, str]) -> None:
    """Fetch the industry listings of the stale companies and save every company on the pages read."""
    industry_urls = _industry_urls(db, list(stale.values()))

    by_industry: dict[str, set[str]] = {}
    for ticker, url in zip(stale, industry_urls):
        if url:
            by_industry.setdefault(url, set()).add(ticker)
        else:
            logger.warning("No industry found for %s - leaving it out of the metrics table", ticker)
    if not by_industry:
        raise ScreenerFetchError(
            "Could not look up the industry of any of your companies on screener.in. "
            "Its session may have expired - check the screener.in cookies in backend/.env."
        )

    fetcher = get_fetcher()
    now = datetime.now(timezone.utc)
    for industry_url, wanted in by_industry.items():
        remaining = set(wanted)
        for page in range(1, MAX_PAGES + 1):
            time.sleep(REQUEST_SPACING_SECONDS)
            try:
                table = fetcher.fetch_sector(f"{industry_url}?limit={PAGE_SIZE}&page={page}")
            except ScreenerFetchError:
                if page == 1:
                    raise
                break  # ran past the last page
            _save_page(db, table, industry_url, now)
            remaining -= set(table.attrs.get("tickers", []))
            if not remaining or len(table) < PAGE_SIZE:
                break
        if remaining:
            logger.warning("Not found in %s: %s", industry_url, sorted(remaining))


def fetch_portfolio_metrics(
    db: Session, tickers: dict[str, str], force_refresh: bool = False, cache_only: bool = False
) -> pd.DataFrame:
    """Raw metrics rows for the given companies, from the shared snapshot table.

    Only companies with no snapshot, or one older than the cache window, are fetched from
    screener.in - and that fetch saves their whole industry, so other users benefit too.
    With `cache_only` nothing is fetched from screener.in: whatever is saved (any age) is returned,
    and the table may be empty or partial.
    The result's `attrs` say how old the oldest row is ("as_of") and whether screener.in
    had to be called at all ("fetched").
    """
    if not tickers:
        raise ScreenerFetchError("No holdings with a matched company to fetch metrics for.")
    if not config.SCREENER_SESSIONS and not cache_only:
        raise ScreenerFetchError(
            "No screener.in sessions configured. Set SCREENER_SESSION_1_CSRF and SCREENER_SESSION_1_SID in backend/.env."
        )

    now = datetime.now(timezone.utc)
    # A forced refresh still leaves alone anything saved very recently.
    max_age = timedelta(
        minutes=config.PORTFOLIO_MIN_REFRESH_MINUTES if force_refresh else config.PORTFOLIO_METRICS_CACHE_TTL_HOURS * 60
    )
    cutoff = now - max_age

    def load() -> dict[str, models.CompanyMetricSnapshot]:
        rows = db.query(models.CompanyMetricSnapshot).filter(models.CompanyMetricSnapshot.ticker.in_(list(tickers)))
        return {row.ticker: row for row in rows}

    snapshots = load()
    stale = {
        ticker: url
        for ticker, url in tickers.items()
        if ticker not in snapshots or snapshots[ticker].fetched_at < cutoff
    }
    if stale and not cache_only:
        _refresh_snapshots(db, stale)
        snapshots = load()

    found = [snapshots[ticker] for ticker in tickers if ticker in snapshots]
    if not found:
        if cache_only:
            return pd.DataFrame()
        raise ScreenerFetchError("None of your companies were found in screener.in's industry listings.")
    table = pd.DataFrame([snap.raw for snap in found])
    table.attrs["as_of"] = min(snap.fetched_at for snap in found)
    table.attrs["fetched"] = bool(stale) and not cache_only
    return table
