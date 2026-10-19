"""Cleans a company's quarterly/yearly shareholding pattern table.

Unlike the P&L tables, screener.in already labels these columns sensibly
(Promoters, FIIs, DIIs, Government, Public, No. of Shareholders), so no
name-based remapping is needed - just transpose and type the values.
"""

from __future__ import annotations

import re

import pandas as pd


def _clean_label(label) -> str:
    text = str(label).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip("+").strip()


def clean_shareholding_table(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={raw.columns[0]: "holding"})
    transposed = df.set_index("holding").T
    transposed.columns = [_clean_label(column) for column in transposed.columns]
    transposed = transposed.replace("%", "", regex=True)

    for column in transposed.columns:
        transposed[column] = pd.to_numeric(transposed[column], errors="coerce")

    return transposed
