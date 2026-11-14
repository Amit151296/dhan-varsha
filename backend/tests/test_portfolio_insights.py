import re
from types import SimpleNamespace as NS

from app.services.portfolio.insights import build_signals, compact_sheet, zone_label


def _hl(zone, dark=False):
    return {"zone": zone, "background": "#000000", "color": "#FFFFFF" if dark else "#000000"}


def _row(name, metrics, highlights=None):
    return NS(name=name, metrics=metrics, highlights=highlights or {})


def _titles(items):
    return {i["title"]: i["companies"] for i in items}


def test_zone_label_distinguishes_white_text():
    assert zone_label(_hl("purple", dark=True)) == "purple-white"
    assert zone_label(_hl("purple")) == "purple"
    assert zone_label(_hl("red", dark=True)) == "dark-red"
    assert zone_label(None) is None


def test_strengths_and_risks_follow_the_rules():
    good = _row(
        "GOOD",
        {"Avg Sales": 30, "Avg profit": 50, "P/E": 12, "Prom ch%": 1, "FII ch%": 2, "DII ch%": 0, "Pledged%": 0, "Debt/Eq": 0.1},
        {"Avg Sales": _hl("purple"), "Avg profit": _hl("purple", True), "P/E": _hl("purple", True)},
    )
    bad = _row(
        "BAD",
        {"Avg Sales": 3, "P/E": 90, "Prom ch%": -2, "FII ch%": -1, "DII ch%": 1, "Pledged%": 15, "Debt/Eq": 0.9, "NP Ann": -5},
        {"Avg Sales": _hl("red"), "P/E": _hl("red")},
    )
    signals = build_signals([good, bad])
    strengths, risks = _titles(signals["strengths"]), _titles(signals["risks"])

    assert [re.split(r" \(|:", c)[0] for c in strengths["Strong sales growth"]] == ["GOOD"]
    assert [re.split(r" \(|:", c)[0] for c in strengths["Strong profit growth"]] == ["GOOD"]
    assert [re.split(r" \(|:", c)[0] for c in strengths["Low P/E valuation"]] == ["GOOD"]
    assert [re.split(r" \(|:", c)[0] for c in strengths["Promoters, FIIs and DIIs net buying"]] == ["GOOD"]
    assert [re.split(r" \(|:", c)[0] for c in risks["Promoter shares pledged"]] == ["BAD"]
    assert [re.split(r" \(|:", c)[0] for c in risks["High debt"]] == ["BAD"]
    assert [re.split(r" \(|:", c)[0] for c in risks["Promoters, FIIs and DIIs net selling"]] == ["BAD"]
    assert [re.split(r" \(|:", c)[0] for c in risks["Loss-making"]] == ["BAD"]


def test_missing_data_is_never_counted():
    row = _row(
        "THIN",
        {"Avg Sales": 999, "Avg profit": 999, "P/E": 999, "Prom ch%": 999, "FII ch%": 999, "DII ch%": 999, "Debt/Eq": 999, "Pledged%": 999},
        {"Avg Sales": _hl("yellow"), "P/E": _hl("red")},
    )
    signals = build_signals([row])
    assert "High debt" not in _titles(signals["risks"])
    assert "Promoter shares pledged" not in _titles(signals["risks"])
    assert "data_gaps" not in signals
    assert compact_sheet([row])[0]["metrics"]["Debt/Eq"] == "MISSING"


def test_standouts_need_two_strengths_and_no_serious_risk():
    strong = _row("STRONG", {"Avg Sales": 30, "Avg profit": 50, "Debt/Eq": 0.1}, {"Avg Sales": _hl("purple"), "Avg profit": _hl("purple")})
    indebted = _row("INDEBTED", {"Avg Sales": 30, "Avg profit": 50, "Debt/Eq": 2}, {"Avg Sales": _hl("purple"), "Avg profit": _hl("purple")})
    single = _row("SINGLE", {"Avg Sales": 30}, {"Avg Sales": _hl("purple")})
    standouts = build_signals([strong, indebted, single])["standouts"]
    assert len(standouts) == 1 and standouts[0].startswith("STRONG - ")


def test_net_buying_is_listed_first_and_replaces_ai_version():
    from app.services.portfolio.insights import BUYING_TITLE, _pin_holding_change, build_signals

    buyer = _row("DIXON", {"Prom ch%": 0, "FII ch%": 1, "DII ch%": 2, "Avg Sales": 30}, {"Avg Sales": _hl("purple")})
    signals = build_signals([buyer])
    assert signals["strengths"][0]["title"] == BUYING_TITLE
    assert signals["strengths"][0]["companies"][0].startswith("DIXON: net change +3, positive")

    ai = [{"title": "Institutions are buying (FII/DII)", "detail": "", "companies": ["X"]}, {"title": "Strong growth", "detail": "", "companies": ["Y"]}]
    merged = _pin_holding_change(ai, signals["strengths"], BUYING_TITLE)
    assert [i["title"] for i in merged] == [BUYING_TITLE, "Strong growth"]


def test_promoter_only_change_still_counts_and_states_positive():
    from app.services.portfolio.insights import _state_net_change, build_signals

    csl = _row("CSL Finance", {"Prom ch%": 1, "FII ch%": 999, "DII ch%": 999})
    signals = build_signals([csl])
    assert signals["strengths"][0]["companies"] == ["CSL Finance: net change +1, positive (promoter +1)"]

    seller = _row("SELLER", {"Prom ch%": -2, "FII ch%": 0, "DII ch%": 0})
    assert _state_net_change(["CSL Finance - low P/E", "SELLER - growth"], [csl, seller]) == [
        "CSL Finance - low P/E; net holding change +1 (positive)"
    ]


def test_strong_last_quarter_needs_both_sales_and_profit_good():
    both = _row(
        "BOTH",
        {"QoQ Sales var%": 25, "QoQ Profits var%": 40},
        {"QoQ Sales var%": _hl("blue"), "QoQ Profits var%": _hl("purple")},
    )
    one = _row(
        "ONE",
        {"QoQ Sales var%": 25, "QoQ Profits var%": 5},
        {"QoQ Sales var%": _hl("blue"), "QoQ Profits var%": _hl("orange")},
    )
    missing = _row(
        "MISS",
        {"QoQ Sales var%": 25, "QoQ Profits var%": 999},
        {"QoQ Sales var%": _hl("blue"), "QoQ Profits var%": _hl("yellow")},
    )
    strengths = _titles(build_signals([both, one, missing])["strengths"])
    assert strengths["Strong last quarter"] == ["BOTH (sales +25%, profit +40% vs last quarter)"]


def test_light_green_quarter_counts_but_orange_does_not():
    green = _row(
        "SILVER",
        {"QoQ Sales var%": 12, "QoQ Profits var%": 15},
        {"QoQ Sales var%": _hl("light-green"), "QoQ Profits var%": _hl("light-green")},
    )
    orange = _row(
        "SLOW",
        {"QoQ Sales var%": 12, "QoQ Profits var%": 5},
        {"QoQ Sales var%": _hl("light-green"), "QoQ Profits var%": _hl("orange")},
    )
    strengths = _titles(build_signals([green, orange])["strengths"])
    assert [c.split(" (")[0] for c in strengths["Strong last quarter"]] == ["SILVER"]


def test_weak_last_quarter_flags_any_red_figure():
    one_red = _row(
        "DIP",
        {"QoQ Sales var%": 8, "QoQ Profits var%": -12},
        {"QoQ Sales var%": _hl("orange"), "QoQ Profits var%": _hl("red", True)},
    )
    fine = _row(
        "OK",
        {"QoQ Sales var%": 8, "QoQ Profits var%": 6},
        {"QoQ Sales var%": _hl("orange"), "QoQ Profits var%": _hl("orange")},
    )
    risks = _titles(build_signals([one_red, fine])["risks"])
    assert risks["Weak last quarter"] == ["DIP (sales +8%, profit -12% (red) vs last quarter)"]
