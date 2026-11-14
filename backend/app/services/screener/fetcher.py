"""Retrieves raw sector tables from screener.in.

BaseScreenerFetcher is a strategy interface on purpose: today the only
implementation logs in via a browser session's cookies because that's what
the budget allows. When an official screener.in API is available later, add
a new subclass here and point SCREENER_DATA_SOURCE at its name - the
analyzer, scoring and persistence layers never need to change.
"""

from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass
from io import StringIO

import pandas as pd
import requests

from app import config
from app.exceptions import ScreenerFetchError, ScreenerSessionExpiredError
from app.services.screener import auth

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenerSession:
    label: str
    csrf_token: str
    session_id: str
    username: str | None = None
    password: str | None = None


class BaseScreenerFetcher(abc.ABC):
    @abc.abstractmethod
    def fetch_sector(self, sector_url: str) -> pd.DataFrame:
        """Return the raw compare/export table for a sector as a DataFrame."""


class SessionCookieFetcher(BaseScreenerFetcher):
    """Fetches sector data by replaying logged-in session cookies.

    screener.in's free tier caps how many columns a single account can see in
    the compare/export table, so results from every configured session are
    fetched and merged column-wise.
    """

    def __init__(self, sessions: list[ScreenerSession] | None = None):
        self._sessions = sessions or [
            ScreenerSession(**raw_session) for raw_session in config.SCREENER_SESSIONS
        ]
        if not self._sessions:
            raise ScreenerFetchError(
                "No screener.in sessions configured. Set SCREENER_SESSION_1_CSRF and "
                "SCREENER_SESSION_1_SID in backend/.env."
            )

    def fetch_sector(self, sector_url: str) -> pd.DataFrame:
        frames = [self._fetch_one(sector_url, session) for session in self._sessions]

        if len(frames) == 1:
            return frames[0]

        # Columns common to every session's table (S.No., Company, ...) show up
        # once per session; the analyzer dedups them by canonical name once it
        # maps screener.in's raw headers, so a plain concat is enough here.
        merged = pd.concat(frames, axis=1, join="inner")
        merged.attrs["tickers"] = frames[0].attrs.get("tickers", [])
        return merged

    def _fetch_one(self, sector_url: str, session: ScreenerSession) -> pd.DataFrame:
        try:
            return self._fetch_with(sector_url, session)
        except ScreenerSessionExpiredError:
            # Only now, once screener.in has shown the cookies are dead, log in again.
            refreshed = auth.refresh_session(session.label, session.session_id)
            if refreshed is None:
                raise
            return self._fetch_with(sector_url, ScreenerSession(**refreshed))

    def _fetch_with(self, sector_url: str, session: ScreenerSession) -> pd.DataFrame:
        headers = {"Cookie": f"csrftoken={session.csrf_token}; sessionid={session.session_id}"}
        try:
            response = get_with_retry(sector_url, headers, config.SCREENER_REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Request to screener.in failed for session '%s'", session.label)
            raise ScreenerFetchError(f"Could not reach screener.in: {exc}") from exc

        try:
            table = pd.read_html(StringIO(response.text))[0]
        except (ValueError, IndexError) as exc:
            raise ScreenerFetchError("screener.in returned a page with no data table") from exc

        if len(table.columns) < config.SCREENER_MIN_EXPECTED_COLUMNS:
            raise ScreenerSessionExpiredError(
                f"screener.in session '{session.label}' looks expired or invalid "
                f"(got {len(table.columns)} columns, expected at least "
                f"{config.SCREENER_MIN_EXPECTED_COLUMNS}). Refresh its csrftoken/sessionid "
                "in backend/.env."
            )

        table.attrs["tickers"] = _row_tickers(response.text)
        logger.info(
            "Fetched %d columns from screener.in using session '%s'", len(table.columns), session.label
        )
        return table


def get_with_retry(url: str, headers: dict, timeout: float, attempts: int = 3) -> requests.Response:
    """GET that waits and retries when screener.in answers 429 (too many requests)."""
    for attempt in range(attempts):
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 429 or attempt == attempts - 1:
            return response
        try:
            wait = float(response.headers.get("Retry-After", ""))
        except ValueError:
            wait = 5.0 * (attempt + 1)
        logger.warning("screener.in rate-limited %s; waiting %.0fs", url, wait)
        time.sleep(min(wait, 30.0))
    return response


def _row_tickers(html: str) -> list[str | None]:
    """Ticker for each row of the first table (from its /company/<TICKER>/ link), None if a row has none."""
    try:
        linked = pd.read_html(StringIO(html), extract_links="body")[0]
    except (ValueError, IndexError):
        return []
    for column in linked.columns:
        hrefs = [value[1] if isinstance(value, tuple) else None for value in linked[column]]
        if any(href and href.startswith("/company/") for href in hrefs):
            return [href.split("/")[2] if href and href.startswith("/company/") else None for href in hrefs]
    return []


def get_fetcher() -> BaseScreenerFetcher:
    if config.SCREENER_DATA_SOURCE == "session_cookie":
        return SessionCookieFetcher()
    raise ScreenerFetchError(f"Unknown SCREENER_DATA_SOURCE '{config.SCREENER_DATA_SOURCE}'")
