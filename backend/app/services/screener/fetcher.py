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
from dataclasses import dataclass

import pandas as pd
import requests

from app import config
from app.exceptions import ScreenerFetchError, ScreenerSessionExpiredError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenerSession:
    label: str
    csrf_token: str
    session_id: str


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

        merged = pd.concat(frames, axis=1, join="inner")
        # Columns common to every session's table show up once per session; keep one copy.
        merged = merged.T.drop_duplicates().T
        return merged

    def _fetch_one(self, sector_url: str, session: ScreenerSession) -> pd.DataFrame:
        headers = {"Cookie": f"csrftoken={session.csrf_token}; sessionid={session.session_id}"}
        try:
            response = requests.get(
                sector_url, headers=headers, timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Request to screener.in failed for session '%s'", session.label)
            raise ScreenerFetchError(f"Could not reach screener.in: {exc}") from exc

        try:
            table = pd.read_html(response.text)[0]
        except (ValueError, IndexError) as exc:
            raise ScreenerFetchError("screener.in returned a page with no data table") from exc

        if len(table.columns) < config.SCREENER_MIN_EXPECTED_COLUMNS:
            raise ScreenerSessionExpiredError(
                f"screener.in session '{session.label}' looks expired or invalid "
                f"(got {len(table.columns)} columns, expected at least "
                f"{config.SCREENER_MIN_EXPECTED_COLUMNS}). Refresh its csrftoken/sessionid "
                "in backend/.env."
            )

        logger.info(
            "Fetched %d columns from screener.in using session '%s'", len(table.columns), session.label
        )
        return table


def get_fetcher() -> BaseScreenerFetcher:
    if config.SCREENER_DATA_SOURCE == "session_cookie":
        return SessionCookieFetcher()
    raise ScreenerFetchError(f"Unknown SCREENER_DATA_SOURCE '{config.SCREENER_DATA_SOURCE}'")
