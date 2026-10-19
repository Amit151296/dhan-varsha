import pandas as pd
import pytest

from app.services.company import financials


def _quarterly_raw():
    periods = ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025"]
    rows = {
        "Unnamed: 0": [
            "Sales\xa0+", "Expenses\xa0+", "Operating Profit", "OPM %",
            "Other Income\xa0+", "Interest", "Depreciation", "Profit before tax",
            "Tax %", "Net Profit\xa0+", "EPS in Rs", "Raw PDF",
        ],
        periods[0]: [100, 60, 40, "40", 2, 1, 3, 38, "25", 28, 2.1, None],
        periods[1]: [110, 65, 45, "41", 2, 1, 3, 43, "25", 32, 2.4, None],
        periods[2]: [90, 55, 35, "39", 2, 1, 3, 33, "25", 24, 1.8, None],
        periods[3]: [120, 70, 50, "42", 2, 1, 3, 48, "25", 36, 2.7, None],
    }
    return pd.DataFrame(rows)


def test_clean_pl_table_maps_rows_by_name_and_drops_raw_pdf():
    cleaned = financials.clean_pl_table(_quarterly_raw())

    assert "Raw PDF" not in cleaned.columns
    assert list(cleaned.index) == ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025"]
    assert cleaned.loc["Sep 2024", "Sales"] == 100
    assert cleaned.loc["Dec 2024", "OPM"] == 41
    assert cleaned.loc["Mar 2025", "Net_Profit"] == 24


def test_clean_pl_table_handles_yearly_dividend_row():
    periods = ["Mar 2024", "Mar 2025"]
    rows = {
        "Unnamed: 0": ["Sales\xa0+", "Net Profit\xa0+", "EPS in Rs", "Dividend Payout %"],
        periods[0]: [100, 20, 2.0, "30"],
        periods[1]: [120, 25, 2.5, "32"],
    }
    cleaned = financials.clean_pl_table(pd.DataFrame(rows))

    assert "Dividend" in cleaned.columns
    assert cleaned.loc["Mar 2025", "Dividend"] == 32


def test_compute_period_change_quarter_over_quarter():
    cleaned = financials.clean_pl_table(_quarterly_raw())

    result = financials.compute_period_change(cleaned, "Sales")

    assert result[0]["change_pct"] == 0.0  # first period compares to itself
    assert result[1]["value"] == 110
    assert result[1]["change_pct"] == 10.0  # (110-100)/100 * 100
    assert result[2]["change_pct"] == pytest.approx(-18.18, abs=0.01)


def test_compute_yoy_groups_by_quarter_with_zero_baseline_and_separators():
    periods = ["Mar 2024", "Jun 2024", "Mar 2025", "Jun 2025"]
    df = pd.DataFrame({"Sales": [100.0, 90.0, 120.0, 99.0]}, index=periods)

    result = financials.compute_yoy(df, "Sales")

    # Regrouped so every "Jun" is together, then every "Mar" - "Jun" sorts
    # before "Mar" alphabetically, matching the original notebook's ordering.
    assert [r["period"] for r in result] == ["Jun 2024", "Jun 2025", "Mar 2024", "Mar 2025"]

    assert result[0]["change_pct"] == 0.0  # first "Jun" - baseline, not blank
    assert result[0]["group_start"] is True
    assert result[1]["change_pct"] == 10.0  # Jun 2025 vs Jun 2024: (99-90)/90*100
    assert result[1]["group_start"] is False
    assert result[2]["change_pct"] == 0.0  # first "Mar" - new group, baseline
    assert result[2]["group_start"] is True
    assert result[3]["change_pct"] == 20.0  # Mar 2025 vs Mar 2024: (120-100)/100*100
    assert result[3]["group_start"] is False


def test_clean_pl_table_maps_bank_row_names_to_the_same_canonical_metrics():
    # Banks/NBFCs use Revenue/Financing Profit/Financing Margin instead of
    # Sales/Operating Profit/OPM for the same underlying concepts.
    periods = ["Sep 2024", "Dec 2024"]
    rows = {
        "Unnamed: 0": [
            "Revenue\xa0+", "Interest", "Expenses\xa0+", "Financing Profit",
            "Financing Margin %", "Profit before tax", "Net Profit\xa0+",
            "EPS in Rs", "Gross NPA %", "Net NPA %", "Raw PDF",
        ],
        periods[0]: [100, 10, 60, 30, "30", 28, 20, 1.5, "1.2", "0.3", None],
        periods[1]: [110, 11, 65, 34, "31", 32, 23, 1.7, "1.1", "0.3", None],
    }
    cleaned = financials.clean_pl_table(pd.DataFrame(rows))

    assert cleaned.loc["Sep 2024", "Sales"] == 100
    assert cleaned.loc["Dec 2024", "Operating_profit"] == 34
    assert cleaned.loc["Sep 2024", "OPM"] == 30
    assert cleaned.loc["Dec 2024", "Gross_NPA"] == 1.1


def test_compute_period_change_missing_column_returns_empty():
    df = pd.DataFrame({"Sales": [100.0]}, index=["Mar 2024"])
    assert financials.compute_period_change(df, "Nonexistent") == []
    assert financials.compute_yoy(df, "Nonexistent") == []
