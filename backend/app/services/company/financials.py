"""Cleans a company's quarterly/yearly P&L tables and computes growth series.

Name-based row mapping (not positional), for the same reason the sector
analyzer moved away from positional column mapping: screener.in's page adds
or omits rows per company (e.g. "Raw PDF" links, a yearly-only "Dividend
Payout %" row), so matching by the row's own label is what actually survives
those differences.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# Keys have no "%" because clean_pl_table() strips every "%" from the table
# (values and row labels alike) before these are matched against row labels.
#
# Banks/NBFCs use a different set of row labels for the same concepts
# (Revenue instead of Sales, Financing Profit instead of Operating Profit,
# Financing Margin instead of OPM) - both variants map to the same canonical
# name so the same six charts work for every company type without the
# frontend needing to know which kind of company it's looking at.
ROW_ALIASES: dict[str, str] = {
    "sales": "Sales",
    "revenue": "Sales",
    "expenses": "Expenses",
    "operating profit": "Operating_profit",
    "financing profit": "Operating_profit",
    "opm": "OPM",
    "financing margin": "OPM",
    "other income": "Other_Income",
    "interest": "Interest",
    "depreciation": "Depreciation",
    "profit before tax": "Profit_before_tax",
    "tax": "Tax",
    "net profit": "Net_Profit",
    "eps in rs": "EPS",
    "dividend payout": "Dividend",
    "gross npa": "Gross_NPA",
    "net npa": "Net_NPA",
}

# Rows screener.in includes that aren't financial data (a link to the raw PDF report).
IGNORED_ROWS = {"raw pdf"}

# The six metrics the UI charts, matching the original analysis tool's scope.
METRIC_COLUMNS = ["Sales", "Operating_profit", "OPM", "Profit_before_tax", "Net_Profit", "EPS"]


def safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_row_label(label) -> str:
    text = str(label).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip("+").strip()
    return text.lower()


def clean_pl_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn a raw quarterly or yearly P&L table into a period-indexed, typed DataFrame."""
    df = raw.dropna(how="all")

    first_column = df.columns[0]
    df = df.rename(columns={first_column: "Parameters"})
    df = df.replace("%", "", regex=True)
    df = df.dropna(subset=df.columns[1:], how="all")

    row_rename: dict[str, str] = {}
    for raw_label in df["Parameters"]:
        normalized = _normalize_row_label(raw_label)
        if normalized in IGNORED_ROWS:
            continue
        canonical = ROW_ALIASES.get(normalized)
        if canonical is None:
            logger.warning("Unrecognised P&L row '%s' - ignoring it", raw_label)
            continue
        row_rename[raw_label] = canonical

    df = df[df["Parameters"].isin(row_rename.keys())].copy()
    df["Parameters"] = df["Parameters"].map(row_rename)
    df = df.drop_duplicates(subset="Parameters", keep="first")

    transposed = df.set_index("Parameters").T

    # Every mapped column is a financial figure - coerce all of them, not just
    # the 6 charted metrics, so columns like Expenses/Dividend are usable too.
    for column in transposed.columns:
        transposed[column] = pd.to_numeric(transposed[column], errors="coerce")

    return transposed


def compute_period_change(df: pd.DataFrame, column: str) -> list[dict]:
    """Change vs. the immediately preceding column (quarter-over-quarter, or
    year-over-year when `df` is the yearly table)."""
    if column not in df.columns:
        return []

    series = df[column]
    previous = series.shift(1).fillna(series)
    change_pct = ((series - previous) / previous * 100).replace([float("inf"), float("-inf")], None).round(2)

    return [
        {"period": period, "value": safe_float(series[period]), "change_pct": safe_float(change_pct[period])}
        for period in df.index
    ]


def compute_yoy(df: pd.DataFrame, column: str) -> list[dict]:
    """Change vs. the same quarter a year earlier, grouped by quarter label
    (all the Decembers together, then all the Junes, etc. - matching the
    original notebook's layout) rather than plain chronological order, since
    a same-quarter comparison reads naturally laid out next to its own kind.

    The first bar in each quarter group has no earlier value to compare
    against; it's shown as a 0.0% baseline (not blank) for the same reason:
    matching the original tool's convention of marking "first appearance of
    this quarter" rather than leaving a gap. `group_start` flags where each
    new quarter group begins, for the frontend to draw a separator.
    """
    if column not in df.columns:
        return []

    def quarter_label(period: str) -> str:
        return str(period)[:3]

    def year_of(period: str) -> int:
        try:
            return int(str(period)[-4:])
        except ValueError:
            return 0

    ordered_periods = sorted(df.index, key=lambda p: (quarter_label(p), year_of(p)))

    last_value_by_quarter: dict[str, float] = {}
    last_quarter_label = None
    results = []
    for period in ordered_periods:
        value = df.loc[period, column]
        quarter = quarter_label(period)
        previous = last_value_by_quarter.get(quarter)

        change_pct = None
        if not pd.isna(value):
            if previous is None:
                change_pct = 0.0
            elif previous != 0:
                change_pct = round((value - previous) / previous * 100, 2)

        results.append({
            "period": period,
            "value": safe_float(value),
            "change_pct": change_pct,
            "group_start": quarter != last_quarter_label,
        })

        if not pd.isna(value):
            last_value_by_quarter[quarter] = value
        last_quarter_label = quarter

    return results
