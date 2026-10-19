import pandas as pd

from app.services.company import shareholding


def test_clean_shareholding_table_transposes_and_strips_percent():
    raw = pd.DataFrame({
        "Unnamed: 0": ["Promoters", "FIIs", "DIIs", "Government", "Public", "No. of Shareholders"],
        "Sep 2024": ["72.30%", "12.10%", "8.50%", "0.00%", "7.10%", "185000"],
        "Dec 2024": ["72.30%", "13.00%", "8.00%", "0.00%", "6.70%", "190500"],
    })

    cleaned = shareholding.clean_shareholding_table(raw)

    assert list(cleaned.index) == ["Sep 2024", "Dec 2024"]
    assert cleaned.loc["Sep 2024", "Promoters"] == 72.3
    assert cleaned.loc["Dec 2024", "No. of Shareholders"] == 190500.0


def test_clean_shareholding_table_strips_screener_column_noise():
    # screener.in's real column labels carry a non-breaking space + "+" suffix
    # ("Promoters\xa0+") marking them as expandable - not part of the name.
    raw = pd.DataFrame({
        "Unnamed: 0": ["Promoters\xa0+", "FIIs\xa0+", "No. of Shareholders"],
        "Sep 2024": ["72.30%", "12.10%", "185000"],
    })

    cleaned = shareholding.clean_shareholding_table(raw)

    assert list(cleaned.columns) == ["Promoters", "FIIs", "No. of Shareholders"]
