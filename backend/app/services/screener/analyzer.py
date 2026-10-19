"""Cleans and reshapes the raw screener.in table into the metric set the app scores.

This is a name-based port of the original analysis notebook's pandas
pipeline: drop the serial-number column, drop any repeated header rows, map
each raw screener.in header to a friendly canonical name, average whichever
growth/return periods are present, and coerce types.

screener.in does not expose the same set of columns for every sector/account
combination (e.g. a 5-year return column shows up for some sectors but not
others). The original notebook assumed a fixed column count and position,
which breaks the moment that set changes even slightly. This version maps by
*name* instead, so optional columns (like 5-year return) are picked up when
present and skipped cleanly when they're not, instead of crashing.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from app.exceptions import DataShapeMismatchError

logger = logging.getLogger(__name__)

# screener.in leaves some cells blank for younger companies (e.g. no 7-year
# sales history). 999 flags "data missing" instead of silently dropping the
# row or crashing on NaN - and it deliberately lands in each scorer's top
# "yellow = anomaly" bucket, so missing data stands out in the UI too.
MISSING_VALUE_SENTINEL = 999

# Raw screener.in headers (after whitespace-normalising) -> canonical name.
# "Name" is required; every other canonical column is optional and is only
# produced when screener.in actually sends it for that sector/account.
COLUMN_ALIASES: dict[str, str] = {
    "company": "Name",
    "cmp rs.": "CMP",
    "mar cap rs.cr.": "MCap",
    "sales var 3yrs %": "Sales 3Yrs%",
    "sales var 5yrs %": "Sales 5Yrs%",
    "sales var 7yrs %": "Sales 7Yrs%",
    "profit var 3yrs %": "Profit 3Yrs%",
    "profit var 5yrs %": "Profit 5Yrs%",
    "profit var 7yrs %": "Profit 7Yrs%",
    "1yr return %": "Return 1Yr%",
    "3yrs return %": "Return 3Yr%",
    "5yrs return %": "Return 5Yr%",
    "free cash flow rs.cr.": "CashFlow",
    "np ann rs.cr.": "NP Ann",
    "cmp / bv": "PB_val",
    "debt / eq": "Debt/Eq",
    "roce %": "ROCE%",
    "roe %": "ROE%",
    "p/e": "P/E",
    "change in prom hold %": "Prom ch%",
    "chg in fii hold %": "FII ch%",
    "chg in dii hold %": "DII ch%",
    "pledged %": "Pledged%",
    "div yld %": "Div Yld%",
    "qtr sales var %": "QoQ Sales var%",
    "qtr profit var %": "QoQ Profits var%",
    "prom. hold. %": "Prom Hold%",
    "down %": "Down 52%",
    "up %": "Up 52%",
    "1wk return %": "1wk r%",
    "1mth return %": "1mth r%",
    "3mth return %": "3mth r%",
    "6mth return %": "6mth r%",
}

# Columns ignored outright - present in the raw table but not part of the
# analysis (the serial number screener.in prints per row).
IGNORED_RAW_COLUMNS = {"s.no."}

# Preferred display order. Any column not present in a given fetch (e.g.
# "Return 5Yr%" when screener.in didn't send it) is simply skipped.
PREFERRED_COLUMN_ORDER = [
    "Name", "CMP", "MCap", "Sales 3Yrs%", "Sales 5Yrs%", "Sales 7Yrs%", "Avg Sales",
    "Profit 3Yrs%", "Profit 5Yrs%", "Profit 7Yrs%", "Avg profit",
    "Return 1Yr%", "Return 3Yr%", "Return 5Yr%", "Avg Return",
    "CashFlow", "NP Ann", "PB_val", "Debt/Eq", "ROCE%", "ROE%", "P/E",
    "Prom ch%", "FII ch%", "DII ch%", "Pledged%", "Div Yld%",
    "QoQ Sales var%", "QoQ Profits var%", "Prom Hold%", "Down 52%", "Up 52%",
    "1wk r%", "1mth r%", "3mth r%", "6mth r%",
]

# Columns the original notebook rounded down to whole percentages/points.
INT_COLUMNS = {
    "P/E", "ROCE%", "ROE%", "Prom ch%", "FII ch%", "DII ch%", "Pledged%",
    "Div Yld%", "QoQ Sales var%", "QoQ Profits var%", "Prom Hold%",
    "Down 52%", "Up 52%",
}

# (canonical average column, source columns in priority order) - whichever
# source columns are actually present for this fetch get averaged together.
AVERAGE_DEFINITIONS = [
    ("Avg Sales", ["Sales 3Yrs%", "Sales 5Yrs%", "Sales 7Yrs%"]),
    ("Avg profit", ["Profit 3Yrs%", "Profit 5Yrs%", "Profit 7Yrs%"]),
    ("Avg Return", ["Return 1Yr%", "Return 3Yr%", "Return 5Yr%"]),
]


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", str(header).strip().lower())


def _canonical_rename_map(columns: list[str]) -> dict[str, str]:
    rename_map = {}
    for column in columns:
        normalized = _normalize_header(column)
        if normalized in IGNORED_RAW_COLUMNS:
            continue
        canonical = COLUMN_ALIASES.get(normalized)
        if canonical is None:
            logger.warning("Unrecognised screener.in column '%s' - ignoring it", column)
            continue
        rename_map[column] = canonical
    return rename_map


def clean_and_enrich(raw: pd.DataFrame) -> pd.DataFrame:
    """Transform a raw screener.in table into the final, typed metric table."""
    df = raw.reset_index(drop=True)

    rename_map = _canonical_rename_map(list(df.columns))
    name_raw_headers = {raw for raw, canonical in rename_map.items() if canonical == "Name"}
    if not name_raw_headers:
        raise DataShapeMismatchError(
            "Could not find the company name column in screener.in's response. "
            "screener.in's table layout may have changed."
        )

    df = df[list(rename_map.keys())].rename(columns=rename_map)
    # A canonical name can appear twice if sessions overlapped on a column
    # that differs only by formatting; keep the first occurrence.
    df = df.loc[:, ~df.columns.duplicated()]

    # Merging paginated/multi-session tables can repeat the header row as a
    # data row - it shows up as the raw header text (e.g. "Company"), not the
    # canonical "Name", since the rename above only touches column labels.
    df = df[~df["Name"].isin(name_raw_headers | {"Name"})].reset_index(drop=True)

    df = df.fillna(MISSING_VALUE_SENTINEL).infer_objects(copy=False)

    present_metric_columns = [c for c in df.columns if c != "Name"]
    for column in present_metric_columns:
        is_int = column in INT_COLUMNS
        cast = int if is_int else float
        df[column] = (
            pd.to_numeric(df[column], errors="coerce")
            .fillna(MISSING_VALUE_SENTINEL)
            .astype(cast)
        )

    for average_column, source_columns in AVERAGE_DEFINITIONS:
        available_sources = [c for c in source_columns if c in df.columns]
        if available_sources:
            df[average_column] = _average_of(df, available_sources)

    final_order = [c for c in PREFERRED_COLUMN_ORDER if c in df.columns]
    df = df[final_order].copy()

    logger.info(
        "Cleaned %d rows across %d columns (%s)",
        len(df), len(df.columns), ", ".join(final_order),
    )
    return df


def _average_of(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    numeric = df[columns].apply(pd.to_numeric, errors="coerce")
    return (numeric.sum(axis=1) / len(columns)).fillna(MISSING_VALUE_SENTINEL).astype(int)
