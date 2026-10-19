import pandas as pd
import pytest

from app.exceptions import DataShapeMismatchError
from app.services.screener import analyzer


def _raw_row(name="Acme Ltd", overrides=None, include_5yr_return=False):
    row = {
        "S.No.": 1,
        "Company": name,
        "CMP  Rs.": 100.0,
        "Sales Var 3Yrs  %": 10, "Sales Var 5Yrs  %": 12, "Sales Var 7Yrs  %": 14,
        "Profit Var 3Yrs  %": 20, "Profit Var 5Yrs  %": 22, "Profit Var 7Yrs  %": 24,
        "1Yr return  %": 5, "3Yrs return  %": 7,
        "Free Cash Flow  Rs.Cr.": 1.1, "NP Ann  Rs.Cr.": 2.2, "CMP / BV": 3.3, "Debt / Eq": 0.5,
        "ROCE  %": 16, "ROE  %": 16, "Mar Cap  Rs.Cr.": 5000.0, "P/E": 25,
        "Change in Prom Hold  %": 1, "Chg in FII Hold  %": -1, "Chg in DII Hold  %": 0,
        "Pledged  %": 0, "Div Yld  %": 1,
        "Qtr Sales Var  %": 5, "Qtr Profit Var  %": 5,
        "Prom. Hold.  %": 45, "Down  %": 5, "Up  %": 10,
        "1wk return  %": 1, "1mth return  %": 2, "3mth return  %": 3, "6mth return  %": 4,
    }
    if include_5yr_return:
        row["5Yrs return  %"] = 9
    if overrides:
        row.update(overrides)
    return row


def _raw_df(rows):
    columns = list(rows[0].keys())
    return pd.DataFrame(rows)[columns]


def test_clean_and_enrich_computes_averages_and_types():
    df = _raw_df([_raw_row()])
    cleaned = analyzer.clean_and_enrich(df)

    assert cleaned.loc[0, "Name"] == "Acme Ltd"
    assert cleaned.loc[0, "Avg Sales"] == 12  # (10+12+14)/3
    assert cleaned.loc[0, "Avg profit"] == 22
    assert cleaned.loc[0, "Avg Return"] == 6  # (5+7)/2 - no 5yr return in this fetch
    assert isinstance(cleaned.loc[0, "ROE%"].item(), int)
    assert isinstance(cleaned.loc[0, "Debt/Eq"].item(), float)
    assert "Return 5Yr%" not in cleaned.columns


def test_clean_and_enrich_includes_5yr_return_when_screener_sends_it():
    df = _raw_df([_raw_row(include_5yr_return=True)])
    cleaned = analyzer.clean_and_enrich(df)

    assert "Return 5Yr%" in cleaned.columns
    assert cleaned.loc[0, "Return 5Yr%"] == 9
    assert cleaned.loc[0, "Avg Return"] == 7  # (5+7+9)/3


def test_clean_and_enrich_merges_columns_split_across_sessions():
    # Mimics concatenating two session tables: shared columns (S.No., Company,
    # CMP, Mar Cap) repeated, each session contributing different metrics -
    # exactly what fetcher.SessionCookieFetcher.fetch_sector() hands over.
    row = _raw_row()
    session_1_cols = [
        "S.No.", "Company", "CMP  Rs.", "Sales Var 3Yrs  %", "Sales Var 5Yrs  %",
        "Sales Var 7Yrs  %", "ROCE  %", "ROE  %", "Mar Cap  Rs.Cr.",
    ]
    session_2_cols = ["S.No.", "Company", "CMP  Rs.", "P/E", "Pledged  %", "Mar Cap  Rs.Cr."]
    session_1_df = pd.DataFrame([{col: row[col] for col in session_1_cols}])[session_1_cols]
    session_2_df = pd.DataFrame([{col: row[col] for col in session_2_cols}])[session_2_cols]
    df = pd.concat([session_1_df, session_2_df], axis=1, join="inner")

    cleaned = analyzer.clean_and_enrich(df)

    assert list(cleaned.columns).count("MCap") <= 1
    assert cleaned.loc[0, "MCap"] == 5000.0
    assert cleaned.loc[0, "P/E"] == 25
    assert cleaned.loc[0, "ROCE%"] == 16


def test_clean_and_enrich_drops_repeated_header_rows():
    header_repeat = _raw_row()
    header_repeat["Company"] = "Company"
    df = _raw_df([_raw_row(), header_repeat, _raw_row(name="Beta Ltd")])

    cleaned = analyzer.clean_and_enrich(df)

    assert len(cleaned) == 2
    assert "Company" not in cleaned["Name"].values


def test_clean_and_enrich_fills_missing_values_with_sentinel():
    row = _raw_row(overrides={"Sales Var 7Yrs  %": None})
    df = _raw_df([row])

    cleaned = analyzer.clean_and_enrich(df)

    # (10 + 12 + 999) / 3 truncated to int, matching the notebook's own
    # fillna-before-average behaviour.
    assert cleaned.loc[0, "Avg Sales"] == int((10 + 12 + 999) / 3)


def test_clean_and_enrich_ignores_unrecognised_columns():
    df = _raw_df([_raw_row(overrides={"Some New Column  %": 42})])

    cleaned = analyzer.clean_and_enrich(df)

    assert "Some New Column  %" not in cleaned.columns
    assert cleaned.loc[0, "Name"] == "Acme Ltd"


def test_clean_and_enrich_requires_a_name_column():
    df = _raw_df([_raw_row()]).drop(columns=["Company"])

    with pytest.raises(DataShapeMismatchError):
        analyzer.clean_and_enrich(df)
