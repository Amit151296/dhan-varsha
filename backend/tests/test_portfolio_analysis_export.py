import io
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.portfolio.analysis import analyse_portfolio
from app.services.portfolio.analysis_export import build_analysis_workbook
from app.services.portfolio.concentration import concentration_breakdown


def _holding(name, broker, invested, current):
    return SimpleNamespace(
        raw_name=name, resolved_url=f"/company/{name}/", broker=broker, quantity=10, avg_price=1, ltp=1,
        invested_value=invested, current_value=current, pnl=current - invested,
    )


def test_workbook_has_all_sheets_and_pnl_percent():
    holdings = [_holding("AAA", "Groww", 100, 150), _holding("BBB", "Kite", 100, 50)]
    analysis = analyse_portfolio(holdings, {"/company/AAA/": ("Defence", "Aerospace & Defense")})
    analysis["by_concentration"] = concentration_breakdown(holdings)

    wb = load_workbook(io.BytesIO(build_analysis_workbook(holdings, analysis)))

    assert wb.sheetnames == ["Summary", "Holdings", "By broker", "By sector", "By industry", "By concentration"]
    rows = {r[0]: r for r in wb["Holdings"].iter_rows(min_row=2, values_only=True)}
    assert rows["AAA"][-1] == 50.0
    assert rows["BBB"][-1] == -50.0
    assert wb["Summary"]["B8"].value == 0.0  # +50 and -50 cancel out


def test_html_exports_are_self_contained_and_escaped():
    from types import SimpleNamespace as NS

    from app.services.html_export import build_analysis_html, build_metrics_html

    holdings = [_holding("A<b>", "Groww", 100, 150)]
    analysis = analyse_portfolio(holdings, {})
    analysis["by_concentration"] = concentration_breakdown(holdings)
    page = build_analysis_html("Shivam's Portfolio - analysis", holdings, analysis).decode()
    assert "viewport" in page and "<script" not in page
    assert "A&lt;b&gt;" in page and "A<b>" not in page
    assert "+50.00%" in page

    row = NS(name="X & Y", metrics={"CMP": 10}, highlights={"CMP": NS(background="#ffffff", color="#000000")})
    table = build_metrics_html("Shivam's Portfolio", [row], None).decode()
    assert "X &amp; Y" in table and "background:#ffffff" in table


def test_report_includes_metrics_and_no_disclaimer():
    from types import SimpleNamespace as NS

    from app.services.html_export import build_analysis_html

    holdings = [_holding("AAA", "Groww", 100, 150)]
    analysis = analyse_portfolio(holdings, {})
    row = NS(name="AAA Ltd", metrics={"CMP": 10}, highlights={"CMP": NS(background="#ffffff", color="#000000")})

    page = build_analysis_html("Shivam's Portfolio", holdings, analysis, None, [row], None, ["ZZZ"]).decode()
    assert "Company metrics (screener.in)" in page and "AAA Ltd" in page
    assert "Metrics not available yet for: ZZZ" in page
    assert "not investment advice" not in page

    wb = load_workbook(io.BytesIO(build_analysis_workbook(holdings, analysis, metric_rows=[row])))
    assert "Company metrics" in wb.sheetnames


def test_report_includes_strength_and_risk_only_when_generated():
    from types import SimpleNamespace as NS

    from app.services.html_export import build_analysis_html

    holdings = [_holding("AAA", "Groww", 100, 150)]
    analysis = analyse_portfolio(holdings, {})
    row = NS(name="AAA Ltd", metrics={"CMP": 10}, highlights={"CMP": NS(background="#ffffff", color="#000000")})
    insights = {
        "summary": "Solid mix.",
        "strengths": [{"title": "Strong last quarter", "detail": "d", "companies": ["AAA Ltd"]}],
        "risks": [{"title": "High debt", "detail": "", "companies": ["BBB"]}],
        "watchlist": [],
        "standouts": ["AAA Ltd - low P/E"],
    }
    with_it = build_analysis_html("T", holdings, analysis, None, [row], None, None, insights).decode()
    without = build_analysis_html("T", holdings, analysis, None, [row]).decode()
    assert "Portfolio strength and risk" in with_it and "Strong last quarter" in with_it and "High debt" in with_it
    assert "Portfolio strength and risk" not in without

    wb = load_workbook(io.BytesIO(build_analysis_workbook(holdings, analysis, metric_rows=[row], insights=insights)))
    assert "Strength and risk" in wb.sheetnames
    wb = load_workbook(io.BytesIO(build_analysis_workbook(holdings, analysis, metric_rows=[row])))
    assert "Strength and risk" not in wb.sheetnames
