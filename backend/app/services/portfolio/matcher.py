"""Resolves each extracted holding's company name to a screener.in company page,
reusing the same search-based matching already used for sector table rows.
"""

from __future__ import annotations

import logging
import re

from app.exceptions import ScreenerError
from app.services.company import search as company_search
from app.services.portfolio.amounts import reconcile_amounts
from app.services.portfolio.numbers import parse_number

logger = logging.getLogger(__name__)

# Broker apps shorten long company names; screener.in search needs the real words.
_ABBREVIATIONS = {
    "dep": "depository",
    "ship": "shipbuilders",
    "infra": "infrastructure",
    "engg": "engineering",
    "inds": "industries",
    "ind": "industries",
    "tech": "technologies",
    "svcs": "services",
    "intl": "international",
    "fin": "finance",
    "pharma": "pharmaceuticals",
}


_FILLER_WORDS = {"the", "ltd", "limited", "co", "company", "corp", "corporation", "of", "and", "&"}


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


_SERIES_SUFFIX = re.compile(r"^(?P<symbol>[A-Za-z0-9&]+)-(?:BE|EQ|BZ|BL|SM|ST|IL|GB|GS|N\d)$", re.IGNORECASE)


def strip_series_suffix(name: str) -> str:
    """NSE appends a series code to symbols in the trade-to-trade/SME segments
    (RADHIKAJWE-BE); brokers show it, but it isn't part of the company's ticker."""
    match = _SERIES_SUFFIX.match(name.strip())
    return match.group("symbol") if match else name.strip()


def _query_candidates(name: str) -> tuple[list[str], list[str]]:
    """(whole-name queries, shortened queries) for an abbreviated company name."""
    name = strip_series_suffix(name)
    words = [w.strip(".,") for w in name.split() if w.strip(".,")]
    expanded = [_ABBREVIATIONS.get(w.casefold(), w) for w in words]
    without_the = expanded[1:] if expanded and expanded[0].casefold() == "the" else expanded

    whole = [name.strip(), " ".join(words), " ".join(expanded), " ".join(without_the)]
    shortened = []
    for count in range(len(without_the) - 1, 1, -1):
        shortened.append(" ".join(without_the[:count]))
        shortened.append(" ".join(words[:count]))

    def unique(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        return [q for q in queries if q and not (q.casefold() in seen or seen.add(q.casefold()))]

    return unique(whole), unique(shortened)


def _contains_all_words(query: str, result_name: str) -> bool:
    haystack = _squash(result_name)
    words = [w for w in query.casefold().split() if w not in _FILLER_WORDS]
    return bool(words) and all(_squash(w) in haystack for w in words)


def _resolve(name: str) -> dict | None:
    whole, shortened = _query_candidates(name)
    for query in whole:
        match = company_search.resolve_company_by_name(query)
        if match:
            return match
    # A shortened query matches loosely ("The Indian Hotels" finds "The Indian Wood
    # Products Company"), so only accept a result that contains every word we searched for.
    for query in shortened:
        match = company_search.resolve_company_by_name(query)
        if match and _contains_all_words(query, match["name"]):
            return match
    return None


def resolve_company(name: str) -> dict | None:
    """Best-effort screener.in match for a holding's name; None if unmatched or unreachable."""
    try:
        return _resolve(name)
    except ScreenerError:
        logger.warning("Could not resolve portfolio holding '%s' against screener.in", name, exc_info=True)
        return None


def match_holdings(holdings: list[dict]) -> tuple[list[dict], list[str]]:
    """Returns (usable holdings, names of skipped rows).

    Each usable holding has its numeric fields parsed and reconciled into
    floats plus resolved_name/resolved_url (or None). A row is skipped, not
    saved, when its figures are incomplete or contradict each other - that is
    what a half-visible row at the edge of a screenshot looks like, and saving
    it would put wrong numbers in the portfolio.

    A failed/unmatched company lookup never skips a row - the user still gets
    it, just without a hyperlink.
    """
    matched = []
    skipped = []
    for holding in holdings:
        amounts = reconcile_amounts(
            quantity=parse_number(holding.get("quantity")),
            avg_price=parse_number(holding.get("avg_price")),
            ltp=parse_number(holding.get("ltp")),
            invested_value=parse_number(holding.get("invested_value")),
            current_value=parse_number(holding.get("current_value")),
            pnl=parse_number(holding.get("pnl")),
        )
        consistent = amounts.pop("consistent")
        complete = (
            amounts["quantity"] is not None
            and amounts["invested_value"] is not None
            and amounts["current_value"] is not None
        )
        if not (complete and consistent):
            skipped.append(holding["company_name"])
            continue

        resolved_name = None
        resolved_url = None
        try:
            match = _resolve(holding["company_name"])
            if match:
                resolved_name = match["name"]
                resolved_url = match["url"]
        except ScreenerError:
            logger.warning(
                "Could not resolve portfolio holding '%s' against screener.in", holding["company_name"],
                exc_info=True,
            )

        matched.append(
            {
                "company_name": holding["company_name"],
                **amounts,
                "resolved_name": resolved_name,
                "resolved_url": resolved_url,
            }
        )
    return matched, skipped
