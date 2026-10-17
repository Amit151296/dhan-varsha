import pandas as pd
import pytest

from app.exceptions import DataShapeMismatchError
from app.services.screener import analyzer


def _raw_row(name="Acme Ltd", overrides=None):
    row = {
        "S.No.": 1,
        "Name": name,
        "CMP": 100.0,
        "Sales 3Yrs%": 10, "Sales 5Yrs%": 12, "Sales 7Yrs%": 14,
        "Profit 3Yrs%": 20, "Profit 5Yrs%": 22, "Profit 7Yrs%": 24,
        "Return 1Yr%": 5, "Return 3Yr%": 7, "Return 5Yr%": 9,
        "CashFlow": 1.1, "NP Ann": 2.2, "PB_val": 3.3, "Debt/Eq": 0.5,
        "ROCE%": 16, "ROE%": 16, "MCap": 5000.0, "P/E": 25,
        "Prom ch%": 1, "FII ch%": -1, "DII ch%": 0, "Pledged%": 0,
        "Div Yld%": 1, "QoQ Sales var%": 5, "QoQ Profits var%": 5,
        "Prom Hold%": 45, "Down 52%": 5, "Up 52%": 10,
        "1wk r%": 1, "1mth r%": 2, "3mth r%": 3, "6mth r%": 4,
    }
    if overrides:
        row.update(overrides)
    return row


def _raw_df(rows):
    # Column order mirrors what screener.in's HTML table yields (S.No. first).
    columns = list(_raw_row().keys())
    return pd.DataFrame(rows)[columns]


def test_clean_and_enrich_computes_averages_and_types():
    df = _raw_df([_raw_row()])
    cleaned = analyzer.clean_and_enrich(df)

    assert cleaned.loc[0, "Name"] == "Acme Ltd"
    assert cleaned.loc[0, "Avg Sales"] == 12  # (10+12+14)/3
    assert cleaned.loc[0, "Avg profit"] == 22
    assert cleaned.loc[0, "Avg Return"] == 7
    assert isinstance(cleaned.loc[0, "ROE%"].item(), int)
    assert isinstance(cleaned.loc[0, "Debt/Eq"].item(), float)
    assert list(cleaned.columns) == analyzer.FINAL_COLUMN_ORDER


def test_clean_and_enrich_drops_repeated_header_rows():
    header_repeat = _raw_row()
    header_repeat["Name"] = "Name"
    df = _raw_df([_raw_row(), header_repeat, _raw_row(name="Beta Ltd")])

    cleaned = analyzer.clean_and_enrich(df)

    assert len(cleaned) == 2
    assert "Name" not in cleaned["Name"].values


def test_clean_and_enrich_fills_missing_values_with_sentinel():
    row = _raw_row(overrides={"Sales 7Yrs%": None})
    df = _raw_df([row])

    cleaned = analyzer.clean_and_enrich(df)

    # (10 + 12 + 999) / 3 truncated to int, matching the notebook's own
    # fillna-before-average behaviour.
    assert cleaned.loc[0, "Avg Sales"] == int((10 + 12 + 999) / 3)


def test_clean_and_enrich_rejects_unexpected_column_count():
    df = _raw_df([_raw_row()]).drop(columns=["CashFlow"])

    with pytest.raises(DataShapeMismatchError):
        analyzer.clean_and_enrich(df)
