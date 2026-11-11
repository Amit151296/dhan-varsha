from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.services.portfolio.analysis import NO_BROKER_LABEL, UNCLASSIFIED_LABEL, analyse_portfolio
from app.services.portfolio.merge import merge_holdings_into_portfolio
from app.services.portfolio.sectors import parse_sector_and_industry


def _extracted(name, url, qty, invested):
    return {
        "company_name": name,
        "quantity": qty,
        "avg_price": invested / qty,
        "ltp": None,
        "invested_value": invested,
        "current_value": invested,
        "pnl": 0.0,
        "resolved_name": name,
        "resolved_url": url,
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    models.PortfolioUpload.__table__.create(engine)
    models.PortfolioHolding.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _rows(db):
    return db.query(models.PortfolioHolding).order_by(models.PortfolioHolding.id).all()


def test_same_company_at_two_brokers_stays_as_two_rows(db):
    merge_holdings_into_portfolio(db, 1, 1, "Groww", [_extracted("PNB", "/company/PNB/consolidated/", 614, 64242.82)])
    merge_holdings_into_portfolio(db, 1, 2, "Angel One", [_extracted("PNB", "/company/PNB/", 100, 10000.0)])
    db.commit()

    rows = _rows(db)
    assert sorted((r.broker, r.quantity) for r in rows) == [("Angel One", 100), ("Groww", 614)]


def test_reuploading_the_same_broker_updates_instead_of_duplicating(db):
    merge_holdings_into_portfolio(db, 1, 1, "Groww", [_extracted("PNB", "/company/PNB/consolidated/", 614, 64242.82)])
    merge_holdings_into_portfolio(db, 1, 2, "Groww", [_extracted("PNB", "/company/PNB/", 700, 70000.0)])
    db.commit()

    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].quantity == 700


def test_row_without_a_broker_is_claimed_by_the_first_upload_that_names_one(db):
    merge_holdings_into_portfolio(db, 1, 1, None, [_extracted("PNB", "/company/PNB/", 614, 64242.82)])
    merge_holdings_into_portfolio(db, 1, 2, "Groww", [_extracted("PNB", "/company/PNB/", 614, 64242.82)])
    db.commit()

    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].broker == "Groww"


def _holding(name, broker, url, invested):
    return SimpleNamespace(
        raw_name=name, broker=broker, resolved_url=url, invested_value=invested,
        current_value=invested * 1.1, pnl=None, quantity=None, avg_price=None, ltp=None,
    )


def test_analysis_groups_by_broker_and_sector_and_counts_distinct_companies():
    holdings = [
        _holding("PNB", "Groww", "/company/PNB/consolidated/", 1000),
        _holding("PNB", "Angel One", "/company/PNB/", 500),
        _holding("TCS", "Angel One", "/company/TCS/consolidated/", 2000),
        _holding("Mystery", None, None, 100),
    ]
    sectors = {"/company/PNB/": ("Financial Services", "Banks"), "/company/TCS/": ("IT", "Software")}

    result = analyse_portfolio(holdings, sectors)

    brokers = {r["label"]: r for r in result["by_broker"]}
    assert brokers["Angel One"]["company_count"] == 2
    assert brokers["Angel One"]["invested"] == 2500
    assert brokers["Groww"]["invested"] == 1000
    assert brokers[NO_BROKER_LABEL]["invested"] == 100

    by_sector = {r["label"]: r for r in result["by_sector"]}
    # PNB is held at two brokers but is still one company.
    assert by_sector["Financial Services"]["company_count"] == 1
    assert by_sector["Financial Services"]["invested"] == 1500
    assert by_sector["IT"]["invested"] == 2000
    assert result["by_sector"][-1]["label"] == UNCLASSIFIED_LABEL

    assert result["company_count"] == 3
    assert result["total_invested"] == 3600
    assert round(sum(r["share_of_invested"] for r in result["by_broker"]), 0) == 100


def test_sector_and_industry_are_read_from_a_screener_page():
    html = (
        '<a href="/market/IN05/" target="_blank" title="Broad Sector">Financial Services</a>'
        '<a href="/market/IN05/IN0501/" target="_blank" title="Sector">Financial Services</a>'
        '<a href="/market/IN05/IN0501/IN050102/IN050102001/" target="_blank" title="Industry">Public Sector Bank</a>'
    )
    assert parse_sector_and_industry(html) == ("Financial Services", "Public Sector Bank")
    assert parse_sector_and_industry("<html>nothing</html>") == (None, None)


def test_shortened_name_queries_reject_a_loosely_matching_wrong_company(monkeypatch):
    from app.services.portfolio import matcher

    def fake_resolve(query):
        # Mimics screener.in search: the full name finds nothing, "The Indian Hotels" finds
        # an unrelated company, and the name without "The" finds the right one.
        results = {
            "Indian Hotels Co": {"name": "Indian Hotels Co Ltd", "url": "/company/INDHOTEL/consolidated/"},
            "The Indian Hotels": {"name": "The Indian Wood Products Company Ltd", "url": "/company/IWP/"},
        }
        return results.get(query)

    monkeypatch.setattr(matcher.company_search, "resolve_company_by_name", fake_resolve)
    assert matcher._resolve("The Indian Hotels Co")["url"] == "/company/INDHOTEL/consolidated/"

    # With only the wrong company available, it must come back unresolved, not wrong.
    monkeypatch.setattr(
        matcher.company_search,
        "resolve_company_by_name",
        lambda q: fake_resolve(q) if q == "The Indian Hotels" else None,
    )
    assert matcher._resolve("The Indian Hotels Co") is None
