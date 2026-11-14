"""Self-contained HTML reports (one file, no external assets) that open on any phone or laptop."""

from __future__ import annotations

from datetime import datetime
from html import escape

from app.services.portfolio.analysis import holding_amounts

_PAGE_CSS = """
:root{--bg:#ffffff;--fg:#111827;--muted:#6b7280;--card:#f3f4f6;--line:#d1d5db;--head:#1f2937;--headfg:#ffffff;--pos:#15803d;--neg:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--fg:#e5e7eb;--muted:#9ca3af;--card:#111a2e;--line:#2b3750;--head:#1e293b;--headfg:#f9fafb;--pos:#4ade80;--neg:#f87171}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:1.35rem;margin:0 0 4px}h2{font-size:1.05rem;margin:28px 0 8px}
.meta{color:var(--muted);margin:0 0 12px}
.cards{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:140px}
.card b{display:block;font-size:1.05rem}.card span{color:var(--muted);font-size:.8rem}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;white-space:nowrap}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right}
th{background:var(--head);color:var(--headfg);position:sticky;top:0;font-weight:600}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1}
th:first-child{background:var(--head);z-index:2}
td.txt{text-align:left;white-space:normal;min-width:220px}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.note{color:var(--muted);font-size:.8rem;margin-top:24px}
"""


def _page(title: str, body: str) -> bytes:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_PAGE_CSS}</style></head><body>{body}</body></html>"
    ).encode("utf-8")


def _num(value, digits: int = 2) -> str:
    return f"{value:,.{digits}f}" if isinstance(value, (int, float)) else "-"


def _pnl_class(value) -> str:
    if not isinstance(value, (int, float)) or value == 0:
        return ""
    return "pos" if value > 0 else "neg"


def _pct_text(pnl: float, invested: float) -> tuple[str, str]:
    if not invested:
        return "-", ""
    pct = pnl / invested * 100
    return f"{pct:+.2f}%", _pnl_class(pct)


def _metrics_table(rows: list) -> str:
    columns = list(rows[0].metrics.keys()) if rows else []
    head = "".join(f"<th>{escape(c)}</th>" for c in ["Name", *columns])
    body_rows = []
    for row in rows:
        cells = [f"<td>{escape(row.name)}</td>"]
        for column in columns:
            highlight = row.highlights.get(column)
            style = (
                f' style="background:{escape(highlight.background)};color:{escape(highlight.color)}"'
                if highlight
                else ""
            )
            cells.append(f"<td{style}>{escape(str(row.metrics.get(column, '')))}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'


def build_metrics_html(title: str, rows: list, as_of: datetime | None) -> bytes:
    when = f" Data as of {as_of:%d %b %Y}." if as_of else ""
    body = (
        f'<h1>{escape(title)}</h1><p class="meta">{len(rows)} companies.{when} '
        f"Generated {datetime.now():%d %b %Y %H:%M}. Scroll sideways to see all columns.</p>"
        + _metrics_table(rows)
    )
    return _page(title, body)


def _breakdown_table(heading: str, label_header: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    headers = [label_header, "Companies", "Invested (Rs)", "Share", "Current value (Rs)", "P&amp;L (Rs)", "P&amp;L %", "Which companies"]
    head = "".join(f"<th>{h}</th>" for h in headers)
    out = []
    for r in rows:
        pct_text, pct_cls = _pct_text(r["pnl"], r["invested"])
        out.append(
            "<tr>"
            f"<td>{escape(r['label'])}</td><td>{r['company_count']}</td><td>{_num(r['invested'])}</td>"
            f"<td>{r['share_of_invested']}%</td><td>{_num(r['current_value'])}</td>"
            f'<td class="{_pnl_class(r["pnl"])}">{_num(r["pnl"])}</td><td class="{pct_cls}">{pct_text}</td>'
            f'<td class="txt">{escape(", ".join(r["companies"]))}</td></tr>'
        )
    return (
        f"<h2>{escape(heading)}</h2>"
        f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(out)}</tbody></table></div>'
    )


def _company_list(companies: list[str] | None) -> str:
    """One line each when entries carry their own commas (net change, last quarter), else comma separated."""
    if not companies:
        return ""
    if any("," in c for c in companies):
        return "<ul>" + "".join(f"<li>{escape(c)}</li>" for c in companies) + "</ul>"
    return f'<div class="meta">{escape(", ".join(companies))}</div>'


def _insight_list(heading: str, items: list[dict]) -> str:
    if not items:
        return ""
    lis = "".join(
        f"<li><b>{escape(i['title'])}</b>"
        + (f" - {escape(i['detail'])}" if i.get("detail") else "")
        + (f" ({len(i['companies'])} {'company' if len(i['companies']) == 1 else 'companies'})" if i.get("companies") else "")
        + _company_list(i.get("companies"))
        + "</li>"
        for i in items
    )
    return f"<h3>{escape(heading)}</h3><ul>{lis}</ul>"


def _insights_html(insights: dict) -> str:
    out = "<h2>Portfolio strength and risk</h2>"
    if insights.get("summary"):
        out += f"<p>{escape(insights['summary'])}</p>"
    out += _insight_list("Strengths", insights.get("strengths", []))
    out += _insight_list("Risks", insights.get("risks", []))
    for heading, key in (("Worth a closer look", "watchlist"), ("Companies with good points", "standouts")):
        entries = insights.get(key) or []
        if entries:
            out += f"<h3>{heading}</h3><ul>" + "".join(f"<li>{escape(e)}</li>" for e in entries) + "</ul>"
    return out


def build_analysis_html(
    title: str,
    holdings: list,
    analysis: dict,
    broker: str | None = None,
    metric_rows: list | None = None,
    metrics_as_of: datetime | None = None,
    metrics_missing: list[str] | None = None,
    insights: dict | None = None,
) -> bytes:
    total_current = total_pnl = 0.0
    for h in holdings:
        _, current, pnl = holding_amounts(h)
        total_current += current
        total_pnl += pnl
    invested = analysis["total_invested"]
    pct_text, pct_cls = _pct_text(total_pnl, invested)
    cards = "".join(
        f'<div class="card"><b class="{cls}">{value}</b><span>{label}</span></div>'
        for label, value, cls in [
            ("Companies", analysis["company_count"], ""),
            ("Invested (Rs)", _num(invested), ""),
            ("Current value (Rs)", _num(total_current), ""),
            ("P&amp;L (Rs)", _num(total_pnl), _pnl_class(total_pnl)),
            ("P&amp;L %", pct_text, pct_cls),
        ]
    )

    headers = ["Company", "Broker", "Qty", "Avg. price", "LTP", "Invested (Rs)", "Current value (Rs)", "P&amp;L (Rs)", "P&amp;L %"]
    head = "".join(f"<th>{h}</th>" for h in headers)
    hold_rows = []
    for h in sorted(holdings, key=lambda x: holding_amounts(x)[0], reverse=True):
        inv, cur, pnl = holding_amounts(h)
        text, cls = _pct_text(pnl, inv)
        hold_rows.append(
            f"<tr><td>{escape(h.raw_name)}</td><td>{escape(h.broker or '-')}</td><td>{_num(h.quantity, 0)}</td>"
            f"<td>{_num(h.avg_price)}</td><td>{_num(h.ltp)}</td><td>{_num(inv)}</td><td>{_num(cur)}</td>"
            f'<td class="{_pnl_class(pnl)}">{_num(pnl)}</td><td class="{cls}">{text}</td></tr>'
        )

    body = (
        f'<h1>{escape(title)}</h1><p class="meta">{escape(broker or "All brokers")} - '
        f"generated {datetime.now():%d %b %Y %H:%M}</p>"
        f'<div class="cards">{cards}</div>'
        f'<h2>Holdings</h2><div class="wrap"><table><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(hold_rows)}</tbody></table></div>'
        + _breakdown_table("By broker", "Broker", analysis["by_broker"])
        + _breakdown_table("By sector", "Sector", analysis["by_sector"])
        + _breakdown_table("By industry", "Industry", analysis.get("by_industry", []))
        + _breakdown_table("By concentration", "Tier", analysis.get("by_concentration", []))
    )
    if metric_rows:
        when = f" Data as of {metrics_as_of:%d %b %Y}." if metrics_as_of else ""
        body += f'<h2>Company metrics (screener.in)</h2><p class="meta">{len(metric_rows)} companies.{when} Scroll sideways to see all columns.</p>'
        body += _metrics_table(metric_rows)
    if metric_rows and insights:
        body += _insights_html(insights)
    if metrics_missing:
        body += f'<p class="meta">Metrics not available yet for: {escape(", ".join(metrics_missing))}.</p>'
    return _page(title, body)
