"""Reads a broker-app portfolio screenshot (Kite, Groww, Upstox, Angel One, ...)
into a list of structured holdings using an OpenAI vision model.

Broker apps don't share a layout, so there's no fixed column mapping to parse
against like the screener.in sector tables - a vision model reads the table
directly off the image instead.
"""

from __future__ import annotations

import base64
import json
import logging

from openai import OpenAI, OpenAIError

from app import config
from app.exceptions import PortfolioExtractionError

logger = logging.getLogger(__name__)

PROMPT = """You are reading a screenshot of a stock portfolio/holdings screen from an \
Indian broker app (examples: Zerodha Kite, Groww, Upstox, Angel One, or similar). \
Extract every holding row you can see into JSON.

Return ONLY a JSON object of this exact shape, nothing else:
{
  "ui_text": ["<every distinctive piece of app interface text visible OUTSIDE the holding rows, copied exactly: top header and index tickers, tab names, filter labels, bottom navigation labels, summary bar labels such as Day's P&L>"],
  "broker": "<name of the broker app this screenshot is from, e.g. Groww, Kite, Angel One, Upstox, or another app's name; null only if there are no clues at all>",
  "holdings": [
    {
      "company_name": "<the stock/company name or ticker exactly as shown>",
      "quantity": "<quantity/shares held, as shown, or null>",
      "avg_price": "<average buy price PER SHARE, only if the screen shows it explicitly, or null>",
      "ltp": "<last traded / current market price PER SHARE, only if the screen shows it explicitly, or null>",
      "invested_value": "<total amount invested in this holding (quantity x avg price), or null>",
      "current_value": "<total current market value of this holding, or null>",
      "pnl": "<total profit/loss in rupees, as shown (keep +/- sign), or null>"
    }
  ]
}

Identifying the broker: screenshots often show no logo, so use every clue (visible app name or logo, tab names, layout, colours). Known apps and their layouts:
- Groww ("Groww"): top tabs "Explore / Holdings / Positions / Orders", bottom bar "Stocks / F&O / Mutual Funds / Loans", a "Current (invested)" sort option. Per row: company name and "N shares" on the left; on the right a LARGE number = current_value and a number in (brackets) = invested_value (both are totals for the whole holding, not per-share prices). Groww shows NO per-share prices and NO P&L, so avg_price, ltp and pnl are null.
- Angel One ("Angel One"): header "Holdings | My Wealth", tabs "Overview / Equity / Mutual Funds / Investment", bottom bar "HOME / WATCHLIST / PORTFOLIO / ORDERS / ACCOUNT" (with HOME and ACCOUNT in capitals). Every row has "N x ATP" under the ticker. Per row: ticker on the left with "N x ATP ₹P" beneath it, where N = quantity and ATP (average traded price) = avg_price. The LARGE red/green number at top right, with a percentage in brackets, is the holding's TOTAL PROFIT/LOSS in rupees (pnl, keep the minus sign for red numbers). It is NOT the invested amount or current value. The line beneath it, "LTP ₹X (±y%)", gives ltp = X (ignore the % there, it is today's change). Angel One shows no invested_value or current_value, so those are null.
- Kite, Zerodha's app (report it as "Kite"): index tickers such as NIFTY 50 / NIFTY BANK at the top, tabs "Holdings (N) / Positions", a "Day's P&L" bar above the bottom navigation, bottom bar "Watchlist / Orders / Portfolio / IPO & Bids / <client id>". Per row: "Qty. N • Avg. P" at the top left (quantity and avg_price), the company name beneath it, then "Invested X" (invested_value, explicit). On the right: a P&L percentage at the top, the P&L amount in rupees in large text (pnl, keep the sign), and "LTP X (±y%)" (ltp = X; ignore the % there, it is today's change). Kite shows no current_value, so that is null. A row starting "Qty." is Kite, never Angel One.
- Anything else: report the app's own name if you can see or infer it.

Rules for amounts (these cause the most mistakes):
- invested_value and current_value are always POSITIVE totals. Never put a profit/loss figure into either of them; a figure with a minus sign or a +/- percentage beside it is a P&L.
- Only fill avg_price / ltp when the screen explicitly shows a per-share price (labels such as ATP, Avg., Avg. cost, LTP).
- Only fill pnl when the screen explicitly shows a profit/loss figure for that row (on Angel One it is always shown, so always fill it there, with all its decimals, exactly as printed). Never calculate one yourself.
- Never invent, round or compute any value. If a figure is not shown, use null.
- SKIP any row that is cut off by the top or bottom edge of the screen, or hidden behind a banner or the bottom bar, unless its name AND all of its figures are fully visible. A half-visible row must not appear in the output at all; it will be read from another screenshot.

Rules:
- One entry per distinct stock holding row. Skip headers, totals, summary cards, and non-stock rows (mutual funds, cash balance, etc. are fine to skip if clearly not an equity holding).
- Keep numbers as plain strings exactly as rendered (you may drop currency symbols and thousands separators, but keep the sign on P&L).
- If a field isn't visible for a row, use null for it - never guess.
- If you cannot find any holdings table in the image, return {"holdings": []}.
"""


def _client() -> OpenAI:
    if not config.OPENAI_API_KEY:
        raise PortfolioExtractionError(
            "OPENAI_API_KEY is not configured. Set it in backend/.env to enable portfolio uploads."
        )
    return OpenAI(api_key=config.OPENAI_API_KEY)


_BROKER_ALIASES = {
    "groww": "Groww",
    "angel one": "Angel One",
    "angel": "Angel One",
    "angel broking": "Angel One",
    "kite": "Kite",
    "zerodha": "Kite",
    "zerodha kite": "Kite",
    "upstox": "Upstox",
}


def normalize_broker(value) -> str | None:
    text = _clean(value)
    if not text or text.casefold() in {"unknown", "null", "none", "n/a", "other"}:
        return None
    return _BROKER_ALIASES.get(text.casefold(), text)


# Interface text that only one app shows. Reading text off a screenshot is far more
# reliable for a vision model than recognising an app from its look, so these rules
# decide the broker and the model's own guess is only a fallback.
_BROKER_SIGNATURES = [
    ("Angel One", ["my wealth", "angel"]),
    ("Groww", ["current (invested)", "groww"]),
    ("Kite", ["ipo & bids", "day's p&l", "nifty bank", "kite", "zerodha"]),
    ("Upstox", ["upstox"]),
]


def detect_broker(ui_text, model_guess) -> str | None:
    if isinstance(ui_text, str):
        ui_text = [ui_text]
    haystack = " | ".join(str(t) for t in (ui_text or [])).casefold().replace("’", "'")
    for broker, markers in _BROKER_SIGNATURES:
        if any(marker in haystack for marker in markers):
            return broker
    if "loans" in haystack and "f&o" in haystack:
        return "Groww"
    return normalize_broker(model_guess)


def extract_holdings_from_image(image_bytes: bytes, content_type: str) -> tuple[str | None, list[dict]]:
    """Returns (detected broker app name or None, holdings)."""
    client = _client()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded}"

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_VISION_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,
        )
    except OpenAIError as exc:
        logger.exception("OpenAI vision request failed while extracting a portfolio screenshot")
        raise PortfolioExtractionError(f"Could not read the screenshot: {exc}") from exc

    raw_content = response.choices[0].message.content
    try:
        parsed = json.loads(raw_content)
    except (TypeError, ValueError) as exc:
        logger.exception("OpenAI vision response wasn't valid JSON: %r", raw_content)
        raise PortfolioExtractionError("Could not parse the extracted portfolio data") from exc

    holdings = parsed.get("holdings")
    if not isinstance(holdings, list):
        raise PortfolioExtractionError("Extracted response didn't contain a holdings list")

    cleaned = []
    for item in holdings:
        name = (item or {}).get("company_name")
        if not name or not str(name).strip():
            continue
        cleaned.append(
            {
                "company_name": str(name).strip(),
                "quantity": _clean(item.get("quantity")),
                "avg_price": _clean(item.get("avg_price")),
                "ltp": _clean(item.get("ltp")),
                "invested_value": _clean(item.get("invested_value")),
                "current_value": _clean(item.get("current_value")),
                "pnl": _clean(item.get("pnl")),
            }
        )
    broker = detect_broker(parsed.get("ui_text"), parsed.get("broker"))
    logger.info("Detected broker %r (model said %r)", broker, parsed.get("broker"))
    return broker, cleaned


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
