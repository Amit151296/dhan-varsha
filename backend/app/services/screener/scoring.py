"""Classifies metric values into colour "zones", ported from the notebook's
pandas Styler functions (color_avgSale, color_PE, color_QoQ, etc).

The backend only returns a semantic zone + resolved colour per cell; it does
not know about CSS classes or Excel fills, so the same classification feeds
both the web table and the Excel export.

Note: the original notebook applied the ROE colour thresholds to the ROCE%
column too (its dedicated color_ROCE function was defined but never used).
That looked like a copy-paste bug, so ROCE% here uses its own thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ZONE_HEX = {
    "red": "#FF0000",
    "orange": "#FFA500",
    "light-green": "#90EE90",
    "blue": "#0000FF",
    "purple": "#800080",
    "yellow": "#FFFF00",
    "green": "#008000",
}
TONE_TEXT = {"light": "#000000", "dark": "#FFFFFF"}


@dataclass(frozen=True)
class Zone:
    name: str
    tone: str = "light"  # "dark" = white text on this zone's background


def _resolve(zone: Zone | None) -> dict | None:
    if zone is None:
        return None
    return {"zone": zone.name, "background": ZONE_HEX[zone.name], "color": TONE_TEXT[zone.tone]}


def _avg_sales_zone(x: float) -> Zone | None:
    if x < 4:
        return Zone("red")
    if x < 9:
        return Zone("orange")
    if x < 18:
        return Zone("light-green")
    if x < 28:
        return Zone("blue")
    if x < 40:
        return Zone("purple")
    if x < 100:
        return Zone("purple", "dark")
    return Zone("yellow")


def _avg_profit_zone(x: float) -> Zone | None:
    if x < 6:
        return Zone("red")
    if x < 15:
        return Zone("orange")
    if x < 24:
        return Zone("light-green")
    if x < 34:
        return Zone("blue")
    if x < 45:
        return Zone("purple")
    if x < 100:
        return Zone("purple", "dark")
    return Zone("yellow")


def _avg_return_zone(x: float) -> Zone | None:
    if x < 6:
        return Zone("red")
    if x < 12:
        return Zone("orange")
    if x < 22:
        return Zone("light-green")
    if x < 33:
        return Zone("blue")
    if x < 44:
        return Zone("purple")
    if x < 100:
        return Zone("purple", "dark")
    return Zone("yellow")


def _pe_zone(x: float) -> Zone | None:
    if x < 15:
        return Zone("purple", "dark")
    if x < 28:
        return Zone("purple")
    if x < 44:
        return Zone("blue")
    if x < 60:
        return Zone("light-green")
    if x < 80:
        return Zone("orange")
    return Zone("red")


def _roe_zone(x: float) -> Zone | None:
    if x < 5:
        return Zone("red")
    if x < 15:
        return Zone("orange")
    if x < 25:
        return Zone("light-green")
    if x < 35:
        return Zone("blue")
    if x < 45:
        return Zone("purple")
    if x < 100:
        return Zone("purple", "dark")
    return Zone("yellow")


def _roce_zone(x: float) -> Zone | None:
    if x < 7:
        return Zone("red")
    if x < 17:
        return Zone("orange")
    if x < 28:
        return Zone("light-green")
    if x < 38:
        return Zone("blue")
    if x < 48:
        return Zone("purple")
    if x < 100:
        return Zone("purple", "dark")
    return Zone("yellow")


def _sign_zone(x: float) -> Zone | None:
    if x < 0:
        return Zone("red")
    if x > 0:
        return Zone("light-green")
    return None


def _pledged_zone(x: float) -> Zone | None:
    if x <= 0:
        return None
    if x < 12:
        return Zone("red")
    return Zone("red", "dark")


def _div_yld_zone(x: float) -> Zone | None:
    if 2 <= x < 4:
        return Zone("light-green")
    if x >= 4:
        return Zone("green")
    return None


def _down_52_zone(x: float) -> Zone | None:
    if 10 < x < 20:
        return Zone("light-green")
    if 20 <= x < 30:
        return Zone("green")
    if 30 <= x < 40:
        return Zone("blue")
    if 40 <= x < 55:
        return Zone("blue", "dark")
    return None


def _qoq_zone(x: float) -> Zone | None:
    if x < -10:
        return Zone("red", "dark")
    if x < 0:
        return Zone("red")
    if x == 0:
        return None  # flat QoQ is neutral, same as the sign-based metrics above
    if x <= 10:
        return Zone("orange")
    if x < 20:
        return Zone("light-green")
    if x < 30:
        return Zone("blue")
    if x < 40:
        return Zone("purple")
    return Zone("purple", "dark")


SCORERS: dict[str, Callable[[float], Zone | None]] = {
    "Avg Sales": _avg_sales_zone,
    "Avg profit": _avg_profit_zone,
    "Avg Return": _avg_return_zone,
    "P/E": _pe_zone,
    "ROE%": _roe_zone,
    "ROCE%": _roce_zone,
    "Prom ch%": _sign_zone,
    "FII ch%": _sign_zone,
    "DII ch%": _sign_zone,
    "Pledged%": _pledged_zone,
    "Div Yld%": _div_yld_zone,
    "Down 52%": _down_52_zone,
    "QoQ Sales var%": _qoq_zone,
    "QoQ Profits var%": _qoq_zone,
}


def score_row(metrics: dict) -> dict:
    """Return {column: {"background": "#hex", "color": "#hex"}} for every scored metric."""
    highlights = {}
    for column, scorer in SCORERS.items():
        value = metrics.get(column)
        if value is None:
            continue
        resolved = _resolve(scorer(float(value)))
        if resolved is not None:
            highlights[column] = resolved
    return highlights
