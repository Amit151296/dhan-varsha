from app.services.portfolio.extractor import detect_broker


def test_kite_screen_is_recognised_from_its_interface_text_even_if_the_model_guesses_wrong():
    # Regression: a Kite screenshot was labelled "Angel One" because both have a
    # Watchlist / Orders / Portfolio bottom bar.
    ui_text = ["NIFTY 50", "NIFTY BANK", "Holdings 9", "Positions", "Equity", "Family", "Analytics",
               "Day's P&L", "Watchlist", "Orders", "Portfolio", "IPO & Bids"]
    assert detect_broker(ui_text, "Angel One") == "Kite"


def test_angel_one_screen_is_recognised():
    ui_text = ["Holdings", "My Wealth", "Overview", "Equity", "Mutual Funds", "Investment",
               "HOME", "WATCHLIST", "PORTFOLIO", "ORDERS", "ACCOUNT"]
    assert detect_broker(ui_text, "Kite") == "Angel One"


def test_groww_screen_is_recognised():
    assert detect_broker(["Explore", "Holdings", "Positions", "Orders", "Sort", "Current (invested)"], None) == "Groww"
    assert detect_broker(["Stocks", "F&O", "Mutual Funds", "Loans"], None) == "Groww"


def test_unknown_screen_falls_back_to_the_models_guess_and_to_none():
    assert detect_broker(["Some", "Other", "App"], "Zerodha") == "Kite"
    assert detect_broker(["Some", "Other", "App"], "Fyers") == "Fyers"
    assert detect_broker([], None) is None
