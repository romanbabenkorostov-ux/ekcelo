"""tests/test_geo_pipeline.py — сквозной проход: выписки → БД → KML + эссе + схема.

Проход склеивает четыре модуля, и ломается он обычно не внутри них, а на стыках:
порядок шагов, отсев файлов подписи, поведение при выписке без геометрии.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser import geo_pipeline as P                        # noqa: E402
from tests.test_xml_geometry import BUILD_XML, land_xml          # noqa: E402


@pytest.fixture
def inbox(tmp_path) -> Path:
    """Папка, похожая на реальную выгрузку Росреестра: XML + подписи + PDF."""
    folder = tmp_path / "Выписки"
    folder.mkdir()
    (folder / "land.xml").write_text(land_xml(), encoding="utf-8")
    (folder / "build.xml").write_text(BUILD_XML, encoding="utf-8")
    (folder / "land.xml.sig").write_text("подпись", encoding="utf-8")
    (folder / "land ЭП.pdf").write_bytes(b"%PDF-1.4")
    return folder


def test_collect_xml_skips_signatures_and_pdf(inbox):
    names = [p.name for p in P.collect_xml(inbox)]
    assert sorted(names) == ["build.xml", "land.xml"]


def test_collect_xml_accepts_single_file(inbox):
    assert P.collect_xml(inbox / "land.xml") == [inbox / "land.xml"]
    assert P.collect_xml(inbox / "land ЭП.pdf") == []


def test_pipeline_writes_db_kml_essays_and_schema_doc(inbox, tmp_path):
    out = tmp_path / "выгрузка"
    result = P.run_pipeline(inbox, tmp_path / "egrn.db", out_dir=out,
                            skip_card=True, generated_on="2026-09-12")
    assert result.written == 1
    assert result.failed == 0
    assert result.kml_path and result.kml_path.exists()
    assert len(result.essays) == 1 and result.essays[0].exists()
    assert result.schema_doc and result.schema_doc.exists()
    assert (tmp_path / "egrn.db").exists()


def test_pipeline_reports_building_without_geometry(inbox, tmp_path):
    """Выписка на ОКС — не ошибка прохода, а объект без контура."""
    result = P.run_pipeline(inbox, tmp_path / "egrn.db", skip_card=True,
                            make_kml=False, make_essays=False,
                            make_schema_doc=False)
    building = next(f for f in result.files if f.path.name == "build.xml")
    assert building.ok
    assert not building.geometry_written
    assert "нет геометрии" in building.note
    assert "26:29:130106:72" in building.note


def test_pipeline_is_idempotent(inbox, tmp_path):
    db = tmp_path / "egrn.db"
    for _ in range(2):
        P.run_pipeline(inbox, db, skip_card=True, make_kml=False,
                       make_essays=False, make_schema_doc=False)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM egrn_contour").fetchone()[0] == 2


def test_pipeline_kml_is_deterministic(inbox, tmp_path):
    first = P.run_pipeline(inbox, tmp_path / "a.db", out_dir=tmp_path / "a",
                           skip_card=True, generated_on="2026-09-12")
    second = P.run_pipeline(inbox, tmp_path / "b.db", out_dir=tmp_path / "b",
                            skip_card=True, generated_on="2026-09-12")
    assert first.kml_path.read_text(encoding="utf-8") == \
           second.kml_path.read_text(encoding="utf-8")


def test_pipeline_skips_empty_kml(tmp_path):
    """Файл с нулём Placemark выглядит как успешная выгрузка — не пишем."""
    folder = tmp_path / "только_оксы"
    folder.mkdir()
    (folder / "build.xml").write_text(BUILD_XML, encoding="utf-8")
    result = P.run_pipeline(folder, tmp_path / "egrn.db", skip_card=True,
                            generated_on="2026-09-12")
    assert result.kml_path is None
    assert result.essays == []
    assert result.schema_doc is not None


def test_pipeline_area_gate_blocks_by_default(tmp_path):
    folder = tmp_path / "плохая_зона"
    folder.mkdir()
    (folder / "land.xml").write_text(land_xml(area="9000"), encoding="utf-8")
    result = P.run_pipeline(folder, tmp_path / "egrn.db", skip_card=True,
                            make_kml=False, make_essays=False,
                            make_schema_doc=False)
    assert result.written == 0
    assert "НЕ СХОДИТСЯ" in result.files[0].note


def test_pipeline_force_overrides_area_gate(tmp_path):
    folder = tmp_path / "плохая_зона"
    folder.mkdir()
    (folder / "land.xml").write_text(land_xml(area="9000"), encoding="utf-8")
    result = P.run_pipeline(folder, tmp_path / "egrn.db", skip_card=True,
                            force=True, make_kml=False, make_essays=False,
                            make_schema_doc=False)
    assert result.written == 1


def test_pipeline_reports_progress(inbox, tmp_path):
    steps: list[str] = []
    P.run_pipeline(inbox, tmp_path / "egrn.db", skip_card=True,
                   generated_on="2026-09-12", on_step=steps.append)
    assert any("Найдено XML" in s for s in steps)
    assert any(s.startswith("✓") for s in steps)
    assert any("Описание схемы" in s for s in steps)


def test_pipeline_survives_broken_file(tmp_path):
    """Битый файл портит свою строку отчёта, а не весь проход."""
    folder = tmp_path / "битые"
    folder.mkdir()
    (folder / "good.xml").write_text(land_xml(), encoding="utf-8")
    (folder / "broken.xml").write_text("<не xml", encoding="utf-8")
    result = P.run_pipeline(folder, tmp_path / "egrn.db", skip_card=True,
                            make_kml=False, make_essays=False,
                            make_schema_doc=False)
    assert result.written == 1
    assert result.failed == 1
    assert not next(f for f in result.files if f.path.name == "broken.xml").ok


def test_parts_flag_reaches_kml(inbox, tmp_path):
    with_parts = P.run_pipeline(inbox, tmp_path / "a.db", out_dir=tmp_path / "a",
                                skip_card=True, generated_on="2026-09-12")
    without = P.run_pipeline(inbox, tmp_path / "b.db", out_dir=tmp_path / "b",
                             skip_card=True, with_parts=False,
                             generated_on="2026-09-12")
    assert with_parts.kml_path.read_text(encoding="utf-8").count("<Placemark>") == 2
    assert without.kml_path.read_text(encoding="utf-8").count("<Placemark>") == 1
