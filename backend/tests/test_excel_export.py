from datetime import datetime, timezone

import openpyxl

from app import config, schemas
from app.services.screener import excel_export


def _row(name, cmp_value, highlight=None):
    highlights = {"CMP": schemas.Highlight(**highlight)} if highlight else {}
    return schemas.StockRowOut(name=name, metrics={"CMP": cmp_value}, highlights=highlights)


def test_build_workbook_writes_headers_values_and_colours():
    rows = [_row("Acme", 100.0, {"zone": "red", "background": "#FF0000", "color": "#000000"})]

    workbook_bytes = excel_export.build_workbook("IT", rows)

    workbook = openpyxl.load_workbook(__import__("io").BytesIO(workbook_bytes))
    sheet = workbook.active
    assert [c.value for c in sheet[1]] == ["Name", "CMP"]
    assert sheet["A2"].value == "Acme"
    assert sheet["B2"].value == 100.0
    assert sheet["B2"].fill.fgColor.rgb[-6:] == "FF0000"


def test_archive_to_disk_creates_year_month_folder_and_skips_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCREENER_EXPORT_DIR", None)
    assert excel_export.archive_to_disk(b"fake", "IT", datetime.now(timezone.utc)) is None

    monkeypatch.setattr(config, "SCREENER_EXPORT_DIR", str(tmp_path))
    fetched_at = datetime(2026, 10, 18, tzinfo=timezone.utc)

    saved_path = excel_export.archive_to_disk(b"fake-bytes", "hospital", fetched_at)

    assert saved_path == tmp_path / "2026" / "OCTOBER" / "hospital.xlsx"
    assert saved_path.read_bytes() == b"fake-bytes"


def test_archive_to_disk_is_best_effort_on_failure(monkeypatch):
    monkeypatch.setattr(config, "SCREENER_EXPORT_DIR", "Z:\\path\\that\\cannot\\exist\\at\\all")
    result = excel_export.archive_to_disk(b"x", "IT", datetime.now(timezone.utc))
    assert result is None
