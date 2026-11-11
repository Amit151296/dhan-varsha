from app.services.portfolio.amounts import reconcile_amounts


def test_angel_one_row_derives_invested_from_current_minus_pnl():
    # AURIONPRO on Angel One: "75 x ATP 1,051.50", P&L -35,456.09, LTP 578.75
    result = reconcile_amounts(
        quantity=75, avg_price=1051.50, ltp=578.75, invested_value=None, current_value=None, pnl=-35456.09
    )
    assert result["current_value"] == 43406.25
    assert result["invested_value"] == 78862.34
    assert result["pnl"] == -35456.09
    assert result["consistent"]


def test_groww_row_uses_totals_and_derives_per_share_prices():
    result = reconcile_amounts(
        quantity=614, avg_price=None, ltp=None, invested_value=64242.82, current_value=77701.70, pnl=None
    )
    assert result["pnl"] == 13458.88
    assert round(result["avg_price"], 2) == 104.63
    assert round(result["ltp"], 2) == 126.55
    assert result["consistent"]  # no P&L on screen is not a contradiction


def test_negative_figure_in_invested_field_is_treated_as_a_misplaced_pnl():
    # Regression: Angel One's big red number (a P&L) was read into invested_value.
    result = reconcile_amounts(
        quantity=75, avg_price=1051.50, ltp=578.75, invested_value=-35456.09, current_value=None, pnl=None
    )
    assert result["invested_value"] == 78862.5
    assert result["invested_value"] > 0


def test_pnl_that_contradicts_the_other_figures_is_flagged_inconsistent():
    # A half-visible row: model guessed qty/ATP/LTP, but the P&L printed on screen disagrees.
    result = reconcile_amounts(
        quantity=100, avg_price=2341.31, ltp=1700.0, invested_value=None, current_value=None, pnl=-23495.91
    )
    assert not result["consistent"]


def test_row_with_only_a_pnl_is_incomplete():
    result = reconcile_amounts(
        quantity=None, avg_price=None, ltp=None, invested_value=None, current_value=None, pnl=1048.97
    )
    assert result["quantity"] is None
    assert result["invested_value"] is None
    assert result["current_value"] is None
