import pandas as pd
import pytest

from app import config
from app.exceptions import ScreenerFetchError, ScreenerSessionExpiredError
from app.services.screener import auth
from app.services.screener.fetcher import ScreenerSession, SessionCookieFetcher


class FakeCookies(dict):
    pass


class FakeHttp:
    """Stands in for requests.Session during login()."""

    def __init__(self, sessionid):
        self.cookies = FakeCookies(csrftoken="csrf-new")
        self._sessionid = sessionid

    def get(self, *a, **k):
        class R:
            text = '<form><input name="csrfmiddlewaretoken" value="form-token"></form>'

            def raise_for_status(self):
                pass

        return R()

    def post(self, *a, **k):
        if self._sessionid:
            self.cookies["sessionid"] = self._sessionid
        return object()


@pytest.fixture
def sessions(monkeypatch):
    data = [{"label": "account_1", "csrf_token": "old", "session_id": "old-sid",
             "username": "u@example.com", "password": "pw"}]
    monkeypatch.setattr(config, "SCREENER_SESSIONS", data)
    monkeypatch.setattr(auth, "_persist_to_env", lambda *a, **k: None)
    return data


def test_login_returns_fresh_cookies(monkeypatch):
    monkeypatch.setattr(auth.requests, "Session", lambda: FakeHttp("new-sid"))
    assert auth.login("u@example.com", "pw") == ("csrf-new", "new-sid")


def test_login_failure_names_the_account_but_never_the_password(monkeypatch):
    monkeypatch.setattr(auth.requests, "Session", lambda: FakeHttp(None))
    with pytest.raises(ScreenerFetchError) as exc:
        auth.login("u@example.com", "super-secret")
    assert "u@example.com" in str(exc.value)
    assert "super-secret" not in str(exc.value)


def test_refresh_updates_the_stored_session(monkeypatch, sessions):
    monkeypatch.setattr(auth, "login", lambda u, p: ("csrf-2", "sid-2"))
    refreshed = auth.refresh_session("account_1", "old-sid")
    assert refreshed["session_id"] == "sid-2"
    assert sessions[0]["csrf_token"] == "csrf-2"


def test_refresh_reuses_a_session_another_request_already_renewed(monkeypatch, sessions):
    sessions[0]["session_id"] = "already-new"
    monkeypatch.setattr(auth, "login", lambda u, p: pytest.fail("should not log in twice"))
    assert auth.refresh_session("account_1", "old-sid")["session_id"] == "already-new"


def test_refresh_without_login_details_does_nothing(monkeypatch):
    monkeypatch.setattr(config, "SCREENER_SESSIONS", [
        {"label": "account_1", "csrf_token": "a", "session_id": "b", "username": None, "password": None}])
    assert auth.refresh_session("account_1", "b") is None


def test_fetcher_logs_in_only_after_expiry_then_retries(monkeypatch, sessions):
    calls = []

    def fake_fetch_with(self, url, session):
        calls.append(session.session_id)
        if session.session_id == "old-sid":
            raise ScreenerSessionExpiredError("expired")
        return pd.DataFrame({"a": [1]})

    monkeypatch.setattr(SessionCookieFetcher, "_fetch_with", fake_fetch_with)
    monkeypatch.setattr(auth, "login", lambda u, p: ("csrf-2", "sid-2"))

    fetcher = SessionCookieFetcher(sessions=[ScreenerSession(**sessions[0])])
    fetcher._fetch_one("http://x", ScreenerSession(**sessions[0]))

    assert calls == ["old-sid", "sid-2"]


def test_fetcher_does_not_log_in_when_session_is_fine(monkeypatch, sessions):
    monkeypatch.setattr(SessionCookieFetcher, "_fetch_with", lambda self, u, s: pd.DataFrame({"a": [1]}))
    monkeypatch.setattr(auth, "login", lambda u, p: pytest.fail("must not log in on a healthy session"))

    SessionCookieFetcher(sessions=[ScreenerSession(**sessions[0])])._fetch_one(
        "http://x", ScreenerSession(**sessions[0]))
