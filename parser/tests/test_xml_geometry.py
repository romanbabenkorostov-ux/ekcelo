"""tests/test_xml_geometry.py — контуры из XML-выписки ЕГРН (ADR-007).

Фикстуры синтетические: структура тегов повторяет реальные выписки Роскадастра
(КУВИ-001/2026-120869336 и -120869307), координаты и площади взяты оттуда же,
а всё, что касается правообладателей, в фикстуры не переносилось вовсе.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import xml_geometry as G  # noqa: E402

SK_ID = "МСК-26, от СК -95, зона 1"

PARCEL_POINTS = [
    (360527.54, 1405241.74), (360530.35, 1405277.75), (360534.47, 1405306.95),
    (360539.28, 1405334.58), (360507.81, 1405358.07), (360507.70, 1405357.60),
    (360500.42, 1405327.05), (360523.89, 1405319.72), (360517.54, 1405296.21),
    (360513.34, 1405247.79),
]
PART_POINTS = [
    (360534.40, 1405306.46), (360534.47, 1405306.95), (360535.19, 1405311.06),
    (360532.95, 1405312.32), (360522.53, 1405314.68), (360521.38, 1405310.43),
    (360531.36, 1405308.17),
]


def _ordinates(points, *, accuracy="2.5", first_number=158) -> str:
    rows = []
    for i, (north, east) in enumerate(points, start=1):
        rows.append(
            f"<ordinate><ord_nmb>{i}</ord_nmb><x>{north}</x><y>{east}</y>"
            f"<num_geopoint>{first_number + i - 1}</num_geopoint>"
            f"<delta_geopoint>{accuracy}</delta_geopoint></ordinate>")
    return "".join(rows)


def _spatial(points, *, sk_id: str | None = SK_ID, **kw) -> str:
    sk = f"<sk_id>{sk_id}</sk_id>" if sk_id else ""
    return (f"<entity_spatial>{sk}<spatials_elements><spatial_element>"
            f"<ordinates>{_ordinates(points, **kw)}</ordinates>"
            f"</spatial_element></spatials_elements></entity_spatial>")


def land_xml(*, cad="26:29:130106:382", area="1986", inaccuracy="390",
             sk_id: str | None = SK_ID, with_part=True, closed=True) -> str:
    points = PARCEL_POINTS + ([PARCEL_POINTS[0]] if closed else [])
    part = ""
    if with_part:
        part = (
            "<object_parts><object_part><part_number>1</part_number>"
            "<mnemonic>26:29-6.395-ЧЗУ1</mnemonic>"
            "<area><type><code>009</code><value>Уточнённая площадь</value></type>"
            "<value>59.29</value></area>"
            "<contours><contour><number_pp>1</number_pp>"
            f"{_spatial(PART_POINTS + [PART_POINTS[0]], sk_id=None)}"
            "</contour></contours></object_part></object_parts>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<extract_about_property_land><land_record>"
        f"<object><common_data><cad_number>{cad}</cad_number>"
        "<type><code>002001001000</code><value>Земельный участок</value></type>"
        "</common_data></object>"
        f"<params><area><value>{area}</value><inaccuracy>{inaccuracy}</inaccuracy>"
        "</area></params>"
        "<contours_location><contours><contour><number_pp>1</number_pp>"
        f"<cad_number>{cad}</cad_number>{_spatial(points, sk_id=sk_id)}"
        "</contour></contours></contours_location>"
        f"{part}</land_record></extract_about_property_land>")


BUILD_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<extract_about_property_build><build_record>"
    "<object><common_data><cad_number>26:29:110104:105</cad_number>"
    "<type><code>002001002000</code><value>Здание</value></type>"
    "</common_data></object>"
    "<cad_links><land_cad_numbers><land_cad_number>"
    "<cad_number>26:29:130106:72, 26:29:130322:7</cad_number>"
    "</land_cad_number></land_cad_numbers></cad_links>"
    "</build_record></extract_about_property_build>")


def _write(tmp_path: Path, xml: str, name: str = "extract.xml") -> Path:
    path = tmp_path / name
    path.write_text(xml, encoding="utf-8")
    return path


# --- участок --------------------------------------------------------------

def test_parcel_contour_is_read(tmp_path):
    geometry = G.extract_geometry(_write(tmp_path, land_xml()))
    assert geometry.object_type == "land"
    assert geometry.cad_number == "26:29:130106:382"
    assert geometry.has_geometry
    assert len(geometry.contours) == 1
    contour = geometry.contours[0]
    assert contour.kind == "parcel"
    assert contour.number_pp == "1"
    assert contour.rings[0].accuracy_m == 2.5
    assert contour.rings[0].is_closed


def test_area_check_matches_declared(tmp_path):
    """Главный приёмочный признак всего модуля."""
    check = G.extract_geometry(_write(tmp_path, land_xml())).area_check()
    assert check.ok
    assert abs(check.delta_sqm) < 1.0
    assert "сходится" in check.describe()


def test_area_check_catches_wrong_geometry(tmp_path):
    """Если координаты и заявленная площадь спорят — модуль обязан это сказать."""
    check = G.extract_geometry(_write(tmp_path, land_xml(area="9000"))).area_check()
    assert not check.ok
    assert "НЕ СХОДИТСЯ" in check.describe()


def test_area_check_without_declared_area_is_not_a_failure(tmp_path):
    xml = land_xml().replace("<value>1986</value>", "<value></value>")
    check = G.extract_geometry(_write(tmp_path, xml)).area_check()
    assert check.declared_sqm is None
    assert check.ok


def test_unclosed_ring_is_accepted(tmp_path):
    """Замыкающую точку выписка пишет не всегда — это не повод терять контур."""
    geometry = G.extract_geometry(_write(tmp_path, land_xml(closed=False)))
    ring = geometry.contours[0].rings[0]
    assert not ring.is_closed
    assert geometry.area_check().ok


# --- части участка (ЧЗУ) --------------------------------------------------

def test_parts_are_separate_from_parcel(tmp_path):
    """ЧЗУ не должны попадать в контуры участка — иначе площадь лота удвоится."""
    geometry = G.extract_geometry(_write(tmp_path, land_xml()))
    assert len(geometry.contours) == 1
    assert len(geometry.parts) == 1
    part = geometry.parts[0]
    assert part.kind == "part"
    assert part.part_number == "1"
    assert part.part_mnemonic == "26:29-6.395-ЧЗУ1"
    assert part.area_sqm() == pytest.approx(59.29, abs=0.5)
    # площадь участка считается без частей
    assert geometry.area_check().computed_sqm == pytest.approx(1985.6, abs=0.5)


def test_extract_without_parts(tmp_path):
    geometry = G.extract_geometry(_write(tmp_path, land_xml(with_part=False)))
    assert geometry.parts == []


# --- система координат ----------------------------------------------------

def test_zone_resolved_and_wgs84_produced(tmp_path):
    geometry = G.extract_geometry(_write(tmp_path, land_xml()))
    assert geometry.zone is not None
    assert geometry.zone_error is None
    rings = geometry.contours[0].to_wgs84_rings(geometry.zone)
    lon, lat = rings[0][0]
    assert 42.7 < lon < 42.9 and 43.9 < lat < 44.1


def test_unknown_zone_keeps_msk_coordinates(tmp_path):
    """Незнакомая зона не обнуляет разбор: метры МСК извлечены и полезны."""
    xml = land_xml(sk_id="МСК-77 от СК-95, зона 3")
    geometry = G.extract_geometry(_write(tmp_path, xml))
    assert geometry.zone is None
    assert geometry.zone_error and "мск-77-з3" in geometry.zone_error
    assert geometry.has_geometry
    assert geometry.area_check().ok


def test_missing_sk_id_is_reported(tmp_path):
    geometry = G.extract_geometry(_write(tmp_path, land_xml(sk_id=None)))
    assert geometry.sk_id is None
    assert geometry.zone is None
    assert geometry.zone_error


# --- ОКС ------------------------------------------------------------------

def test_building_has_no_geometry_but_links_to_land(tmp_path):
    """Выписка на здание геометрии не содержит — это штатно, а не сбой."""
    geometry = G.extract_geometry(_write(tmp_path, BUILD_XML))
    assert geometry.object_type == "build"
    assert not geometry.has_geometry
    assert geometry.contours == []
    assert geometry.land_cad_numbers == ["26:29:130106:72", "26:29:130322:7"]


def test_multi_cad_link_is_split(tmp_path):
    """Два КН в одном теге — два участка, а не одна строка."""
    geometry = G.extract_geometry(_write(tmp_path, BUILD_XML))
    assert len(geometry.land_cad_numbers) == 2


# --- вырожденные случаи ---------------------------------------------------

def test_degenerate_ring_is_dropped(tmp_path):
    """Кольцо из двух точек — не полигон; молча рисовать его нельзя."""
    xml = land_xml()
    head = xml.split("<ordinate><ord_nmb>3</ord_nmb>")[0]
    xml = head + "</ordinates></spatial_element></spatials_elements></entity_spatial>" \
                 "</contour></contours></contours_location></land_record>" \
                 "</extract_about_property_land>"
    geometry = G.extract_geometry(_write(tmp_path, xml))
    assert geometry.contours == []
    assert not geometry.has_geometry


def test_holes_are_subtracted(tmp_path):
    """Второй spatial_element — дырка; её площадь вычитается, а не прибавляется."""
    outer = _spatial(PARCEL_POINTS + [PARCEL_POINTS[0]])
    hole = ("<spatial_element><ordinates>"
            f"{_ordinates(PART_POINTS + [PART_POINTS[0]])}"
            "</ordinates></spatial_element>")
    xml = land_xml().replace("</spatial_element></spatials_elements>",
                             f"</spatial_element>{hole}</spatials_elements>", 1)
    assert outer  # фикстура собрана тем же генератором
    geometry = G.extract_geometry(_write(tmp_path, xml))
    contour = geometry.contours[0]
    assert len(contour.rings) == 2
    assert contour.area_sqm() < contour.rings[0].area_sqm()
