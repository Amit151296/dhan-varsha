"""NSE index performance, shared by all users and cached until midnight India time.

The numbers come from the same JSON feed that powers dhan.co's "All NSE indices" page. One fetch a
day serves every user; if the feed is down, the last saved copy is shown instead (marked stale).
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import requests
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from app import models
from app.exceptions import ScreenerError

logger = logging.getLogger(__name__)

SOURCE_URL = "https://ow-scanx-analytics.dhan.co/customscan/fetchdt"
IST = timezone(timedelta(hours=5, minutes=30))
CACHE_KEY = "nse-indices-v3"  # bump when the saved row shape changes, so old copies are not reused
PAGE_SIZE = 25
MAX_PAGES = 10  # safety stop; the feed has about 5 pages
FIELDS = [
    "DispSym", "Sym", "Ltp", "Open", "Close", "Pchange", "PPerchange", "High1Yr", "Low1Yr",
    "PricePerchng1week", "PricePerchng1mon", "PricePerchng3mon", "PricePerchng6mon",
    "PricePerchng1year", "PricePerchng3year", "PricePerchng5year", "IndexBasedOnExch", "LastTradeTime", "Seosym",
]

# The indices worth tracking (broad market, sectors and a few themes).
REQUIRED_INDICES = [
    "Nifty 50", "NIFTY 100", "NIFTY 200", "NIFTY 500", "NIFTY Midcap 150", "NIFTY Smallcap 250",
    "NIFTY Smallcap 100", "Nifty Bank", "NIFTY Private Bank", "NIFTY PSU Bank", "Finnifty", "NIFTY Auto",
    "NIFTY FMCG", "Nifty IT", "NIFTY Media", "NIFTY Metal", "NIFTY Pharma", "NIFTY Realty",
    "Nifty Commodities", "NIFTY Consumption", "Nifty PSE", "NIFTY Energy", "NIFTY Infra", "NIFTY MNC",
    "Nifty CPSE", "NIFTY Services Sector", "Nifty Healthcare", "Nifty Consumer Durable",
    "Nifty Oil and Gas", "Nifty India Defence", "Nifty India Manufacturing",
]
_WANTED = {name.casefold() for name in REQUIRED_INDICES}


class IndexDataError(ScreenerError):
    """The index feed could not be read."""


def end_of_day_ist(now: datetime) -> datetime:
    """The coming 24:00 (midnight) in India time, as an aware datetime."""
    local = now.astimezone(IST)
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _post_page(page: int) -> dict:
    body = {
        "data": {
            "sort": "PricePerchng1year",
            "sorder": "desc",
            "count": PAGE_SIZE,
            "params": [{"field": "IndexBasedOnExch", "op": "", "val": "NSE"}, {"field": "Exch", "op": "", "val": "IDX"}],
            "fields": FIELDS,
            "pgno": page,
        }
    }
    try:
        response = requests.post(SOURCE_URL, json=body, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise IndexDataError(f"Could not fetch index data: {exc}") from exc


def _number(value) -> float | None:
    return round(float(value), 2) if isinstance(value, (int, float)) else None


def parse_rows(raw_rows: list[dict]) -> list[dict]:
    """Keep the tracked indices, with tidy numbers. Day change is a percentage."""
    rows = []
    for raw in raw_rows:
        name = str(raw.get("DispSym") or "").strip()
        key = name.casefold()
        if key not in _WANTED:
            continue
        rows.append(
            {
                "name": name,
                "slug": raw.get("Seosym"),
                "ltp": _number(raw.get("Ltp")),
                "day_change_pct": _number(raw.get("PPerchange")),
                "prev_close": _number(raw.get("Close")),
                "high_52w": _number(raw.get("High1Yr")),
                "low_52w": _number(raw.get("Low1Yr")),
                "return_1w": _number(raw.get("PricePerchng1week")),
                "return_1m": _number(raw.get("PricePerchng1mon")),
                "return_3m": _number(raw.get("PricePerchng3mon")),
                "return_6m": _number(raw.get("PricePerchng6mon")),
                "return_1y": _number(raw.get("PricePerchng1year")),
                "return_3y": _number(raw.get("PricePerchng3year")),
                "return_5y": _number(raw.get("PricePerchng5year")),
            }
        )
    return rows


def fetch_indices() -> list[dict]:
    raw: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = _post_page(page)
        chunk = payload.get("data") or []
        raw.extend(chunk)
        if page >= int(payload.get("tot_pg") or 1) or not chunk:
            break
    rows = parse_rows(raw)
    if not rows:
        raise IndexDataError("The index feed returned no data for the tracked indices.")
    return sorted(rows, key=lambda r: r["name"].casefold())


def with_derived(rows: list[dict]) -> list[dict]:
    """Adds "up_from_low_pct": how far the last price is above the 52-week low, worked out from those two columns."""
    out = []
    for row in rows:
        ltp, low = row.get("ltp"), row.get("low_52w")
        up = round((ltp - low) / low * 100, 2) if ltp is not None and low else None
        out.append({**row, "up_from_low_pct": up})
    return out


def _cached(db: Session, key: str, loader, now: datetime | None, force_refresh: bool = False) -> dict:
    """Shared day cache: `loader()` runs only when nothing is saved for `key` or the saved copy is past midnight IST.

    If the loader fails and an old copy exists, that copy is returned marked stale.
    """
    now = now or datetime.now(timezone.utc)
    saved = db.query(models.IndexPerformanceCache).filter(models.IndexPerformanceCache.key == key).first()
    if saved is not None and not force_refresh and now < _aware(saved.expires_at):
        return {"rows": saved.rows, "fetched_at": saved.fetched_at, "expires_at": saved.expires_at, "cached": True, "stale": False}
    try:
        rows = loader()
    except IndexDataError:
        if saved is None:
            raise
        logger.warning("Source unavailable for %s; serving the last saved copy", key, exc_info=True)
        return {"rows": saved.rows, "fetched_at": saved.fetched_at, "expires_at": saved.expires_at, "cached": True, "stale": True}
    expires = end_of_day_ist(now).astimezone(timezone.utc)
    if saved is None:
        db.add(models.IndexPerformanceCache(key=key, rows=rows, fetched_at=now, expires_at=expires))
    else:
        saved.rows, saved.fetched_at, saved.expires_at = rows, now, expires
    db.commit()
    return {"rows": rows, "fetched_at": now, "expires_at": expires, "cached": False, "stale": False}


def get_index_performance(db: Session, now: datetime | None = None, force_refresh: bool = False) -> dict:
    """{"rows", "fetched_at", "expires_at", "cached", "stale"}; refetches only after the day rolls over."""
    result = _cached(db, CACHE_KEY, fetch_indices, now, force_refresh)
    return {**result, "rows": with_derived(result["rows"])}


class IndexNotFound(Exception):
    """The requested index is not one of the tracked ones."""


MEMBERS_URL = "https://dhan.co/indices/{slug}-companies/"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def fetch_members(slug: str) -> list[dict]:
    """The companies in one index, from the index's own dhan.co page (it embeds the list as JSON)."""
    try:
        response = requests.get(MEMBERS_URL.format(slug=slug), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        match = _NEXT_DATA.search(response.text)
        raw = json.loads(match.group(1))["props"]["pageProps"].get("sniData") if match else None
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise IndexDataError(f"Could not fetch the companies in this index: {exc}") from exc
    members = []
    for item in raw or []:
        name = str(item.get("DispSym") or "").strip()
        if not name:
            continue
        ltp, low = _number(item.get("Ltp")), _number(item.get("Low1Yr"))
        members.append(
            {
                "name": name,
                "symbol": item.get("Sym"),
                "sector": item.get("Sector"),
                "ltp": ltp,
                "day_change_pct": _number(item.get("PPerchange")),
                "market_cap_cr": _number(item.get("Mcap")),
                "pe": _number(item.get("Pe")),
                "low_52w": low,
                "high_52w": _number(item.get("High1Yr")),
                "up_from_low_pct": round((ltp - low) / low * 100, 2) if ltp is not None and low else None,
            }
        )
    if not members:
        raise IndexDataError("dhan.co returned no companies for this index.")
    return sorted(members, key=lambda m: m["market_cap_cr"] or 0, reverse=True)


def get_index_members(db: Session, slug: str, now: datetime | None = None) -> dict:
    """Companies in a tracked index. Fetched only when someone opens it, then saved for everyone until midnight IST."""
    rows = get_index_performance(db, now)["rows"]
    names = {row.get("slug"): row["name"] for row in rows}
    if slug not in names:  # only slugs from our own list ever reach the outbound request
        raise IndexNotFound(slug)
    result = _cached(db, f"members:{slug}", lambda: fetch_members(slug), now)
    return {**result, "index_name": names[slug], "slug": slug}


_EXPORT_COLUMNS = [
    ("Index", "name"), ("Last price", "ltp"), ("Today %", "day_change_pct"), ("1 week %", "return_1w"),
    ("1 month %", "return_1m"), ("3 months %", "return_3m"), ("6 months %", "return_6m"), ("1 year %", "return_1y"),
    ("3 years %", "return_3y"), ("5 years %", "return_5y"), ("52W low", "low_52w"), ("52W high", "high_52w"), ("Up from 52W low %", "up_from_low_pct"),
]


def build_workbook(rows: list[dict]) -> bytes:
    """Excel file with real numbers and filter arrows on the header row."""
    wb = Workbook()
    ws = wb.active
    ws.title = "NSE indices"
    ws.append([label for label, _ in _EXPORT_COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(key) for _, key in _EXPORT_COLUMNS])
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 28
    for letter in "BCDEFGHIJKLM":
        ws.column_dimensions[letter].width = 13
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
