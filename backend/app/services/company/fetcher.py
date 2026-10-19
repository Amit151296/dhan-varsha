"""Fetches a single company's screener.in page and returns all of its tables.

Reuses the first configured session - a company page doesn't hit the free
account's column cap the way the sector compare page does, so there's no
need to merge multiple sessions here.
"""

from __future__ import annotations

import logging
from io import StringIO

import pandas as pd
import requests

from app import config
from app.exceptions import ScreenerFetchError, ScreenerSessionExpiredError
from app.services.screener.fetcher import ScreenerSession

logger = logging.getLogger(__name__)

BASE_URL = "https://www.screener.in"


def fetch_company_tables(company_url: str) -> list[pd.DataFrame]:
    if not config.SCREENER_SESSIONS:
        raise ScreenerFetchError(
            "No screener.in sessions configured. Set SCREENER_SESSION_1_CSRF and "
            "SCREENER_SESSION_1_SID in backend/.env."
        )
    session = ScreenerSession(**config.SCREENER_SESSIONS[0])
    headers = {"Cookie": f"csrftoken={session.csrf_token}; sessionid={session.session_id}"}

    url = company_url if company_url.startswith("http") else f"{BASE_URL}{company_url}"
    try:
        response = requests.get(
            url, headers=headers, timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Request to screener.in failed for company page '%s'", company_url)
        raise ScreenerFetchError(f"Could not reach screener.in: {exc}") from exc

    if "Please login again" in response.text or "/login/" in response.url:
        raise ScreenerSessionExpiredError(
            "screener.in session looks expired or invalid. Refresh its csrftoken/sessionid "
            "in backend/.env."
        )

    try:
        tables = pd.read_html(StringIO(response.text))
    except (ValueError, IndexError) as exc:
        raise ScreenerFetchError(f"screener.in returned no data tables for '{company_url}'") from exc

    logger.info("Fetched %d tables from screener.in for company page '%s'", len(tables), company_url)
    return tables
