"""Unit-tests для `kml_apply_nspd_contours.py`.

Главные инварианты:
  - Полигон Placemark'а заменяется, только если КН найден в description
    И contours.json несёт для него пригодную (wfs/pkk/ol_state/...) геометрию.
  - Placemark без КН в description, без записи в contours.json, или с
    непригодным источником (screenshot_cv/нет geojson) — не трогается.
  - name/description/styleUrl не меняются.
  - Один КН на нескольких Placemark'ах (ЕЗ, sql/02 в VineInvent — тот же
    случай) — заменяются ВСЕ совпадения, не только первое.
"""
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kml_apply_nspd_contours.py"
spec = importlib.util.spec_from_file_location("kml_apply_nspd_contours", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["kml_apply_nspd_contours"] = mod
spec.loader.exec_module(mod)

NS = {"k": "http://www.opengis.net/kml/2.2"}

KML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Поле A</name><description>Поле 23:15:0000000:2267 · Шардоне</description>
  <styleUrl>#green</styleUrl>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>0,0,0 1,0,0 1,1,0 0,1,0 0,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>Поле A (второй контур ЕЗ)</name>
  <description>Поле 23:15:0000000:2267 · второй контур</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>2,0,0 3,0,0 3,1,0 2,1,0 2,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>Без контура в реестре</name>
  <description>Поле 23:15:9999999:1</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>5,0,0 6,0,0 6,1,0 5,1,0 5,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>CV-fallback без геореференса</name>
  <description>Поле 23:15:0303000:1130</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>7,0,0 8,0,0 8,1,0 7,1,0 7,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>Без КН вообще</name>
  <description>Просто площадка, без кадастра</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>9,0,0 10,0,0 10,1,0 9,1,0 9,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>Точка-объект</name>
  <Point><coordinates>0.5,0.5,0</coordinates></Point>
</Placemark>
</Document></kml>
"""

CONTOURS = {
    "schema_version": "1.0",
    "objects": {
        "23:15:0000000:2267": {
            "источник": "wfs",
            "geojson": {"type": "Polygon", "coordinates": [[[10.0, 20.0], [10.1, 20.0], [10.1, 20.1], [10.0, 20.1], [10.0, 20.0]]]},
        },
        "23:15:0303000:1130": {
            "источник": "screenshot_cv",
            "geojson": None,
        },
    },
}


@pytest.fixture
def kml_path(tmp_path: Path) -> Path:
    p = tmp_path / "in.kml"
    p.write_text(KML_TEMPLATE, encoding="utf-8")
    return p


def _placemark_by_name(root, name):
    for pm in root.findall(".//k:Placemark", NS):
        n = pm.find("k:name", NS)
        if n is not None and n.text == name:
            return pm
    raise AssertionError(f"Placemark {name!r} не найден")


def test_replaces_polygon_when_wfs_contour_available(kml_path):
    tree, report = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "Поле A")
    coords = pm.find(".//k:coordinates", NS).text
    assert "10.0,20.0" in coords
    assert ("23:15:0000000:2267", "wfs") in report["replaced"]


def test_replaces_all_placemarks_sharing_same_cadastre_number(kml_path):
    """ЕЗ (единое землепользование) — несколько Placemark на один КН."""
    tree, report = mod.apply_contours(kml_path, CONTOURS)
    second = _placemark_by_name(tree.getroot(), "Поле A (второй контур ЕЗ)")
    coords = second.find(".//k:coordinates", NS).text
    assert "10.0,20.0" in coords
    assert report["replaced"].count(("23:15:0000000:2267", "wfs")) == 2


def test_preserves_name_description_style(kml_path):
    tree, _ = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "Поле A")
    assert pm.find("k:description", NS).text == "Поле 23:15:0000000:2267 · Шардоне"
    assert pm.find("k:styleUrl", NS).text == "#green"


def test_skips_cn_missing_from_contours_json(kml_path):
    tree, report = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "Без контура в реестре")
    coords = pm.find(".//k:coordinates", NS).text
    assert coords.strip() == "5,0,0 6,0,0 6,1,0 5,1,0 5,0,0"
    assert "23:15:9999999:1" in report["no_contour"]


def test_skips_screenshot_cv_source_without_geojson(kml_path):
    tree, report = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "CV-fallback без геореференса")
    coords = pm.find(".//k:coordinates", NS).text
    assert coords.strip() == "7,0,0 8,0,0 8,1,0 7,1,0 7,0,0"
    assert ("23:15:0303000:1130", "screenshot_cv") in report["bad_source"]


def test_skips_placemark_without_cadastre_number(kml_path):
    tree, report = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "Без КН вообще")
    coords = pm.find(".//k:coordinates", NS).text
    assert coords.strip() == "9,0,0 10,0,0 10,1,0 9,1,0 9,0,0"
    assert report["no_cn"] == 1


def test_point_placemarks_untouched(kml_path):
    tree, _ = mod.apply_contours(kml_path, CONTOURS)
    pm = _placemark_by_name(tree.getroot(), "Точка-объект")
    assert pm.find("k:Point", NS) is not None
    assert pm.find("k:Polygon", NS) is None


def test_multipolygon_geojson(kml_path):
    contours = {
        "objects": {
            "23:15:0000000:2267": {
                "источник": "wfs",
                "geojson": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
                        [[[2.0, 2.0], [3.0, 2.0], [3.0, 3.0], [2.0, 2.0]]],
                    ],
                },
            },
        },
    }
    tree, report = mod.apply_contours(kml_path, contours)
    pm = _placemark_by_name(tree.getroot(), "Поле A")
    assert pm.find("k:MultiGeometry", NS) is not None
    assert len(pm.findall(".//k:Polygon", NS)) == 2


def test_list_cadastre_numbers_unique_sorted(kml_path):
    cns = mod.list_cadastre_numbers(kml_path)
    # 4 полигона с КН в фикстуре, один КН дублируется (ЕЗ) → 3 уникальных.
    assert cns == sorted(set(cns))
    assert cns == ["23:15:0000000:2267", "23:15:0303000:1130", "23:15:9999999:1"]


def test_main_missing_contours_json_gives_actionable_error(kml_path, tmp_path, capsys):
    missing = tmp_path / "_data" / "contours.json"
    rc = mod.main(["--kml", str(kml_path), "--contours", str(missing),
                   "--out", str(tmp_path / "out.kml")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "01_parsing_nspd_v8.py" in err
    assert "01b_ingest_contours.py" in err
    assert "--list-cadastre-numbers" in err


def test_main_list_cadastre_numbers_mode_needs_no_contours_arg(kml_path, capsys):
    rc = mod.main(["--kml", str(kml_path), "--list-cadastre-numbers"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "23:15:0000000:2267" in out
