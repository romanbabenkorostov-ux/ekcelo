"""tests/test_land_layout.py — детектор ЗУ/ЕЗП/МКУ (ADR-005)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import land_layout as L  # noqa: E402


def test_zu_single_contour():
    assert L.detect_land_layout(cad_number="23:50:0301004:25", contours_count=1) == "ЗУ"
    assert L.detect_land_layout(cad_number="23:50:0301004:25") == "ЗУ"


def test_ezp_by_marker():
    assert L.detect_land_layout(
        name="Единое землепользование", contours_count=3) == "ЕЗП"


def test_ezp_by_child_cads():
    assert L.detect_land_layout(
        cad_number="23:50:0000000:10", child_cads=["23:50:0301004:25",
                                                   "23:50:0301004:26"]) == "ЕЗП"


def test_mku_multi_contour_no_children():
    assert L.detect_land_layout(cad_number="23:50:0301004:100",
                                contours_count=2) == "МКУ"


def test_ezp_wins_over_mku_when_children_present():
    # несколько контуров И дочерние КН → ЕЗП (двухуровневая структура)
    assert L.detect_land_layout(contours_count=3,
                                child_cads=["a", "b"]) == "ЕЗП"


def test_detect_from_land_object_geojson():
    obj = {"cad_number": "x", "geom": {"type": "MultiPolygon",
                                       "coordinates": [[[]], [[]]]}}
    assert L.detect_from_land_object(obj) == "МКУ"
    obj1 = {"cad_number": "x", "geom": {"type": "Polygon", "coordinates": [[]]}}
    assert L.detect_from_land_object(obj1) == "ЗУ"
    obj2 = {"cad_number": "x", "name": "… (Единое землепользование)",
            "полигонов": 4}
    assert L.detect_from_land_object(obj2) == "ЕЗП"


def test_techcard_stub_raises():
    from egrn_parser.parsers import agro_techcard
    import pytest
    with pytest.raises(NotImplementedError, match="образец"):
        agro_techcard.parse_techcard("nope.xlsx")
