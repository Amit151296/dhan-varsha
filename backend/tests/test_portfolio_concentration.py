from types import SimpleNamespace

from app.services.portfolio.concentration import concentration_breakdown


def _holding(name, value, current=None):
    return SimpleNamespace(
        raw_name=name,
        resolved_url=f"/company/{name}/",
        invested_value=value,
        current_value=value if current is None else current,
        pnl=0.0,
        quantity=None,
        avg_price=None,
        ltp=None,
    )


def _names(row):
    return [c.split(" (")[0] for c in row["companies"]]


def test_tiers_split_by_cumulative_share_largest_first():
    holdings = [_holding("D", 5), _holding("B", 30), _holding("A", 40), _holding("E", 5), _holding("C", 20)]
    top, core, tail = concentration_breakdown(holdings)

    assert _names(top) == ["A"]
    assert _names(core) == ["B", "C"]  # largest first
    assert sorted(_names(tail)) == ["D", "E"]
    assert tail["share_of_invested"] == 10.0
    assert top["companies"] == ["A (40.0%)"]


def test_labels_show_the_bands():
    top, core, tail = concentration_breakdown([_holding("A", 1)])
    assert (top["label"], core["label"], tail["label"]) == (
        "Top holdings (first 30%)",
        "Core holdings (next 60%)",
        "Long tail (last 10%)",
    )


def test_ranked_by_invested_not_current_value():
    holdings = [_holding("A", 90, current=10), _holding("B", 10, current=90)]
    top, _, _ = concentration_breakdown(holdings)
    assert _names(top) == ["A"]


def test_same_company_at_two_brokers_counts_once():
    holdings = [_holding("A", 30), _holding("A", 30), _holding("B", 40)]
    rows = concentration_breakdown(holdings)
    assert sum(r["company_count"] for r in rows) == 2


def test_tier_shares_add_up_to_100():
    holdings = [_holding(name, value) for name, value in [("A", 25), ("B", 25), ("C", 25), ("D", 15), ("E", 10)]]
    rows = concentration_breakdown(holdings)
    assert round(sum(r["share_of_invested"] for r in rows), 1) == 100.0
    assert sum(r["company_count"] for r in rows) == 5


def test_empty_portfolio():
    rows = concentration_breakdown([])
    assert [r["company_count"] for r in rows] == [0, 0, 0]
