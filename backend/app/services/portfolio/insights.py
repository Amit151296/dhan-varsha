"""Portfolio strength and risk, read off the colour-coded company metrics table.

Two layers on purpose:

* `build_signals` applies the plain rules (purple growth, pledged shares, debt above 0.5, falling
  institutional holding, ...) in code, so the lists of companies are exact.
* `generate_insights` hands the same sheet, the colour legend and those signals to an OpenAI model
  to write the observations. If OpenAI is unavailable the rule-based lists are returned alone.

Colour meaning (from services/screener/scoring.py): red is weak/risky, purple is the best zone,
purple with white text is the very best, yellow means the data is missing. Missing values are
stored as the placeholder 999 and must never be treated as real numbers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from openai import OpenAI, OpenAIError

from app import config
from app.services.screener.analyzer import MISSING_VALUE_SENTINEL

logger = logging.getLogger(__name__)

PROMPT_VERSION = 7
DEBT_EQUITY_LIMIT = 0.5
LOW_PROMOTER_HOLDING = 25.0

BUYING_TITLE = "Promoters, FIIs and DIIs net buying"
SELLING_TITLE = "Promoters, FIIs and DIIs net selling"
QUARTER_TITLE = "Strong last quarter"
WEAK_QUARTER_TITLE = "Weak last quarter"
_QUARTER_TITLE = re.compile(r"quarter|qoq", re.IGNORECASE)
_GOOD_QOQ_ZONES = ("light-green", "green", "blue", "purple", "purple-white")
# AI points about holding changes are replaced by the exact rule-based ones above.
_HOLDING_CHANGE_TITLE = re.compile(r"net (buying|selling)|\bFIIs?\b|\bDIIs?\b|institutional", re.IGNORECASE)

# Columns sent to the model: enough to judge growth, valuation, balance sheet and ownership.
KEY_COLUMNS = [
    "MCap", "Avg Sales", "Avg profit", "Avg Return", "P/E", "ROE%", "ROCE%", "Debt/Eq",
    "Pledged%", "Prom ch%", "FII ch%", "DII ch%", "Prom Hold%", "QoQ Sales var%",
    "QoQ Profits var%", "CashFlow", "NP Ann", "Div Yld%",
]

LEGEND = """Colour legend (the colour is computed from the number):
- red = weak or risky; dark-red (red with white text) = severe
- orange = below average; light-green = acceptable; blue = good
- purple = very good (best zone); purple-white (purple with white text) = excellent, the very best
- yellow = DATA MISSING. Such a cell carries the placeholder 999 (shown here as MISSING). It is not a real number: never count it as strength or risk and never average it in.
- P/E: purple means a LOW P/E (cheap), red means very expensive.
- Prom ch% / FII ch% / DII ch%: light-green = holding increased, red = holding decreased.
- Pledged%: any red means promoter shares are pledged.
- A column with no colour has no score; use the number itself."""

RULES = """Strengths to look for:
- Avg Sales in a purple or purple-white zone; Avg profit in a purple or purple-white zone.
- Low P/E (purple zones).
- Net change in holdings (Prom ch% + FII ch% + DII ch%) above zero: promoters, FIIs and DIIs are adding.
- Strong last quarter: both QoQ Sales var% and QoQ Profits var% in a light-green, green, blue, purple or purple-white zone (orange and red do not count).
Risks to look for:
- Any promoter pledge (Pledged% above 0).
- Debt/Eq above 0.5.
- Net change in holdings below zero: promoters, FIIs and DIIs are selling.
Also look for, and add your own judgement on: weak ROE/ROCE (red), weak last quarter (QoQ sales or profit in red), loss-making companies (NP Ann below 0), negative free cash flow (CashFlow below 0), very low promoter holding, very expensive valuation (P/E red)."""


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, (int, float)) and value >= MISSING_VALUE_SENTINEL)


def zone_label(highlight) -> str | None:
    """'purple-white' for purple with white text, 'dark-red' for red with white text, else the zone name."""
    if not highlight:
        return None
    zone = highlight["zone"] if isinstance(highlight, dict) else highlight.zone
    color = (highlight["color"] if isinstance(highlight, dict) else highlight.color).upper()
    dark = color == "#FFFFFF"
    if zone == "purple" and dark:
        return "purple-white"
    if zone == "red" and dark:
        return "dark-red"
    return zone


def compact_sheet(rows: list) -> list[dict]:
    """The table as the model sees it: per company, `value (zone)` for each key column."""
    sheet = []
    for row in rows:
        cells = {}
        for column in KEY_COLUMNS:
            if column not in row.metrics:
                continue
            value = row.metrics[column]
            if _is_missing(value):
                cells[column] = "MISSING"
                continue
            zone = zone_label(row.highlights.get(column))
            cells[column] = f"{value} ({zone})" if zone else value
        sheet.append({"company": row.name, "metrics": cells})
    return sheet


def _item(title: str, detail: str, companies: list[str]) -> dict:
    return {"title": title, "detail": detail, "companies": companies}


def net_holding_change(row) -> float | None:
    """Promoter + FII + DII change for a row, counting only the figures screener.in reported; None if none."""
    known = [row.metrics.get(c) for c in ("Prom ch%", "FII ch%", "DII ch%")]
    known = [v for v in known if not _is_missing(v)]
    return sum(known) if known else None


def _state_net_change(entries: list[str], rows: list) -> list[str]:
    """Every company named in a good-points entry must say whether its net holding change is positive or negative.

    A company whose net change is negative is a risk, not a good point, so it is dropped here.
    """
    nets = {row.name.casefold(): net_holding_change(row) for row in rows}
    out = []
    for entry in entries:
        name = entry.split(" - ")[0].strip().casefold()
        net = nets.get(name)
        if net is not None and net < 0:
            continue
        if net is not None and net > 0 and "net holding change" not in entry.lower():
            entry = f"{entry}; net holding change {net:+g} (positive)"
        out.append(entry)
    return out


def _standouts(good: dict[str, list[str]], flagged: set[str]) -> list[str]:
    """Up to five companies with the most strengths and no serious risk (pledge, debt, loss, cash burn)."""
    ranked = sorted(
        ((name, tags) for name, tags in good.items() if name not in flagged and len(tags) >= 2),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    return [f"{name} - {', '.join(tags)}" for name, tags in ranked[:5]]


def build_signals(rows: list) -> dict:
    """Rule-based strengths and risks: {"strengths": [...], "risks": [...]}."""
    strengths: dict[str, list[str]] = {k: [] for k in ("sales", "profit", "pe", "buying", "roe", "quarter")}
    risks: dict[str, list[str]] = {
        k: [] for k in ("pledge", "debt", "selling", "weak_roe", "falling", "loss", "cashflow", "promoter", "pricey")
    }
    good: dict[str, list[str]] = {}  # per company: its strengths, for the "good points" list
    flagged: set[str] = set()  # companies with a serious risk

    for row in rows:
        m, name = row.metrics, row.name

        def value(column):
            v = m.get(column)
            return None if _is_missing(v) else v

        def zone(column):
            return zone_label(row.highlights.get(column))

        if zone("Avg Sales") in ("purple", "purple-white"):
            strengths["sales"].append(f"{name} ({m['Avg Sales']}%)")
            good.setdefault(name, []).append(f"sales growth {m['Avg Sales']}%")
        if zone("Avg profit") in ("purple", "purple-white"):
            strengths["profit"].append(f"{name} ({m['Avg profit']}%)")
            good.setdefault(name, []).append(f"profit growth {m['Avg profit']}%")
        if zone("P/E") in ("purple", "purple-white"):
            strengths["pe"].append(f"{name} (P/E {m['P/E']})")
            good.setdefault(name, []).append(f"low P/E {m['P/E']}")
        if zone("ROE%") in ("purple", "purple-white") or zone("ROCE%") in ("purple", "purple-white"):
            strengths["roe"].append(name)
            good.setdefault(name, []).append("excellent ROE/ROCE")

        if (
            zone("QoQ Sales var%") in _GOOD_QOQ_ZONES
            and zone("QoQ Profits var%") in _GOOD_QOQ_ZONES
            and value("QoQ Sales var%") is not None
            and value("QoQ Profits var%") is not None
        ):
            strengths["quarter"].append(
                f"{name} (sales {m['QoQ Sales var%']:+g}%, profit {m['QoQ Profits var%']:+g}% vs last quarter)"
            )
            good.setdefault(name, []).append(
                f"strong last quarter (sales {m['QoQ Sales var%']:+g}%, profit {m['QoQ Profits var%']:+g}%)"
            )

        changes = [value(c) for c in ("Prom ch%", "FII ch%", "DII ch%")]
        known = [c for c in changes if c is not None]
        if known:
            net = sum(known)
            direction = "positive" if net > 0 else "negative" if net < 0 else "zero"
            # A holding with no figure (blank on screener.in) adds nothing: the net is of the ones reported.
            parts = ", ".join(
                f"{label} {change:+g}" for label, change in zip(("promoter", "FII", "DII"), changes) if change is not None
            )
            detail = f"{name}: net change {net:+g}, {direction} ({parts})"
            if net > 0:
                strengths["buying"].append(detail)
                good.setdefault(name, []).append(f"net holding change {net:+g} (positive)")
            elif net < 0:
                risks["selling"].append(detail)
                flagged.add(name)

        pledged = value("Pledged%")
        if pledged and pledged > 0:
            risks["pledge"].append(f"{name} ({pledged}% pledged)")
            flagged.add(name)
        debt = value("Debt/Eq")
        if debt is not None and debt > DEBT_EQUITY_LIMIT:
            risks["debt"].append(f"{name} (Debt/Eq {debt})")
            flagged.add(name)
        if zone("ROE%") in ("red", "dark-red") or zone("ROCE%") in ("red", "dark-red"):
            risks["weak_roe"].append(f"{name} (ROE {m.get('ROE%', 'n/a')}% and ROCE {m.get('ROCE%', 'n/a')}%)")
        weak = [
            f"{label} {value(col):+g}% (red)" if zone(col) in ("red", "dark-red") and value(col) is not None else None
            for label, col in (("sales", "QoQ Sales var%"), ("profit", "QoQ Profits var%"))
        ]
        if any(weak):
            parts = [
                w or (f"{label} {value(col):+g}%" if value(col) is not None else None)
                for w, (label, col) in zip(weak, (("sales", "QoQ Sales var%"), ("profit", "QoQ Profits var%")))
            ]
            risks["falling"].append(f"{name} ({', '.join(p for p in parts if p)} vs last quarter)")
        np_ann = value("NP Ann")
        if np_ann is not None and np_ann < 0:
            risks["loss"].append(f"{name} (annual profit {np_ann} Cr)")
            flagged.add(name)
        cash = value("CashFlow")
        if cash is not None and cash < 0:
            risks["cashflow"].append(f"{name} (free cash flow {cash} Cr)")
            flagged.add(name)
        promoter = value("Prom Hold%")
        if promoter is not None and promoter < LOW_PROMOTER_HOLDING:
            risks["promoter"].append(f"{name} (promoter holds {promoter}%)")
        if zone("P/E") in ("red", "orange"):
            risks["pricey"].append(f"{name} (P/E {m.get('P/E')})")

    strength_items = [
        _item(
            BUYING_TITLE,
            "Combined change in promoter, FII and DII holding is positive.",
            strengths["buying"],
        ),
        _item(
            QUARTER_TITLE,
            "Both sales and profit grew strongly versus the previous quarter (light-green zone or better).",
            strengths["quarter"],
        ),
        _item("Strong sales growth", "Average sales growth is in the purple (best) zone.", strengths["sales"]),
        _item("Strong profit growth", "Average profit growth is in the purple (best) zone.", strengths["profit"]),
        _item("Low P/E valuation", "P/E is low (purple zone), so the price is modest for the earnings.", strengths["pe"]),
        _item("Excellent ROE or ROCE", "Return on equity or capital is in the purple zone.", strengths["roe"]),
    ]
    risk_items = [
        _item(
            WEAK_QUARTER_TITLE,
            "Sales growth or profit growth versus the previous quarter is in the red zone (at least one of the two).",
            risks["falling"],
        ),
        _item(
            SELLING_TITLE,
            "Combined change in promoter, FII and DII holding is negative.",
            risks["selling"],
        ),
        _item("Promoter shares pledged", "Promoters have pledged part of their holding.", risks["pledge"]),
        _item("High debt", f"Debt to equity is above {DEBT_EQUITY_LIMIT}.", risks["debt"]),
        _item("Loss-making", "Annualised net profit is negative.", risks["loss"]),
        _item("Negative free cash flow", "The business is burning cash.", risks["cashflow"]),
        _item("Weak ROE or ROCE", "Return on equity or capital is in the red zone.", risks["weak_roe"]),
                _item("Expensive valuation", "P/E is in the red or orange zone.", risks["pricey"]),
        _item("Low promoter holding", f"Promoters hold under {LOW_PROMOTER_HOLDING:g}%.", risks["promoter"]),
    ]
    return {
        "strengths": [i for i in strength_items if i["companies"]],
        "risks": [i for i in risk_items if i["companies"]],
        "standouts": _standouts(good, flagged),
    }


def input_hash(rows: list) -> str:
    """Stable fingerprint of what the analysis is based on, so unchanged data is never re-sent."""
    payload = json.dumps({"v": PROMPT_VERSION, "model": config.OPENAI_INSIGHTS_MODEL, "sheet": compact_sheet(rows)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _prompt(rows: list, signals: dict) -> str:
    return (
        "You are reviewing the stock portfolio of an Indian retail investor. Below is a sheet of the "
        "companies they hold, with screener.in metrics. Each value is followed by its colour zone in brackets.\n\n"
        f"{LEGEND}\n\n{RULES}\n\n"
        f"Rule-based findings already computed in code (exact; use them, do not contradict them):\n"
        f"{json.dumps(signals, ensure_ascii=False)}\n\n"
        f"Sheet:\n{json.dumps(compact_sheet(rows), ensure_ascii=False)}\n\n"
        "Write the portfolio's strengths and risks. Rules: only use numbers present in the sheet; do not invent "
        "figures, targets, news or prices; name the companies each point applies to; keep each detail to one or two "
        "plain sentences; do not give buy or sell instructions; never mention or list missing data, just leave those cells out of the judgement. Return JSON only, in this shape:\n"
        '{"summary": "3-4 sentence overall read of the portfolio", '
        '"strengths": [{"title": "...", "detail": "...", "companies": ["..."]}], '
        '"risks": [{"title": "...", "detail": "...", "companies": ["..."]}], '
        '"watchlist": ["up to 5 company names that deserve a closer look, with a few words why"], '
        '"standouts": ["up to 5 company names with the best points, each with a few words on the strengths, for example: Name - strong profit growth, low P/E, net buying; pick companies that are strong without serious risks"]}'
    )


def _clean_items(raw) -> list[dict]:
    items = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or not entry.get("title"):
            continue
        companies = entry.get("companies")
        items.append(
            {
                "title": str(entry["title"]).strip(),
                "detail": str(entry.get("detail") or "").strip(),
                "companies": [str(c).strip() for c in companies if str(c).strip()] if isinstance(companies, list) else [],
            }
        )
    return items


def _pin_holding_change(ai_items: list[dict], rule_items: list[dict], title: str) -> list[dict]:
    """Put the exact net buying/selling finding first, ahead of whatever the AI wrote."""
    pinned = [item for item in rule_items if item["title"] == title]
    rest = [item for item in ai_items if not _HOLDING_CHANGE_TITLE.search(item["title"])]
    return pinned + rest


def _pin_quarter(ai_items: list[dict], rule_items: list[dict]) -> list[dict]:
    """Keep the exact strong-quarter finding right after the net buying one; drop AI duplicates."""
    pinned = [item for item in rule_items if item["title"] == QUARTER_TITLE]
    rest = [item for item in ai_items if not _QUARTER_TITLE.search(item["title"])]
    buying = [item for item in rest if item["title"] == BUYING_TITLE]
    others = [item for item in rest if item["title"] != BUYING_TITLE]
    return buying + pinned + others


def _pin_weak_quarter(ai_items: list[dict], rule_items: list[dict]) -> list[dict]:
    """Exact weak-quarter finding right after net selling; AI quarter points are replaced by it."""
    pinned = [item for item in rule_items if item["title"] == WEAK_QUARTER_TITLE]
    rest = [item for item in ai_items if not _QUARTER_TITLE.search(item["title"])]
    selling = [item for item in rest if item["title"] == SELLING_TITLE]
    others = [item for item in rest if item["title"] != SELLING_TITLE]
    return selling + pinned + others


def generate_insights(rows: list) -> dict:
    """AI-written strength/risk analysis of the sheet. Raises RuntimeError with a readable message on failure."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    signals = build_signals(rows)
    try:
        response = OpenAI(api_key=config.OPENAI_API_KEY).chat.completions.create(
            model=config.OPENAI_INSIGHTS_MODEL,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": _prompt(rows, signals)}],
            max_tokens=2500,
            temperature=0.2,
        )
        parsed = json.loads(response.choices[0].message.content)
    except (OpenAIError, TypeError, ValueError) as exc:
        logger.exception("OpenAI insights request failed")
        raise RuntimeError(f"The AI analysis could not be generated: {exc}") from exc

    strengths = _pin_quarter(
        _pin_holding_change(_clean_items(parsed.get("strengths")), signals["strengths"], BUYING_TITLE),
        signals["strengths"],
    )
    risks = _pin_weak_quarter(
        _pin_holding_change(_clean_items(parsed.get("risks")), signals["risks"], SELLING_TITLE),
        signals["risks"],
    )
    if not strengths and not risks:
        raise RuntimeError("The AI analysis came back empty.")
    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "strengths": strengths,
        "risks": risks,
        "watchlist": [str(w) for w in parsed.get("watchlist", []) if str(w).strip()][:5],
        "standouts": _state_net_change([str(w) for w in parsed.get("standouts", []) if str(w).strip()][:5], rows)
        or signals["standouts"],
    }


def rules_only_insights(rows: list) -> dict:
    signals = build_signals(rows)
    return {
        "summary": "",
        "strengths": signals["strengths"],
        "risks": signals["risks"],
        "watchlist": [],
        "standouts": signals["standouts"],
    }
