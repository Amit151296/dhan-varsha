"""Buckets holdings by cumulative share of the portfolio's invested amount.

Tells a user how concentrated their portfolio is: how few companies make up
most of the money put in, versus how many thinly-held names make up the tail.
"""

from __future__ import annotations

from app.services.portfolio.analysis import _company_identity, holding_amounts


def _tier_labels(cutoffs: tuple[float, float]) -> tuple[str, str, str]:
    first, second = cutoffs
    return (
        f"Top holdings (first {first:g}%)",
        f"Core holdings (next {second - first:g}%)",
        f"Long tail (last {100 - second:g}%)",
    )


def concentration_breakdown(holdings: list, cutoffs: tuple[float, float] = (30.0, 90.0)) -> list[dict]:
    """Rank companies by invested amount (largest first) and bucket by cumulative % of the total.

    A stock held at several brokers counts once, with its amounts added together. A company's
    tier is set by the cumulative share *before* it is added, so the fewest companies needed to
    reach cutoffs[0] are tier 0 (even if one position alone exceeds it), the next ones up to
    cutoffs[1] are tier 1, and the rest are the long tail.
    """
    by_company: dict[str, dict] = {}
    for h in holdings:
        invested, current, pnl = holding_amounts(h)
        entry = by_company.setdefault(
            _company_identity(h), {"name": h.raw_name, "invested": 0.0, "current": 0.0, "pnl": 0.0}
        )
        entry["invested"] += invested
        entry["current"] += current
        entry["pnl"] += pnl

    total_invested = sum(c["invested"] for c in by_company.values())
    ordered = sorted(by_company.values(), key=lambda c: c["invested"], reverse=True)

    tiers: list[list[dict]] = [[], [], []]
    cumulative = 0.0
    for company in ordered:
        share_before = (cumulative / total_invested * 100) if total_invested else 0.0
        if share_before < cutoffs[0]:
            tier_index = 0
        elif share_before < cutoffs[1]:
            tier_index = 1
        else:
            tier_index = 2
        tiers[tier_index].append(company)
        cumulative += company["invested"]

    rows = []
    for label, members in zip(_tier_labels(cutoffs), tiers):
        invested = sum(c["invested"] for c in members)
        rows.append(
            {
                "label": label,
                "company_count": len(members),
                "invested": round(invested, 2),
                "current_value": round(sum(c["current"] for c in members), 2),
                "pnl": round(sum(c["pnl"] for c in members), 2),
                "share_of_invested": round(invested / total_invested * 100, 1) if total_invested else 0.0,
                # Largest first, each with its own share of the whole portfolio.
                "companies": [
                    f"{c['name']} ({c['invested'] / total_invested * 100:.1f}%)" if total_invested else c["name"]
                    for c in members
                ],
            }
        )
    return rows
