"""Ties together fetch + financials + shareholding into the payload the API
and frontend charts consume.

screener.in reports standalone and consolidated P&L as separate pages
(/company/<ticker>/ vs /company/<ticker>/consolidated/) - mixing their numbers
together would be misleading, so both are fetched and kept in their own
section of the response. Not every company publishes a consolidated report
(no subsidiaries), so it's treated as optional, same as shareholding.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.exceptions import DataShapeMismatchError, ScreenerError
from app.services.company import financials, shareholding
from app.services.company.fetcher import fetch_company_tables

logger = logging.getLogger(__name__)

# Table positions on a screener.in company page, as observed today. If
# screener.in reorders its page sections this breaks loudly (IndexError /
# missing "Sales" row below) rather than silently analysing the wrong table.
QUARTERLY_PL_TABLE_INDEX = 0
YEARLY_PL_TABLE_INDEX = 1
QUARTERLY_SHAREHOLDING_TABLE_INDEX = 11
YEARLY_SHAREHOLDING_TABLE_INDEX = 12


def variant_urls(company_url: str) -> tuple[str, str]:
    """Derive (standalone_url, consolidated_url) from whichever variant was given."""
    base = company_url.rstrip("/")
    if base.endswith("/consolidated"):
        base = base[: -len("/consolidated")]
    return f"{base}/", f"{base}/consolidated/"


def canonical_company_key(company_url: str) -> str:
    """The standalone URL, used as a stable cache key regardless of which
    variant (standalone or consolidated) the caller originally passed in -
    one analysis fetches and returns both anyway."""
    standalone_url, _ = variant_urls(company_url)
    return standalone_url


def analyse_company(company_url: str) -> dict:
    standalone_url, consolidated_url = variant_urls(company_url)

    standalone_quarterly, standalone_yearly, standalone_tables = _fetch_and_clean_pl(standalone_url)

    consolidated_tables = None
    consolidated_block = None
    try:
        consolidated_quarterly, consolidated_yearly, consolidated_tables = _fetch_and_clean_pl(
            consolidated_url
        )
        consolidated_block = _pl_block(consolidated_quarterly, consolidated_yearly)
    except (DataShapeMismatchError, ScreenerError):
        logger.info(
            "No distinct consolidated financials for '%s' - standalone only", company_url, exc_info=True
        )

    # The two pages describe the same company, so one shareholding pattern
    # covers both - prefer it from whichever page actually has it (consolidated
    # when published, since that's screener.in's primary page for such companies).
    shareholding_source = consolidated_tables or standalone_tables

    shareholding_block = {
        "quarterly": _safe_shareholding(shareholding_source, QUARTERLY_SHAREHOLDING_TABLE_INDEX, company_url),
        "yearly": _safe_shareholding(shareholding_source, YEARLY_SHAREHOLDING_TABLE_INDEX, company_url),
    }

    logger.info(
        "Analysed company '%s': %d standalone quarters, consolidated %s",
        company_url, len(standalone_quarterly), "available" if consolidated_block else "unavailable",
    )

    return {
        "standalone": _pl_block(standalone_quarterly, standalone_yearly),
        "consolidated": consolidated_block,
        "shareholding": shareholding_block,
    }


def _fetch_and_clean_pl(url: str) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """Fetch one company-page variant and return (quarterly, yearly, raw_tables)."""
    tables = fetch_company_tables(url)

    try:
        quarterly_raw = tables[QUARTERLY_PL_TABLE_INDEX]
        yearly_raw = tables[YEARLY_PL_TABLE_INDEX]
    except IndexError as exc:
        raise DataShapeMismatchError(
            f"screener.in doesn't have enough financial history published for "
            f"'{url}' to analyse (only {len(tables)} data sections found)."
        ) from exc

    quarterly = financials.clean_pl_table(quarterly_raw)
    yearly = financials.clean_pl_table(yearly_raw)

    if "Sales" not in quarterly.columns or "Sales" not in yearly.columns:
        raise DataShapeMismatchError(
            f"screener.in doesn't have enough financial history published for "
            f"'{url}' to analyse - its P&L tables have no recognisable Sales/Revenue row."
        )

    return quarterly, yearly, tables


def _pl_block(quarterly: pd.DataFrame, yearly: pd.DataFrame) -> dict:
    return {
        "quarterly": {
            "periods": list(quarterly.index),
            "metrics": {
                column: {
                    "qoq": financials.compute_period_change(quarterly, column),
                    "yoy": financials.compute_yoy(quarterly, column),
                }
                for column in financials.METRIC_COLUMNS
                if column in quarterly.columns
            },
        },
        "yearly": {
            "periods": list(yearly.index),
            "metrics": {
                column: {"change": financials.compute_period_change(yearly, column)}
                for column in financials.METRIC_COLUMNS
                if column in yearly.columns
            },
        },
    }


_EMPTY_SHAREHOLDING_BLOCK = {"periods": [], "series": {}}


def _safe_shareholding(tables: list | None, table_index: int, company_url: str) -> dict:
    """Shareholding pattern is treated as optional: some companies (thinly
    traded micro-caps especially) don't publish one, and that shouldn't sink
    the whole analysis when the P&L data is otherwise fine.
    """
    if not tables or table_index >= len(tables):
        logger.info(
            "No shareholding table at index %d for '%s' - skipping it", table_index, company_url
        )
        return _EMPTY_SHAREHOLDING_BLOCK

    try:
        cleaned = shareholding.clean_shareholding_table(tables[table_index])
    except Exception:  # noqa: BLE001 - shareholding is optional, never fail the whole analysis over it
        logger.warning(
            "Could not parse shareholding table at index %d for '%s' - skipping it",
            table_index, company_url, exc_info=True,
        )
        return _EMPTY_SHAREHOLDING_BLOCK

    return {
        "periods": list(cleaned.index),
        "series": {column: [financials.safe_float(v) for v in cleaned[column]] for column in cleaned.columns},
    }
