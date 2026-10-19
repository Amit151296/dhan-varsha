import pandas as pd
import pytest

from app.services.company import analyzer
from app.services.company.analyzer import _safe_shareholding, analyse_company, canonical_company_key, variant_urls


def test_safe_shareholding_returns_empty_when_table_missing():
    tables = [pd.DataFrame()] * 5  # fewer tables than the expected shareholding index

    result = _safe_shareholding(tables, 11, "/company/TINY/")

    assert result == {"periods": [], "series": {}}


def test_safe_shareholding_returns_empty_on_malformed_table():
    # A completely empty table (no columns at all) can't be cleaned.
    tables = [pd.DataFrame()]

    result = _safe_shareholding(tables, 0, "/company/TINY/")

    assert result == {"periods": [], "series": {}}


def test_safe_shareholding_parses_a_valid_table():
    tables = [
        pd.DataFrame({
            "Unnamed: 0": ["Promoters", "Public"],
            "Sep 2024": ["60.00%", "40.00%"],
        })
    ]

    result = _safe_shareholding(tables, 0, "/company/REAL/")

    assert result["periods"] == ["Sep 2024"]
    assert result["series"]["Promoters"] == [60.0]


@pytest.mark.parametrize(
    "given,expected",
    [
        ("/company/TCS/consolidated/", ("/company/TCS/", "/company/TCS/consolidated/")),
        ("/company/TCS/", ("/company/TCS/", "/company/TCS/consolidated/")),
        ("/company/TCS", ("/company/TCS/", "/company/TCS/consolidated/")),
    ],
)
def test_variant_urls_normalizes_either_input_form(given, expected):
    assert variant_urls(given) == expected


def test_canonical_company_key_is_the_standalone_url_either_way():
    assert canonical_company_key("/company/TCS/consolidated/") == "/company/TCS/"
    assert canonical_company_key("/company/TCS/") == "/company/TCS/"


def _pl_table(periods: list[str], sales: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "Unnamed: 0": ["Sales\xa0+", "Net Profit\xa0+", "EPS in Rs"],
        **{p: [sales[i], sales[i] / 2, 1.0] for i, p in enumerate(periods)},
    })


def _degenerate_table() -> pd.DataFrame:
    # Mimics what screener.in returns for a company with no consolidated report.
    return pd.DataFrame({"Expenses\xa0+": [1, 2, 3]})


def _shareholding_table(periods: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "Unnamed: 0": ["Promoters", "Public"],
        **{p: ["60.00%", "40.00%"] for p in periods},
    })


def test_analyse_company_falls_back_to_standalone_when_no_consolidated_report(monkeypatch):
    standalone_periods = ["Mar 2024", "Mar 2025"]
    standalone_tables = (
        [_pl_table(standalone_periods, [100.0, 120.0]), _pl_table(standalone_periods, [100.0, 120.0])]
        + [pd.DataFrame()] * 9
        + [_shareholding_table(standalone_periods), _shareholding_table(standalone_periods)]
    )
    consolidated_tables = [_degenerate_table()] * 13

    def fake_fetch(url):
        return consolidated_tables if "consolidated" in url else standalone_tables

    monkeypatch.setattr(analyzer, "fetch_company_tables", fake_fetch)

    result = analyse_company("/company/SOLO/")

    assert result["consolidated"] is None
    assert result["standalone"]["quarterly"]["periods"] == standalone_periods
    assert result["shareholding"]["quarterly"]["periods"] == standalone_periods


def test_analyse_company_returns_both_when_consolidated_report_exists(monkeypatch):
    periods = ["Mar 2024", "Mar 2025"]
    standalone_tables = (
        [_pl_table(periods, [100.0, 120.0]), _pl_table(periods, [100.0, 120.0])]
        + [pd.DataFrame()] * 9
        + [_shareholding_table(periods), _shareholding_table(periods)]
    )
    consolidated_tables = (
        [_pl_table(periods, [150.0, 180.0]), _pl_table(periods, [150.0, 180.0])]
        + [pd.DataFrame()] * 9
        + [_shareholding_table(periods), _shareholding_table(periods)]
    )

    def fake_fetch(url):
        return consolidated_tables if "consolidated" in url else standalone_tables

    monkeypatch.setattr(analyzer, "fetch_company_tables", fake_fetch)

    result = analyse_company("/company/GROUP/")

    assert result["consolidated"] is not None
    standalone_sales = [p["value"] for p in result["standalone"]["quarterly"]["metrics"]["Sales"]["qoq"]]
    consolidated_sales = [p["value"] for p in result["consolidated"]["quarterly"]["metrics"]["Sales"]["qoq"]]
    assert standalone_sales == [100.0, 120.0]
    assert consolidated_sales == [150.0, 180.0]
