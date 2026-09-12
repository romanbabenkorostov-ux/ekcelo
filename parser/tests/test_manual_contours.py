"""tests/test_manual_contours.py — ручные контуры и конфликт с выпиской (ADR-008).

Сторожится не запись в таблицу, а три обещания модуля: ручной контур не
попадает в слепок ЕГРН, повторная загрузка не плодит копий, и появление контура
в выписке НЕ подменяет обводку молча.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import manual_contours as M             # noqa: E402
from egrn_parser.parsers import xml_geometry_db as W             # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry    # noqa: E402
from tests.test_xml_geometry import land_xml                     # noqa: E402

CAD = "26:29:130106:382"

# Примерная обводка вокруг того же участка — прямоугольник «на глаз».
ROUGH_RING = [(42.8098, 43.9713), (42.8115, 43.9713),
              (42.8115, 43.9719), (42.8098, 43.9719)]


def _kml(cad: str = CAD, ring=None, name_only: bool = False) -> str:
    ring = ring or ROUGH_RING
    coords = " ".join(f"{lon},{lat}" for lon, lat in ring)
    label = (f"<name>{cad} примерно</name>" if name_only
             else f"<name>участок</name><description>КН {cad}, обвёл по снимку</description>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f"<Placemark>{label}<Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{coords}</coordinates>"
            "</LinearRing></outerBoundaryIs></Polygon></Placemark>"
            "<Placemark><name>точка съёмки</name><Point>"
            "<coordinates>42.81,43.97</coordinates></Point></Placemark>"
            "</Document></kml>")


def _write(tmp_path: Path, text: str, name: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def _add_egrn_contour(conn: sqlite3.Connection, tmp_path: Path) -> None:
    path = _write(tmp_path, land_xml(), "extract.xml")
    W.write_geometry(conn, extract_geometry(path))


# --- чтение файлов --------------------------------------------------------

def test_reads_kml_with_cad_in_description(tmp_path):
    contours = M.load_contours(_write(tmp_path, _kml(), "ручные.kml"))
    assert len(contours) == 1
    assert contours[0].cad_number == CAD
    assert contours[0].source == "kml"


def test_reads_kml_with_cad_in_name(tmp_path):
    """В разных редакторах подпись удобно писать по-разному — ищем в обоих."""
    contours = M.load_contours(_write(tmp_path, _kml(name_only=True), "n.kml"))
    assert contours and contours[0].cad_number == CAD


def test_placemark_without_cad_is_skipped_not_fatal(tmp_path):
    """В файле человека всегда есть посторонние метки — ронять загрузку нельзя."""
    contours = M.load_contours(_write(tmp_path, _kml(), "ручные.kml"))
    assert len(contours) == 1, "точка съёмки не должна попасть в контуры"


def test_reads_geojson(tmp_path):
    payload = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"cadastral_number": CAD},
        "geometry": {"type": "Polygon",
                     "coordinates": [[list(p) for p in ROUGH_RING + [ROUGH_RING[0]]]]}}]}
    path = _write(tmp_path, json.dumps(payload), "ручные.geojson")
    contours = M.load_contours(path)
    assert len(contours) == 1 and contours[0].source == "geojson"


def test_unknown_format_is_refused(tmp_path):
    with pytest.raises(ValueError):
        M.load_contours(_write(tmp_path, "x", "ручные.dxf"))


def test_area_is_computed_in_square_metres(tmp_path):
    contour = M.load_contours(_write(tmp_path, _kml(), "ручные.kml"))[0]
    # Прямоугольник ~0.0017° долготы × 0.0006° широты на широте 44°.
    assert 7000 < contour.area_sqm() < 11000


# --- запись ---------------------------------------------------------------

def test_import_writes_and_becomes_current(conn, tmp_path):
    report = M.import_manual_contours(
        conn, M.load_contours(_write(tmp_path, _kml(), "ручные.kml"),
                              author="Бабенко", note="по снимку", confidence=0.4))
    assert report.imported == [CAD]
    current = M.current_contours(conn)
    assert len(current) == 1
    assert current[0]["contour_source"] == "manual"
    assert current[0]["confidence"] == 0.4


def test_manual_contour_never_lands_in_egrn_snapshot(conn, tmp_path):
    """Главный инвариант: §8 воспроизводится из выписок, обводки там нет."""
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    assert conn.execute("SELECT COUNT(*) FROM egrn_contour").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM manual_contour").fetchone()[0] == 1


def test_second_import_updates_not_duplicates(conn, tmp_path):
    path = _write(tmp_path, _kml(), "ручные.kml")
    M.import_manual_contours(conn, M.load_contours(path))
    report = M.import_manual_contours(conn, M.load_contours(path))
    assert report.updated == [CAD] and report.imported == []
    assert conn.execute("SELECT COUNT(*) FROM manual_contour").fetchone()[0] == 1


def test_degenerate_contour_is_skipped(conn, tmp_path):
    contour = M.ManualContour(cad_number=CAD, rings=[[(42.8, 43.9), (42.8, 43.9)]])
    report = M.import_manual_contours(conn, [contour])
    assert report.imported == []
    assert report.skipped and "вырожденный" in report.skipped[0][1]


# --- конфликт -------------------------------------------------------------

def test_extract_contour_raises_conflict_not_silent_replace(conn, tmp_path):
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    fresh = M.detect_conflicts(conn)
    assert len(fresh) == 1
    message = fresh[0]["message"]
    assert "появился уточнённый контур" in message
    assert "Оставить исходный или заменить на уточнённый?" in message
    assert "1986" in message


def test_manual_stays_current_until_person_decides(conn, tmp_path):
    """Умолчание — ручной контур: он мог уже уйти в подписанный акт."""
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    current = M.current_contours(conn)
    assert len(current) == 1
    assert current[0]["contour_source"] == "manual"


def test_conflict_is_not_raised_twice(conn, tmp_path):
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    assert len(M.detect_conflicts(conn)) == 1
    assert M.detect_conflicts(conn) == []
    assert len(M.open_conflicts(conn)) == 1


def test_open_conflict_carries_authorship_for_the_decision(conn, tmp_path):
    M.import_manual_contours(
        conn, M.load_contours(_write(tmp_path, _kml(), "m.kml"),
                              author="Бабенко", note="по забору", confidence=0.3))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    item = M.open_conflicts(conn)[0]
    assert item["author"] == "Бабенко"
    assert item["note"] == "по забору"
    assert item["confidence"] == 0.3
    assert item["delta_sqm"] is not None


def test_resolution_use_egrn_switches_current_and_retires_manual(conn, tmp_path):
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    result = M.resolve_conflict(conn, CAD, "use_egrn", resolved_by="Бабенко")
    assert result["resolved"]
    current = M.current_contours(conn)
    assert len(current) == 1
    assert current[0]["contour_source"] == "egrn"
    assert current[0]["land_layout"] == "ЗУ"
    retired = conn.execute(
        "SELECT retired_at IS NOT NULL, retired_reason FROM manual_contour").fetchone()
    assert retired[0] == 1, "ручной контур отзывается"
    assert conn.execute("SELECT COUNT(*) FROM manual_contour").fetchone()[0] == 1, \
        "но не удаляется: на него мог ссылаться подписанный акт"


def test_resolution_keep_manual_leaves_egrn_snapshot_intact(conn, tmp_path):
    """Решение человека не правит слепок ЕГРН — только то, что считать текущим."""
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    M.resolve_conflict(conn, CAD, "keep_manual", resolved_by="Бабенко",
                       note="акт подписан")
    current = M.current_contours(conn)
    assert current[0]["contour_source"] == "manual"
    assert conn.execute(
        "SELECT COUNT(*) FROM egrn_contour WHERE kind='parcel'").fetchone()[0] == 1


def test_resolution_is_recorded_with_author(conn, tmp_path):
    M.import_manual_contours(conn, M.load_contours(_write(tmp_path, _kml(), "m.kml")))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    M.resolve_conflict(conn, CAD, "keep_manual", resolved_by="Бабенко",
                       note="акт подписан")
    row = conn.execute(
        "SELECT resolution, resolved_by, resolution_note, resolved_at IS NOT NULL "
        "  FROM contour_conflict").fetchone()
    assert row == ("keep_manual", "Бабенко", "акт подписан", 1)


def test_unknown_choice_is_refused(conn, tmp_path):
    with pytest.raises(ValueError):
        M.resolve_conflict(conn, CAD, "перезаписать")


def test_resolving_absent_conflict_is_reported_not_raised(conn):
    result = M.resolve_conflict(conn, CAD, "use_egrn")
    assert not result["resolved"]
    assert "нет" in result["reason"]


def test_no_conflict_when_object_had_no_manual_contour(conn, tmp_path):
    _add_egrn_contour(conn, tmp_path)
    assert M.detect_conflicts(conn) == []
    assert M.current_contours(conn)[0]["contour_source"] == "egrn"


def test_reimport_revives_retired_contour(conn, tmp_path):
    """Повторная подача того же файла — сознательное решение человека."""
    path = _write(tmp_path, _kml(), "m.kml")
    M.import_manual_contours(conn, M.load_contours(path))
    _add_egrn_contour(conn, tmp_path)
    M.detect_conflicts(conn)
    M.resolve_conflict(conn, CAD, "use_egrn")
    M.import_manual_contours(conn, M.load_contours(path))
    assert conn.execute(
        "SELECT retired_at FROM manual_contour").fetchone()[0] is None


# --- раскладка участка ----------------------------------------------------

def test_layout_is_recorded_for_simple_parcel(conn, tmp_path):
    _add_egrn_contour(conn, tmp_path)
    assert conn.execute(
        "SELECT DISTINCT land_layout FROM egrn_contour").fetchone()[0] == "ЗУ"
