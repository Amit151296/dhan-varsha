"""Cleans and reshapes the raw screener.in table into the metric set the app scores.

This is a direct port of the original analysis notebook's pandas pipeline:
drop the serial-number column, drop any repeated header rows, rename columns,
compute 3-period averages for Sales/Profit/Return, and coerce types. Fixed
behaviour over the notebook version is called out inline.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.exceptions import DataShapeMismatchError

logger = logging.getLogger(__name__)

# screener.in leaves some cells blank for younger companies (e.g. no 7-year
# sales history). 999 flags "data missing" instead of silently dropping the
# row or crashing on NaN - and it deliberately lands in each scorer's top
# "yellow = anomaly" bucket below, so missing data stands out in the UI too.
MISSING_VALUE_SENTINEL = 999

RAW_COLUMN_NAMES = [
    "Name", "CMP", "Sales 3Yrs%", "Sales 5Yrs%", "Sales 7Yrs%",
    "Profit 3Yrs%", "Profit 5Yrs%", "Profit 7Yrs%",
    "Return 1Yr%", "Return 3Yr%", "Return 5Yr%",
    "CashFlow", "NP Ann", "PB_val", "Debt/Eq", "ROCE%", "ROE%", "MCap", "P/E",
    "Prom ch%", "FII ch%", "DII ch%", "Pledged%", "Div Yld%",
    "QoQ Sales var%", "QoQ Profits var%", "Prom Hold%",
    "Down 52%", "Up 52%", "1wk r%", "1mth r%", "3mth r%", "6mth r%",
]

FINAL_COLUMN_ORDER = [
    "Name", "CMP", "MCap", "Sales 3Yrs%", "Sales 5Yrs%", "Sales 7Yrs%", "Avg Sales",
    "Profit 3Yrs%", "Profit 5Yrs%", "Profit 7Yrs%", "Avg profit",
    "Return 1Yr%", "Return 3Yr%", "Return 5Yr%", "Avg Return",
    "CashFlow", "NP Ann", "PB_val", "Debt/Eq", "ROCE%", "ROE%", "P/E",
    "Prom ch%", "FII ch%", "DII ch%", "Pledged%", "Div Yld%",
    "QoQ Sales var%", "QoQ Profits var%", "Prom Hold%", "Down 52%", "Up 52%",
    "1wk r%", "1mth r%", "3mth r%", "6mth r%",
]

# Columns the original notebook rounded down to whole percentages/points.
INT_COLUMNS = [
    "P/E", "ROCE%", "ROE%", "Prom ch%", "FII ch%", "DII ch%", "Pledged%",
    "Div Yld%", "QoQ Sales var%", "QoQ Profits var%", "Prom Hold%",
    "Down 52%", "Up 52%",
]

FLOAT_COLUMNS = [
    column for column in FINAL_COLUMN_ORDER if column not in INT_COLUMNS and column != "Name"
]


def clean_and_enrich(raw: pd.DataFrame) -> pd.DataFrame:
    """Transform a raw screener.in table into the final, typed metric table."""
    df = raw.reset_index(drop=True)

    if "S.No." in df.columns:
        df = df.drop(columns=["S.No."])

    # Merging paginated/multi-session tables can repeat the header row - drop it.
    df = df[df.iloc[:, 0] != "Name"].reset_index(drop=True)

    if len(df.columns) != len(RAW_COLUMN_NAMES):
        raise DataShapeMismatchError(
            f"Expected {len(RAW_COLUMN_NAMES)} columns from screener.in, got "
            f"{len(df.columns)}. screener.in's table layout may have changed."
        )
    df.columns = RAW_COLUMN_NAMES

    df = df.fillna(MISSING_VALUE_SENTINEL).infer_objects(copy=False)

    df["Avg Sales"] = _average_of(df, "Sales 3Yrs%", "Sales 5Yrs%", "Sales 7Yrs%")
    df["Avg profit"] = _average_of(df, "Profit 3Yrs%", "Profit 5Yrs%", "Profit 7Yrs%")
    df["Avg Return"] = _average_of(df, "Return 1Yr%", "Return 3Yr%", "Return 5Yr%")

    df = df[FINAL_COLUMN_ORDER].copy()

    for column in FLOAT_COLUMNS:
        df[column] = (
            pd.to_numeric(df[column], errors="coerce").fillna(MISSING_VALUE_SENTINEL).astype(float)
        )
    for column in INT_COLUMNS:
        df[column] = (
            pd.to_numeric(df[column], errors="coerce").fillna(MISSING_VALUE_SENTINEL).astype(int)
        )

    logger.info("Cleaned %d rows across %d columns", len(df), len(df.columns))
    return df


def _average_of(df: pd.DataFrame, *columns: str) -> pd.Series:
    numeric = df[list(columns)].apply(pd.to_numeric, errors="coerce")
    return (numeric.sum(axis=1) / len(columns)).fillna(MISSING_VALUE_SENTINEL).astype(int)
