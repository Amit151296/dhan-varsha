from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services.market import index_performance as ip


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[models.IndexPerformanceCache.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _rows(tag="a"):
    return [{"name": f"Nifty {tag}", "return_1y": 5.0}]


def test_end_of_day_is_next_midnight_ist():
    now = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)  # 01:30 on 13 Nov in IST
    assert ip.end_of_day_ist(now) == datetime(2026, 11, 14, 0, 0, tzinfo=ip.IST)
    morning = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)  # 09:30 IST on 12 Nov
    assert ip.end_of_day_ist(morning) == datetime(2026, 11, 13, 0, 0, tzinfo=ip.IST)


def test_parse_keeps_only_tracked_indices():
    raw = [
        {"DispSym": "NIFTY Auto", "Ltp": 100.123, "PPerchange": -0.5, "PricePerchng1year": 12.3},
        {"DispSym": "Nifty Midcap150 Momentum 50", "Ltp": 1},
    ]
    rows = ip.parse_rows(raw)
    assert [r["name"] for r in rows] == ["NIFTY Auto"]
    assert rows[0]["ltp"] == 100.12 and rows[0]["return_3y"] is None


def test_cached_until_midnight_then_refetched(db, monkeypatch):
    calls = []
    monkeypatch.setattr(ip, "fetch_indices", lambda: calls.append(1) or _rows(str(len(calls))))
    morning = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)
    first = ip.get_index_performance(db, now=morning)
    again = ip.get_index_performance(db, now=morning + timedelta(hours=10))  # 19:30 IST, same day
    assert first["cached"] is False and again["cached"] is True and len(calls) == 1
    next_day = ip.get_index_performance(db, now=datetime(2026, 11, 12, 18, 31, tzinfo=timezone.utc))  # 00:01 IST
    assert next_day["cached"] is False and len(calls) == 2


def test_feed_failure_serves_stale_copy_or_raises(db, monkeypatch):
    def boom():
        raise ip.IndexDataError("down")

    monkeypatch.setattr(ip, "fetch_indices", boom)
    with pytest.raises(ip.IndexDataError):
        ip.get_index_performance(db)
    monkeypatch.setattr(ip, "fetch_indices", lambda: _rows())
    morning = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)
    ip.get_index_performance(db, now=morning)
    monkeypatch.setattr(ip, "fetch_indices", boom)
    result = ip.get_index_performance(db, now=morning + timedelta(days=1))
    assert result["stale"] is True and result["rows"] == ip.with_derived(_rows())


def test_workbook_has_numbers_and_filter():
    import io

    from openpyxl import load_workbook

    rows = [{"name": "Nifty 50", "ltp": 1.0, "return_1y": 5.5}, {"name": "NIFTY Auto", "ltp": 2.0, "return_1y": -1.0}]
    ws = load_workbook(io.BytesIO(ip.build_workbook(rows))).active
    assert [c.value for c in ws[1]][:2] == ["Index", "Last price"]
    assert ws["H2"].value == 5.5 and ws.auto_filter.ref


def test_up_from_52w_low_is_derived():
    rows = ip.with_derived([{"name": "A", "ltp": 120.0, "low_52w": 100.0}, {"name": "B", "ltp": 5.0, "low_52w": None}])
    assert rows[0]["up_from_low_pct"] == 20.0 and rows[1]["up_from_low_pct"] is None


def test_members_are_fetched_per_index_once_a_day_and_slug_is_checked(db, monkeypatch):
    monkeypatch.setattr(ip, "fetch_indices", lambda: [{"name": "Nifty Bank", "slug": "nifty-bank", "ltp": 1.0}])
    calls = []
    monkeypatch.setattr(ip, "fetch_members", lambda slug: calls.append(slug) or [{"name": "HDFC Bank"}])
    morning = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)
    first = ip.get_index_members(db, "nifty-bank", now=morning)
    again = ip.get_index_members(db, "nifty-bank", now=morning + timedelta(hours=5))
    assert first["index_name"] == "Nifty Bank" and again["cached"] is True and calls == ["nifty-bank"]
    with pytest.raises(ip.IndexNotFound):
        ip.get_index_members(db, "../evil", now=morning)
    assert calls == ["nifty-bank"]


def test_fetch_members_parses_the_embedded_page_data(monkeypatch):
    import json as _json

    page = '<script id="__NEXT_DATA__" type="application/json">' + _json.dumps(
        {"props": {"pageProps": {"sniData": [
            {"DispSym": "Small Co", "Mcap": 10, "Ltp": 120, "Low1Yr": 100, "Pe": 5, "Sector": "X"},
            {"DispSym": "Big Co", "Mcap": 500, "Ltp": 50, "Low1Yr": 0},
        ]}}}
    ) + "</script>"

    class R:
        text = page

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ip.requests, "get", lambda *a, **k: R())
    rows = ip.fetch_members("nifty-x")
    assert [r["name"] for r in rows] == ["Big Co", "Small Co"]
    assert rows[1]["up_from_low_pct"] == 20.0 and rows[0]["up_from_low_pct"] is None
