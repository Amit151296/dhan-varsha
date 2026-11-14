"""Builds a shareable Excel workbook of a user's portfolio analysis."""

from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.portfolio.analysis import holding_amounts

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(bold=True, color="FFFFFF")
GREEN = Font(color="15803D")
RED = Font(color="B91C1C")


def _join_companies(companies: list[str]) -> str:
    """One per line when entries carry their own commas (net change, last quarter), else comma separated."""
    return ("\n" if any("," in c for c in companies) else ", ").join(companies)


def _pct(pnl: float, invested: float) -> float | None:
    return round(pnl / invested * 100, 2) if invested else None


def _style_header(ws, row: int, width: int) -> None:
    for col in range(1, width + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def _colour_pnl(ws, row: int, columns: list[int]) -> None:
    for col in columns:
        cell = ws.cell(row=row, column=col)
        if isinstance(cell.value, (int, float)) and cell.value != 0:
            cell.font = GREEN if cell.value > 0 else RED


def _autosize(ws, widths: dict[int, int] | None = None) -> None:
    for col in range(1, ws.max_column + 1):
        longest = max((len(str(c.value)) for c in ws[get_column_letter(col)] if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col)].width = min(max(longest + 2, 10), 70)
    for col, width in (widths or {}).items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _breakdown_sheet(wb: Workbook, title: str, label_header: str, share_header: str, rows: list[dict]) -> None:
    ws = wb.create_sheet(title)
    headers = [label_header, "Companies", "Invested (Rs)", share_header, "Current value (Rs)", "P&L (Rs)", "P&L %", "Which companies"]
    ws.append(headers)
    _style_header(ws, 1, len(headers))
    for row in rows:
        ws.append(
            [
                row["label"],
                row["company_count"],
                row["invested"],
                row["share_of_invested"] / 100,
                row["current_value"],
                row["pnl"],
                _pct(row["pnl"], row["invested"]),
                ", ".join(row["companies"]),
            ]
        )
        r = ws.max_row
        ws.cell(row=r, column=4).number_format = "0.0%"
        for col in (3, 5, 6):
            ws.cell(row=r, column=col).number_format = "#,##0.00"
        _colour_pnl(ws, r, [6, 7])
    ws.freeze_panes = "B2"
    _autosize(ws, {8: 80})


def build_analysis_workbook(
    holdings: list,
    analysis: dict,
    broker: str | None = None,
    owner: str | None = None,
    metric_rows: list | None = None,
    insights: dict | None = None,
) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"

    total_invested = analysis["total_invested"]
    total_current = total_pnl = 0.0
    for h in holdings:
        _, current, pnl = holding_amounts(h)
        total_current += current
        total_pnl += pnl
    summary_rows = [
        (f"{owner}'s portfolio analysis" if owner else "Portfolio analysis", None),
        ("Broker", broker or "All brokers"),
        ("Generated", f"{datetime.now():%d %b %Y %H:%M}"),
        ("Companies", analysis["company_count"]),
        ("Invested (Rs)", round(total_invested, 2)),
        ("Current value (Rs)", round(total_current, 2)),
        ("P&L (Rs)", round(total_pnl, 2)),
        ("P&L %", _pct(total_pnl, total_invested)),
    ]
    for row in summary_rows:
        summary.append(row)
    summary["A1"].font = Font(bold=True, size=14)
    for r in range(2, 9):
        summary.cell(row=r, column=1).font = Font(bold=True)
    for r in (5, 6, 7):
        summary.cell(row=r, column=2).number_format = "#,##0.00"
    _colour_pnl(summary, 7, [2])
    _colour_pnl(summary, 8, [2])
    summary.column_dimensions["A"].width = 24
    summary.column_dimensions["B"].width = 24

    ws = wb.create_sheet("Holdings")
    headers = ["Company", "Broker", "Qty", "Avg. price", "LTP", "Invested (Rs)", "Current value (Rs)", "P&L (Rs)", "P&L %"]
    ws.append(headers)
    _style_header(ws, 1, len(headers))
    for h in sorted(holdings, key=lambda x: holding_amounts(x)[0], reverse=True):
        invested, current, pnl = holding_amounts(h)
        ws.append([h.raw_name, h.broker or "-", h.quantity, h.avg_price, h.ltp, round(invested, 2), round(current, 2), round(pnl, 2), _pct(pnl, invested)])
        _colour_pnl(ws, ws.max_row, [8, 9])
    ws.freeze_panes = "B2"
    _autosize(ws)

    _breakdown_sheet(wb, "By broker", "Broker", "Share of invested", analysis["by_broker"])
    _breakdown_sheet(wb, "By sector", "Sector", "Share of invested", analysis["by_sector"])
    _breakdown_sheet(wb, "By industry", "Industry", "Share of invested", analysis.get("by_industry", []))
    _breakdown_sheet(wb, "By concentration", "Tier", "Share of invested", analysis.get("by_concentration", []))

    if metric_rows:
        columns = list(metric_rows[0].metrics.keys())
        ms = wb.create_sheet("Company metrics")
        ms.append(["Name", *columns])
        _style_header(ms, 1, len(columns) + 1)
        for row in metric_rows:
            ms.append([row.name, *(row.metrics.get(c) for c in columns)])
            for col_index, column in enumerate(columns, start=2):
                highlight = row.highlights.get(column)
                if highlight:
                    cell = ms.cell(row=ms.max_row, column=col_index)
                    bg = highlight.background.lstrip("#")
                    cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
                    cell.font = Font(color=highlight.color.lstrip("#"))
        ms.freeze_panes = "B2"
        for col_index in range(1, len(columns) + 2):
            ms.column_dimensions[get_column_letter(col_index)].width = 14
        ms.column_dimensions["A"].width = 28

    if metric_rows and insights:
        ws_i = wb.create_sheet("Strength and risk")
        ws_i.append(["Section", "Point", "Detail", "No. of companies", "Companies"])
        _style_header(ws_i, 1, 5)
        if insights.get("summary"):
            ws_i.append(["Summary", insights["summary"], "", "", ""])
        for section, key in (("Strengths", "strengths"), ("Risks", "risks")):
            for item in insights.get(key, []):
                ws_i.append([section, item["title"], item.get("detail", ""), len(item.get("companies", [])), _join_companies(item.get("companies", []))])
        for section, key in (("Worth a closer look", "watchlist"), ("Companies with good points", "standouts")):
            for entry in insights.get(key) or []:
                ws_i.append([section, entry, "", "", ""])
        for row in ws_i.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for letter, width in zip("ABCDE", (24, 40, 50, 12, 60)):
            ws_i.column_dimensions[letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
