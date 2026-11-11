"""Re-logs in to screener.in when a session cookie has expired.

Nothing here runs on a normal request: a fetch only calls refresh_session()
after screener.in has already shown it is treating that session as logged
out. Fresh cookies replace the in-memory ones and are written back to
backend/.env, so the next restart starts from a working session too.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

import requests
from lxml import html as lhtml

from app import config
from app.exceptions import ScreenerFetchError

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.screener.in/login/"
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

_refresh_lock = threading.Lock()


def login(username: str, password: str) -> tuple[str, str]:
    """Log in with screener.in's own form; returns (csrftoken, sessionid)."""
    http = requests.Session()
    try:
        page = http.get(LOGIN_URL, timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS)
        page.raise_for_status()
        token_inputs = lhtml.fromstring(page.text).xpath('//input[@name="csrfmiddlewaretoken"]/@value')
        form_token = token_inputs[0] if token_inputs else http.cookies.get("csrftoken", "")

        response = http.post(
            LOGIN_URL,
            data={"csrfmiddlewaretoken": form_token, "next": "", "username": username, "password": password},
            headers={"Referer": LOGIN_URL},
            timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ScreenerFetchError(f"Could not reach screener.in to log in: {exc}") from exc

    session_id = http.cookies.get("sessionid")
    if not session_id:
        # Never log the password; the username is enough to tell which account.
        raise ScreenerFetchError(
            f"screener.in login failed for '{username}'. Check the username/password in backend/.env "
            "(an account created via 'Login with Google' has no screener.in password until you set one "
            "through 'Forgot password')."
        )
    return http.cookies.get("csrftoken", form_token), session_id


def refresh_session(label: str, stale_session_id: str) -> dict | None:
    """Log the named account in again and update its stored cookies.

    Returns the updated session dict, or None if the account has no login
    details configured. `stale_session_id` is the cookie that just failed:
    if another request already replaced it while this one waited on the
    lock, that newer session is reused instead of logging in twice.
    """
    with _refresh_lock:
        session = next((s for s in config.SCREENER_SESSIONS if s["label"] == label), None)
        if session is None or not (session.get("username") and session.get("password")):
            return None
        if session["session_id"] and session["session_id"] != stale_session_id:
            return session

        logger.info("screener.in session '%s' expired - logging in again", label)
        csrf_token, session_id = login(session["username"], session["password"])
        session["csrf_token"] = csrf_token
        session["session_id"] = session_id
        _persist_to_env(label, csrf_token, session_id)
        return session


def _persist_to_env(label: str, csrf_token: str, session_id: str) -> None:
    index = label.rsplit("_", 1)[-1]
    try:
        text = ENV_PATH.read_text(encoding="utf-8")
        for suffix, value in (("CSRF", csrf_token), ("SID", session_id)):
            key = f"SCREENER_SESSION_{index}_{suffix}"
            line = f"{key}={value}"
            pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
            text = pattern.sub(lambda _m: line, text) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"
        ENV_PATH.write_text(text, encoding="utf-8")
    except OSError:
        logger.warning("Could not save refreshed screener.in cookies to %s", ENV_PATH, exc_info=True)
