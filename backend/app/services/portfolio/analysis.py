"""Breaks a user's portfolio down by broker and by sector."""

from __future__ import annotations

from collections import defaultdict

from app.services.company.analyzer import canonical_company_key

NO_BROKER_LABEL = "Manual / not specified"
UNCLASSIFIED_LABEL = "Unclassified"


def holding_amounts(h) -> tuple[float, float, float]:
    """(invested, current value, P&L) for one holding, from whatever figures it has."""
    if h.invested_value is not None:
        invested = h.invested_value
    elif h.quantity and h.avg_price:
        invested = h.quantity * h.avg_price
    else:
        invested = 0.0

    if h.current_value is not None:
        current = h.current_value
    elif h.quantity and h.ltp:
        current = h.quantity * h.ltp
    else:
        current = 0.0

    pnl = h.pnl if h.pnl is not None else current - invested
    return invested, current, pnl


def _company_identity(h) -> str:
    if h.resolved_url:
        return canonical_company_key(h.resolved_url).casefold()
    return "name:" + h.raw_name.strip().casefold()


def _breakdown(groups: dict[str, list], total_invested: float) -> list[dict]:
    rows = []
    for label, holdings in groups.items():
        invested = current = pnl = 0.0
        for h in holdings:
            i, c, p = holding_amounts(h)
            invested += i
            current += c
            pnl += p
        rows.append(
            {
                "label": label,
                "company_count": len({_company_identity(h) for h in holdings}),
                "invested": round(invested, 2),
                "current_value": round(current, 2),
                "pnl": round(pnl, 2),
                "share_of_invested": round(invested / total_invested * 100, 1) if total_invested else 0.0,
                "companies": sorted({h.raw_name for h in holdings}),
            }
        )
    rows.sort(key=lambda r: r["invested"], reverse=True)
    return rows


def analyse_portfolio(holdings: list, sectors: dict[str, tuple[str, str | None]]) -> dict:
    """`sectors` maps canonical company URL -> (sector, industry)."""
    total_invested = sum(holding_amounts(h)[0] for h in holdings)

    by_broker: dict[str, list] = defaultdict(list)
    by_sector: dict[str, list] = defaultdict(list)
    for h in holdings:
        by_broker[h.broker or NO_BROKER_LABEL].append(h)
        sector = None
        if h.resolved_url:
            sector = (sectors.get(canonical_company_key(h.resolved_url)) or (None, None))[0]
        by_sector[sector or UNCLASSIFIED_LABEL].append(h)

    sector_rows = _breakdown(by_sector, total_invested)
    # Keep "Unclassified" last regardless of how much is in it.
    sector_rows.sort(key=lambda r: r["label"] == UNCLASSIFIED_LABEL)

    return {
        "total_invested": round(total_invested, 2),
        "company_count": len({_company_identity(h) for h in holdings}),
        "by_broker": _breakdown(by_broker, total_invested),
        "by_sector": sector_rows,
    }
