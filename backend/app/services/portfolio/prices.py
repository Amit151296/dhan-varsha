"""Latest market prices for portfolio holdings.

Yahoo Finance's public chart endpoint (unofficial, no API key) is tried
first, keyed off the ticker embedded in the holding's resolved screener.in
URL (/company/PNB/consolidated/ -> PNB), which is the NSE symbol for
NSE-listed companies; BSE-only companies use a numeric scrip code.

Yahoo has no quote for every stock (illiquid/SME-listed/very recently listed
companies especially), so when it comes back empty the "Current Price"
figure shown on the company's own screener.in page is used as an
approximate fallback instead of leaving the holding unsynced - it's already
on a page this app fetches elsewhere with an authenticated session, and
being "approximate" (it can lag the live tick, and screener.in's own numbers
are rounded to whole rupees too) is an acceptable trade for coverage.

All prices/values this module produces are rounded to whole rupees, not
fractional paise - NSE/BSE prices aren't normally shown with decimals.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from lxml import html as lhtml

from app import config
from app.services.screener.fetcher import ScreenerSession

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SCREENER_BASE_URL = "https://www.screener.in"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT_SECONDS = 10
MAX_WORKERS = 8


def ticker_from_url(url: str | None) -> str | None:
    parts = [p for p in (url or "").split("/") if p]
    return parts[1] if len(parts) > 1 else None


def _symbols_to_try(ticker: str) -> list[str]:
    if ticker.isdigit():
        return [f"{ticker}.BO"]
    return [f"{ticker}.NS", f"{ticker}.BO"]


def fetch_price(ticker: str) -> float | None:
    """Exact last-traded price from Yahoo Finance, or None if it has no quote."""
    for symbol in _symbols_to_try(ticker):
        try:
            response = requests.get(
                CHART_URL.format(symbol=quote(symbol, safe="")),
                params={"range": "1d", "interval": "1d"},
                headers=HEADERS,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            price = response.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            if price:
                return float(price)
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            logger.info("No price from Yahoo for %s", symbol, exc_info=True)
    return None


def fetch_screener_price(resolved_url: str) -> float | None:
    """Approximate fallback: the "Current Price" figure on the company's own
    screener.in page, for stocks Yahoo Finance has no quote for.
    """
    if not config.SCREENER_SESSIONS:
        return None

    session = ScreenerSession(**config.SCREENER_SESSIONS[0])
    headers = {
        **HEADERS,
        "Cookie": f"csrftoken={session.csrf_token}; sessionid={session.session_id}",
    }
    url = resolved_url if resolved_url.startswith("http") else f"{SCREENER_BASE_URL}{resolved_url}"

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.info("Could not reach screener.in for approximate price at %s", resolved_url, exc_info=True)
        return None

    try:
        tree = lhtml.fromstring(response.text)
        for item in tree.xpath('//li[contains(@class, "flex-space-between")]'):
            name = item.xpath('.//span[@class="name"]')
            if not name or name[0].text_content().strip() != "Current Price":
                continue
            number = item.xpath('.//span[@class="number"]')
            if number:
                raw = re.sub(r"[^\d.]", "", number[0].text_content())
                return float(raw) if raw else None
    except (ValueError, IndexError):
        logger.info("Could not parse screener.in price for %s", resolved_url, exc_info=True)
    return None


def fetch_price_for_holding(ticker: str | None, resolved_url: str | None) -> tuple[float | None, bool]:
    """Returns (price, is_approximate). Tries Yahoo Finance first (exact);
    falls back to screener.in's own page (approximate) if that has nothing.
    """
    if ticker:
        price = fetch_price(ticker)
        if price is not None:
            return price, False

    if resolved_url:
        price = fetch_screener_price(resolved_url)
        if price is not None:
            return price, True

    return None, False


def fetch_prices_for_holdings(holdings: list) -> dict[int, tuple[float | None, bool]]:
    """Batch version of fetch_price_for_holding, keyed by holding id."""
    jobs = [(h.id, ticker_from_url(h.resolved_url), h.resolved_url) for h in holdings]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = pool.map(lambda job: fetch_price_for_holding(job[1], job[2]), jobs)
    return {job[0]: result for job, result in zip(jobs, results)}


def fetch_prices(tickers: list[str]) -> dict[str, float | None]:
    """Yahoo-only batch lookup, kept for callers that only have tickers on hand."""
    unique = list(dict.fromkeys(tickers))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return dict(zip(unique, pool.map(fetch_price, unique)))


def apply_price(holding, price: float, is_approximate: bool = False) -> None:
    """Sets LTP and recomputes current value / P&L from it, rounded to whole rupees."""
    holding.ltp = round(price)
    holding.price_is_approximate = is_approximate
    if holding.quantity:
        holding.current_value = round(holding.quantity * price)
        invested = holding.invested_value
        if invested is None and holding.avg_price is not None:
            invested = holding.quantity * holding.avg_price
        if invested is not None:
            holding.pnl = round(holding.current_value - invested)
