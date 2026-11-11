"""Parses the loosely-formatted numeric strings a vision model reads off a
broker screenshot (currency symbols, thousands separators, parens for
negatives, a trailing/leading +/- sign) into plain floats.
"""

from __future__ import annotations

import re

_NUMERIC_CHARS = re.compile(r"[^0-9.\-]")


def parse_number(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace(",", "")
    text = _NUMERIC_CHARS.sub("", text)
    if not text or text in {"-", "."}:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    return -abs(number) if negative else number
