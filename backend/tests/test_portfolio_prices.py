from types import SimpleNamespace

from app.services.portfolio import prices


def test_apply_price_rounds_everything_to_whole_rupees():
    holding = SimpleNamespace(quantity=10, avg_price=99.6, invested_value=None, ltp=None, pnl=None)

    prices.apply_price(holding, 123.6)

    assert holding.ltp == 124  # round(123.6)
    assert holding.current_value == 1236  # round(10 * 123.6)
    assert holding.pnl == round(1236 - 996)
    assert isinstance(holding.ltp, int)
    assert holding.price_is_approximate is False


def test_apply_price_marks_approximate_when_requested():
    holding = SimpleNamespace(quantity=5, avg_price=10.0, invested_value=None, ltp=None, pnl=None)

    prices.apply_price(holding, 20.0, is_approximate=True)

    assert holding.price_is_approximate is True


def test_fetch_price_for_holding_prefers_yahoo_over_screener(monkeypatch):
    monkeypatch.setattr(prices, "fetch_price", lambda ticker: 100.0)
    monkeypatch.setattr(prices, "fetch_screener_price", lambda url: 999.0)

    price, is_approximate = prices.fetch_price_for_holding("TCS", "/company/TCS/consolidated/")

    assert price == 100.0
    assert is_approximate is False


def test_fetch_price_for_holding_falls_back_to_screener_when_yahoo_has_nothing(monkeypatch):
    monkeypatch.setattr(prices, "fetch_price", lambda ticker: None)
    monkeypatch.setattr(prices, "fetch_screener_price", lambda url: 55.0)

    price, is_approximate = prices.fetch_price_for_holding("TINYCO", "/company/TINYCO/")

    assert price == 55.0
    assert is_approximate is True


def test_fetch_price_for_holding_returns_none_when_both_sources_fail(monkeypatch):
    monkeypatch.setattr(prices, "fetch_price", lambda ticker: None)
    monkeypatch.setattr(prices, "fetch_screener_price", lambda url: None)

    price, is_approximate = prices.fetch_price_for_holding("TINYCO", "/company/TINYCO/")

    assert price is None
    assert is_approximate is False


def test_fetch_price_for_holding_skips_screener_without_a_resolved_url(monkeypatch):
    calls = []
    monkeypatch.setattr(prices, "fetch_price", lambda ticker: None)
    monkeypatch.setattr(prices, "fetch_screener_price", lambda url: calls.append(url) or 10.0)

    price, is_approximate = prices.fetch_price_for_holding(None, None)

    assert price is None
    assert calls == []


def test_fetch_screener_price_parses_the_current_price_figure(monkeypatch):
    html = """
    <ul>
      <li class="flex flex-space-between">
        <span class="name">Market Cap</span>
        <span class="nowrap value"><span class="number">8,95,621</span></span>
      </li>
      <li class="flex flex-space-between">
        <span class="name">Current Price</span>
        <span class="nowrap value">Rs<span class="number">2,475</span></span>
      </li>
    </ul>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            pass

    monkeypatch.setattr(prices.config, "SCREENER_SESSIONS", [
        {"label": "account_1", "csrf_token": "x", "session_id": "y"}
    ])
    monkeypatch.setattr(prices.requests, "get", lambda *a, **k: FakeResponse())

    assert prices.fetch_screener_price("/company/TCS/consolidated/") == 2475.0


def test_fetch_screener_price_returns_none_without_configured_sessions(monkeypatch):
    monkeypatch.setattr(prices.config, "SCREENER_SESSIONS", [])

    assert prices.fetch_screener_price("/company/TCS/consolidated/") is None


def test_nse_is_tried_before_bse_for_named_tickers():
    assert prices._symbols_to_try("RADHIKAJWE") == ["RADHIKAJWE.NS", "RADHIKAJWE.BO"]
    assert prices._symbols_to_try("521252") == ["521252.BO"]


def test_bse_quote_is_used_when_nse_has_none(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, price):
            self._price = price

        def raise_for_status(self):
            pass

        def json(self):
            return {"chart": {"result": [{"meta": {"regularMarketPrice": self._price}}]}}

    def fake_get(url, **kwargs):
        calls.append(url)
        return Resp(None if ".NS" in url else 42.0)

    monkeypatch.setattr(prices.requests, "get", fake_get)

    assert prices.fetch_price("SOMECO") == 42.0
    assert ".NS" in calls[0] and ".BO" in calls[1]
