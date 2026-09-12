"""tests/test_kml_exporter.py — KML контуров против инвариантов CONTRACT_KMZ §6.

Проверяется не «файл получился», а каждый пункт чеклиста контракта: по нему
вьюер классифицирует объекты, и нарушение обнаружится не здесь, а на чужой
стороне через неделю.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.exporters import kml_exporter as K              # noqa: E402
from egrn_parser.parsers import xml_geometry_db as W             # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry    # noqa: E402
from tests.test_xml_geometry import land_xml                     # noqa: E402

NS = {"k": "http://www.opengis.net/kml/2.2"}
# Регулярка кад.№ из CONTRACT_KMZ §6; суффикс /N — часть или контур.
CAD_RE = re.compile(r"\b\d{2}:\d{2}:\d{2,8}:\d{1,8}(?:/\d+)?\b")


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    path = tmp_path / "extract.xml"
    path.write_text(land_xml(), encoding="utf-8")
    W.write_geometry(connection, extract_geometry(path))
    yield connection
    connection.close()


def _doc(kml: str):
    return ET.fromstring(kml).find("k:Document", NS)


def _placemarks(kml: str):
    return _doc(kml).findall(".//k:Placemark", NS)


def _text(elem, tag: str) -> str:
    node = elem.find(f"k:{tag}", NS)
    return node.text if node is not None and node.text else ""


# --- инварианты §6 --------------------------------------------------------

def test_is_well_formed_xml(conn):
    ET.fromstring(K.build_kml(conn))


def test_style_prefix_and_unique_ids(conn):
    kml = K.build_kml(conn)
    doc = _doc(kml)
    ids = [s.get("id") for s in doc.findall("k:Style", NS)]
    assert ids and len(ids) == len(set(ids))
    assert all(i.startswith("cad_zu_") for i in ids)
    for placemark in _placemarks(kml):
        assert _text(placemark, "styleUrl").startswith("#cad_zu_")


def test_cad_number_is_token_in_name_and_key_in_description(conn):
    for placemark in _placemarks(K.build_kml(conn)):
        assert CAD_RE.search(_text(placemark, "name"))
        assert "Кадастровый номер: " in _text(placemark, "description")


def test_description_is_key_value_pairs_without_html(conn):
    for placemark in _placemarks(K.build_kml(conn)):
        description = _text(placemark, "description")
        assert "<" not in description and ">" not in description
        assert description.endswith(";")
        for chunk in [c for c in description.split("; ") if c]:
            assert ": " in chunk


def test_empty_values_are_dropped_not_written_blank(conn):
    """Контракт §A.5: пустое значение — ключ опускается, а не «Площадь: ;»."""
    for placemark in _placemarks(K.build_kml(conn)):
        assert ": ;" not in _text(placemark, "description")


def test_rings_are_closed_and_have_four_points(conn):
    for coords in _doc(K.build_kml(conn)).findall(".//k:coordinates", NS):
        points = coords.text.split()
        assert len(points) >= 4
        assert points[0] == points[-1]


def test_coordinates_are_lon_lat_wgs84(conn):
    for coords in _doc(K.build_kml(conn)).findall(".//k:coordinates", NS):
        for point in coords.text.split():
            lon, lat = (float(v) for v in point.split(","))
            assert 42.0 < lon < 43.5, "первым идёт долгота, а не широта"
            assert 43.5 < lat < 44.5


def test_one_geometry_per_placemark(conn):
    for placemark in _placemarks(K.build_kml(conn)):
        assert len(placemark.findall(".//k:Polygon", NS)) == 1
        assert not placemark.findall(".//k:MultiGeometry", NS)


def test_document_carries_schema_version_and_author(conn):
    doc = _doc(K.build_kml(conn))
    assert doc.find("k:atom:author", {**NS, "atom": "http://www.w3.org/2005/Atom"}) is not None \
        or doc.find("{http://www.w3.org/2005/Atom}author") is not None
    data = {d.get("name"): d.find("k:value", NS).text
            for d in doc.findall("k:ExtendedData/k:Data", NS)}
    assert data["kml_schema_version"] == "2.1"
    assert data["generator"]


def test_graph_node_id_on_every_placemark(conn):
    """Контракт 2.11.0+: формула 04 для узла КН — сам КН."""
    for placemark in _placemarks(K.build_kml(conn)):
        data = {d.get("name"): d.find("k:value", NS).text
                for d in placemark.findall("k:ExtendedData/k:Data", NS)}
        assert re.fullmatch(r"[A-Za-z0-9_:/-]{1,256}", data["graph_node_id"])
        assert data["graph_node_id"] == data["cad_number"]


def test_empty_folders_are_not_created(conn):
    """§A.3: пустые папки не создаются. Земля есть — папка одна."""
    names = [f.find("k:name", NS).text for f in _doc(K.build_kml(conn)).findall("k:Folder", NS)]
    assert len(names) == 1
    assert names[0].startswith("Земельные участки (")


def test_deterministic_output(conn):
    """§6: два прогона на одном входе дают побитово одинаковый файл."""
    first = K.build_kml(conn, generated_on="2026-09-12")
    second = K.build_kml(conn, generated_on="2026-09-12")
    assert first == second


# --- содержание -----------------------------------------------------------

def test_parts_are_separate_placemarks(conn):
    kml = K.build_kml(conn, with_parts=True)
    descriptions = [_text(p, "description") for p in _placemarks(kml)]
    assert any("Часть участка: " in d for d in descriptions)
    assert any("Площадь: " in d for d in descriptions)
    # У части — своя площадь под своим ключом, чтобы её нельзя было спутать
    # с площадью участка и сложить.
    assert all(not ("Площадь: " in d and "Часть участка: " in d) for d in descriptions)


def test_parts_can_be_excluded(conn):
    with_parts = len(_placemarks(K.build_kml(conn, with_parts=True)))
    without = len(_placemarks(K.build_kml(conn, with_parts=False)))
    assert without == with_parts - 1


def test_filter_by_cad_number(conn):
    assert _placemarks(K.build_kml(conn, cad_number="26:29:000000:1")) == []
    assert _placemarks(K.build_kml(conn, cad_number="26:29:130106:382"))


def test_extract_date_in_document_extended_data(conn, tmp_path):
    xml = land_xml().replace(
        "<extract_about_property_land>",
        "<extract_about_property_land><details_statement><group_top_requisites>"
        "<registration_number>КУВИ-001/2026-1</registration_number>"
        "<date_formation>2026-09-07</date_formation>"
        "</group_top_requisites></details_statement>")
    path = tmp_path / "dated.xml"
    path.write_text(xml, encoding="utf-8")
    W.write_geometry(conn, extract_geometry(path))
    doc = _doc(K.build_kml(conn))
    data = {d.get("name"): d.find("k:value", NS).text
            for d in doc.findall("k:ExtendedData/k:Data", NS)}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["extract_date"])


def test_area_is_not_mangled_by_trailing_zero_strip():
    """Регресс: `15120` не должен превращаться в `1512` при обрезке нулей."""
    assert K._num(15120.0, 0) == "15120"
    assert K._num(8030.0, 0) == "8030"
    assert K._num(4415.63, 1) == "4415.6"


def test_semicolon_inside_value_is_escaped():
    """Точка с запятой внутри значения ломает разбор пар у вьюера."""
    assert K._kv([("Адрес", "ул. Ленина; д. 5")]) == "Адрес: ул. Ленина, д. 5;"


def test_empty_db_gives_document_without_placemarks():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE egrn_contour (cad_number TEXT, kind TEXT, contour_no INT, "
        "contour_cad TEXT, part_number TEXT, part_mnemonic TEXT, geom_geojson TEXT, "
        "area_computed_sqm REAL, area_declared_sqm REAL, accuracy_m REAL, sk_id TEXT, "
        "msk_zone TEXT, source TEXT, source_extract_number TEXT, source_file TEXT, "
        "extract_date TEXT);")
    kml = K.build_kml(connection)
    ET.fromstring(kml)
    assert "<Placemark>" not in kml
    connection.close()
