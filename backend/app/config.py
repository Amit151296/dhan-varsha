import os
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Screener.in data source -------------------------------------------------
# "session_cookie" is the only implementation today: it reuses a logged-in
# browser session's csrftoken/sessionid cookies. When an official screener.in
# API becomes available, add a new fetcher class in
# app/services/screener/fetcher.py and point this at it - nothing else in the
# pipeline (analyzer/scoring/persistence/routes) needs to change.
SCREENER_DATA_SOURCE = os.getenv("SCREENER_DATA_SOURCE", "session_cookie")
SCREENER_REQUEST_TIMEOUT_SECONDS = int(os.getenv("SCREENER_REQUEST_TIMEOUT_SECONDS", "15"))

# screener.in's compare/export table has ~33 columns when a session is valid.
# A logged-out/expired session renders a stripped-down table instead, which is
# how we detect an expired cookie without screener.in returning an HTTP error.
SCREENER_MIN_EXPECTED_COLUMNS = int(os.getenv("SCREENER_MIN_EXPECTED_COLUMNS", "19"))


def _load_screener_sessions() -> list[dict]:
    """Load numbered SCREENER_SESSION_<n>_CSRF / _SID pairs from the environment.

    A single free screener.in account doesn't expose every column in the
    compare/export table, so multiple logged-in accounts are fetched and
    merged. Add more accounts later by adding SCREENER_SESSION_3_*, etc.
    """
    sessions = []
    index = 1
    while True:
        csrf_token = os.getenv(f"SCREENER_SESSION_{index}_CSRF")
        session_id = os.getenv(f"SCREENER_SESSION_{index}_SID")
        if not csrf_token or not session_id:
            break
        sessions.append(
            {"label": f"account_{index}", "csrf_token": csrf_token, "session_id": session_id}
        )
        index += 1
    return sessions


SCREENER_SESSIONS = _load_screener_sessions()
