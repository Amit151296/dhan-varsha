"""Turns the raw figures read off a broker screenshot into one consistent set
(invested, current value, P&L, per-share prices).

Apps show different subsets: Groww gives current + invested totals, Angel One
gives qty, average price, LTP and the total P&L. A vision model can also put a
figure in the wrong field (e.g. a P&L in "invested"), so every figure is
sanity-checked against the others before it's used.
"""

from __future__ import annotations


def _positive(value: float | None) -> float | None:
    # Invested and current value of a holding are never zero or negative; a
    # negative number here is a P&L that landed in the wrong field.
    return value if value is not None and value > 0 else None


def reconcile_amounts(
    quantity: float | None,
    avg_price: float | None,
    ltp: float | None,
    invested_value: float | None,
    current_value: float | None,
    pnl: float | None,
) -> dict:
    invested_value = _positive(invested_value)
    current_value = _positive(current_value)
    avg_price = _positive(avg_price)
    ltp = _positive(ltp)
    quantity = _positive(quantity)

    if current_value is None and quantity and ltp:
        current_value = round(quantity * ltp, 2)

    # A P&L read off the screen is exact (average prices are rounded to paise),
    # but only trust it when it agrees with qty x (LTP - avg price), since models
    # sometimes invent one for screens that don't show it.
    pnl_given = pnl is not None
    pnl_plausible = True
    if pnl_given and quantity and ltp and avg_price:
        tolerance = quantity * 0.01 + 1
        pnl_plausible = abs(pnl - quantity * (ltp - avg_price)) <= tolerance

    if invested_value is None:
        if pnl_given and pnl_plausible and current_value is not None:
            invested_value = round(current_value - pnl, 2)
        elif quantity and avg_price:
            invested_value = round(quantity * avg_price, 2)

    if avg_price is None and quantity and invested_value:
        avg_price = invested_value / quantity
    if ltp is None and quantity and current_value:
        ltp = current_value / quantity

    if current_value is not None and invested_value is not None:
        pnl = round(current_value - invested_value, 2)
    elif not pnl_plausible:
        pnl = None

    return {
        "quantity": quantity,
        "avg_price": avg_price,
        "ltp": ltp,
        "invested_value": invested_value,
        "current_value": current_value,
        "pnl": pnl,
        # False when the figures contradict each other (typically a half-visible
        # row the model filled in by guessing) - the row shouldn't be saved.
        "consistent": pnl_plausible,
    }
