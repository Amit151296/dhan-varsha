from app.services.screener import scoring


def test_avg_sales_bands():
    assert scoring.score_row({"Avg Sales": 2})["Avg Sales"]["background"] == scoring.ZONE_HEX["red"]
    assert scoring.score_row({"Avg Sales": 20})["Avg Sales"]["background"] == scoring.ZONE_HEX["blue"]


def test_avg_sales_missing_sentinel_flagged_yellow():
    highlight = scoring.score_row({"Avg Sales": 999})["Avg Sales"]
    assert highlight["background"] == scoring.ZONE_HEX["yellow"]


def test_pe_zone_is_inverted_low_is_good():
    low_pe = scoring.score_row({"P/E": 10})["P/E"]
    high_pe = scoring.score_row({"P/E": 90})["P/E"]
    assert low_pe["background"] == scoring.ZONE_HEX["purple"]
    assert low_pe["color"] == scoring.TONE_TEXT["dark"]
    assert high_pe["background"] == scoring.ZONE_HEX["red"]


def test_roce_uses_its_own_thresholds_not_roe():
    # At 16, ROE%'s bands call it "light-green" (15-25) while ROCE%'s own
    # bands call it "orange" (7-17) - this would be silently wrong if ROCE%
    # reused ROE%'s thresholds, which is what the original notebook did.
    roce = scoring.score_row({"ROCE%": 16})["ROCE%"]
    roe = scoring.score_row({"ROE%": 16})["ROE%"]
    assert roce["background"] == scoring.ZONE_HEX["orange"]
    assert roe["background"] == scoring.ZONE_HEX["light-green"]


def test_sign_zone_handles_zero_as_neutral():
    assert scoring.score_row({"Prom ch%": 0}) == {}


def test_pledged_zone_dark_above_threshold():
    moderate = scoring.score_row({"Pledged%": 5})["Pledged%"]
    heavy = scoring.score_row({"Pledged%": 20})["Pledged%"]
    assert moderate["color"] == scoring.TONE_TEXT["light"]
    assert heavy["color"] == scoring.TONE_TEXT["dark"]


def test_qoq_extreme_drop_is_dark_red():
    highlight = scoring.score_row({"QoQ Sales var%": -25})["QoQ Sales var%"]
    assert highlight["background"] == scoring.ZONE_HEX["red"]
    assert highlight["color"] == scoring.TONE_TEXT["dark"]


def test_unscored_columns_are_ignored():
    assert scoring.score_row({"CMP": 123.4}) == {}
