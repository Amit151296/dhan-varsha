"""Proxies screener.in's own company search so the frontend gets autocomplete
over every listed Indian company without us maintaining a static directory.
"""

from __future__ import annotations

import logging

import requests

from app import config
from app.exceptions import ScreenerFetchError
from app.services.screener.fetcher import ScreenerSession

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.screener.in/api/company/search/"
MIN_QUERY_LENGTH = 2


def search_companies(query: str) -> list[dict]:
    query = query.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    if not config.SCREENER_SESSIONS:
        raise ScreenerFetchError(
            "No screener.in sessions configured. Set SCREENER_SESSION_1_CSRF and "
            "SCREENER_SESSION_1_SID in backend/.env."
        )
    session = ScreenerSession(**config.SCREENER_SESSIONS[0])
    headers = {"Cookie": f"csrftoken={session.csrf_token}; sessionid={session.session_id}"}

    try:
        response = requests.get(
            SEARCH_URL,
            params={"q": query},
            headers=headers,
            timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        logger.exception("Company search request to screener.in failed for '%s'", query)
        raise ScreenerFetchError(f"Could not reach screener.in: {exc}") from exc
    except ValueError as exc:
        raise ScreenerFetchError("screener.in returned an unexpected search response") from exc

    return [{"name": item["name"], "url": item["url"]} for item in results if "name" in item and "url" in item]


def _ticker_from_url(url: str) -> str:
    # "/company/TCS/consolidated/" -> "TCS"
    parts = [p for p in url.split("/") if p]
    return parts[1] if len(parts) > 1 else ""


def resolve_company_by_name(name: str) -> dict | None:
    """Best-effort lookup used when a sector table only gives us a plain name/ticker.

    Sector compare tables show the short ticker (e.g. "TCS"), not the full
    legal name search returns (e.g. "Tata Consultancy Services Ltd"), so the
    ticker embedded in each result's URL is the more reliable match target.
    """
    results = search_companies(name)
    if not results:
        return None

    normalized = name.strip().casefold()
    for result in results:
        if _ticker_from_url(result["url"]).casefold() == normalized:
            return result
    for result in results:
        if result["name"].strip().casefold() == normalized:
            return result
    return results[0]
