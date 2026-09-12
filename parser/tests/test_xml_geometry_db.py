"""tests/test_xml_geometry_db.py — запись контуров выписки в БД (ADR-007, §8).

Фикстуры синтетические: структура тегов как в выписках Роскадастра, координаты
и площади из реальных выписок, персональных данных нет.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import xml_geometry_db as W          # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry  # noqa: E402
from tests.test_xml_geometry import BUILD_XML, land_xml       # noqa: E402

PARSER_SCHEMA = Path(__file__).parent.parent / "egrn_parser" / "db" / "schema.sql"


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Пустая БД: только §8 из миграции, без схемы парсера.

    Так проверяется, что писатель не падает там, где витрин
    (`object_geometries`) нет — миграцию 0006 применяют и к таким базам.
    """
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def parser_conn() -> sqlite3.Connection:
    """БД со схемой парсера — есть куда зеркалить."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(PARSER_SCHEMA.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def _geometry(tmp_path: Path, xml: str, name: str = "extract.xml"):
    path = tmp_path / name
    path.write_text(xml, encoding="utf-8")
    return extract_geometry(path)


def _rows(connection, sql: str, *args):
    return connection.execute(sql, args).fetchall()


# --- запись ---------------------------------------------------------------

def test_writes_parcel_and_parts(conn, tmp_path):
    report = W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    assert report["written"]
    assert report["contours"] == 1
    assert report["parts"] == 1
    kinds = dict(_rows(conn, "SELECT kind, COUNT(*) FROM egrn_contour GROUP BY kind"))
    assert kinds == {"parcel": 1, "part": 1}


def test_migration_applied_on_demand(conn, tmp_path):
    """Таблицы §8 нет — писатель применяет миграцию сам, а не падает."""
    assert not _rows(conn, "SELECT 1 FROM sqlite_master WHERE name='egrn_contour'")
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    assert _rows(conn, "SELECT 1 FROM sqlite_master WHERE name='egrn_contour'")


def test_geometry_is_valid_geojson_polygon(conn, tmp_path):
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    raw = _rows(conn, "SELECT geom_geojson FROM egrn_contour WHERE kind='parcel'")[0][0]
    geom = json.loads(raw)
    assert geom["type"] == "Polygon"
    ring = geom["coordinates"][0]
    assert ring[0] == ring[-1], "GeoJSON требует замкнутого кольца"
    lon, lat = ring[0]
    assert 42.7 < lon < 42.9 and 43.9 < lat < 44.1


def test_requisites_taken_from_extract(conn, tmp_path):
    """Номер и дата выписки лежат в том же XML — вызывающий их не подставляет."""
    xml = land_xml().replace(
        "<extract_about_property_land>",
        "<extract_about_property_land><details_statement><group_top_requisites>"
        "<registration_number>КУВИ-001/2026-120869336</registration_number>"
        "<date_formation>2026-09-07</date_formation>"
        "</group_top_requisites></details_statement>")
    W.write_geometry(conn, _geometry(tmp_path, xml))
    row = _rows(conn, "SELECT source_extract_number, extract_date FROM egrn_contour LIMIT 1")[0]
    assert row == ("КУВИ-001/2026-120869336", "2026-09-07")


def test_accuracy_and_zone_stored(conn, tmp_path):
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    row = _rows(conn, "SELECT accuracy_m, msk_zone, sk_id, crs FROM egrn_contour "
                      "WHERE kind='parcel'")[0]
    assert row[0] == 2.5
    assert row[1] == "мск-26-з1"
    assert "МСК-26" in row[2]
    assert row[3] == "EPSG:4326"


# --- идемпотентность ------------------------------------------------------

def test_second_run_does_not_duplicate(conn, tmp_path):
    geometry = _geometry(tmp_path, land_xml())
    W.write_geometry(conn, geometry)
    W.write_geometry(conn, geometry)
    assert _rows(conn, "SELECT COUNT(*) FROM egrn_contour")[0][0] == 2


def test_rerun_keeps_known_extract_number(conn, tmp_path):
    """Повтор без реквизитов не должен стирать уже известный номер выписки."""
    geometry = _geometry(tmp_path, land_xml())
    W.write_geometry(conn, geometry, extract_number="КУВИ-001/2026-1", extract_date="2026-09-07")
    W.write_geometry(conn, geometry)
    row = _rows(conn, "SELECT source_extract_number, extract_date FROM egrn_contour LIMIT 1")[0]
    assert row == ("КУВИ-001/2026-1", "2026-09-07")


# --- гейт по площади ------------------------------------------------------

def test_area_mismatch_is_refused_by_default(conn, tmp_path):
    """Главный предохранитель: несошедшаяся площадь = неверная зона МСК."""
    report = W.write_geometry(conn, _geometry(tmp_path, land_xml(area="9000")))
    assert not report["written"]
    assert "НЕ СХОДИТСЯ" in report["skipped"]
    assert "мск-26-з1" in report["skipped"]
    assert not _rows(conn, "SELECT 1 FROM sqlite_master WHERE name='egrn_contour'")


def test_area_mismatch_can_be_forced(conn, tmp_path):
    report = W.write_geometry(conn, _geometry(tmp_path, land_xml(area="9000")),
                              strict=False)
    assert report["written"]
    assert _rows(conn, "SELECT COUNT(*) FROM egrn_contour")[0][0] == 2


# --- случаи, когда писать нечего ------------------------------------------

def test_building_is_skipped_with_land_link(conn, tmp_path):
    report = W.write_geometry(conn, _geometry(tmp_path, BUILD_XML))
    assert not report["written"]
    assert "нет геометрии" in report["skipped"]
    assert "26:29:130106:72" in report["skipped"]


def test_unknown_zone_is_skipped_with_reason(conn, tmp_path):
    xml = land_xml(sk_id="МСК-77 от СК-95, зона 3")
    report = W.write_geometry(conn, _geometry(tmp_path, xml))
    assert not report["written"]
    assert "мск-77-з3" in report["skipped"]


# --- витрины --------------------------------------------------------------

def test_mirrors_into_object_geometries(parser_conn, tmp_path):
    report = W.write_geometry(parser_conn, _geometry(tmp_path, land_xml()))
    assert "object_geometries" in report["mirrored"]
    row = _rows(parser_conn,
                "SELECT geom_type, geom_source, crs, area_geom_sqm, geom_wkt "
                "FROM object_geometries")[0]
    assert row[0] == "MultiPolygon"
    assert row[1] == "egrn_xml"
    assert row[2] == "EPSG:4326"
    assert row[3] == pytest.approx(1985.6, abs=0.5)
    assert row[4].startswith("MULTIPOLYGON (((")


def test_mirror_into_object_geometries_is_idempotent(parser_conn, tmp_path):
    geometry = _geometry(tmp_path, land_xml())
    W.write_geometry(parser_conn, geometry)
    W.write_geometry(parser_conn, geometry)
    assert _rows(parser_conn, "SELECT COUNT(*) FROM object_geometries")[0][0] == 1


def test_mirrors_into_land_contours(conn, tmp_path):
    """`land_contours` не описана в db/schema.sql — её создаёт land_db сам."""
    report = W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    assert "land_contours" in report["mirrored"]
    assert _rows(conn, "SELECT COUNT(*) FROM land_contours")[0][0] == 1


def test_missing_showcase_is_not_an_error(conn, tmp_path):
    """Базы без схемы парсера — штатный случай, а не сбой."""
    report = W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    assert report["written"]
    assert "object_geometries" not in report["mirrored"]


# --- представления --------------------------------------------------------

def test_parcel_view_excludes_parts(conn, tmp_path):
    """Площадь лота не должна включать ЧЗУ — ради этого и заведено представление."""
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    assert _rows(conn, "SELECT COUNT(*) FROM v_egrn_parcel_contour")[0][0] == 1
    total = _rows(conn, "SELECT SUM(area_computed_sqm) FROM v_egrn_parcel_contour")[0][0]
    assert total == pytest.approx(1985.6, abs=0.5)


def test_summary_view_reports_area_check(conn, tmp_path):
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    row = _rows(conn, "SELECT contours, area_computed_sqm, area_declared_sqm, "
                      "accuracy_m, area_check_ok FROM v_egrn_geometry_summary")[0]
    assert row[0] == 1
    assert row[1] == pytest.approx(1985.6, abs=0.5)
    assert row[2] == 1986.0
    assert row[3] == 2.5
    assert row[4] == 1


def test_summary_flags_forced_mismatch(conn, tmp_path):
    """Запись с --force обязана остаться видимой как несошедшаяся."""
    W.write_geometry(conn, _geometry(tmp_path, land_xml(area="9000")), strict=False)
    assert _rows(conn, "SELECT area_check_ok FROM v_egrn_geometry_summary")[0][0] == 0


# --- канон и миграция не должны разъезжаться ------------------------------

def test_canonical_schema_mirrors_migration():
    """§8 в `schema/egrn_current_schema.sql` обязан совпадать с миграцией 0006.

    Канон объявлен «единым источником правды для Python + Frontend», а DDL
    физически написан дважды — в миграции и в каноне (так же устроен §7).
    Расхождение обнаружится не здесь, а на фронте через полгода, поэтому оно
    ловится тестом.
    """
    repo = Path(__file__).resolve().parents[2]
    canonical = sqlite3.connect(":memory:")
    migrated = sqlite3.connect(":memory:")
    try:
        canonical.executescript(
            (repo / "schema" / "egrn_current_schema.sql").read_text(encoding="utf-8"))
        migrated.executescript(W.MIGRATION_PATH.read_text(encoding="utf-8"))

        def columns(connection):
            return [(r[1], r[2], r[3], r[5])
                    for r in connection.execute("PRAGMA table_info(egrn_contour)")]

        assert columns(canonical) == columns(migrated)

        def objects(connection, kind):
            return sorted(r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type=? "
                "AND (name LIKE '%egrn_contour%' OR name LIKE 'v_egrn%')", (kind,)))

        assert objects(canonical, "view") == objects(migrated, "view")
        assert objects(canonical, "index") == objects(migrated, "index")
    finally:
        canonical.close()
        migrated.close()


# --- случай из выписки КУВИ-001/2026-120869334 (26:29:130106:73) -----------
# Участок 15 120 кв.м с СЕМЬЮ частями. Он вскрыл две ошибки, которых не было
# видно на участках с одной-двумя частями, поэтому вынесен в отдельные тесты.

def _many_parts_xml(count: int = 7, area: str = "1986") -> str:
    """Выписка с несколькими ЧЗУ; геометрия участка и частей — как в land_xml.

    Площадь оставлена согласованной с координатами намеренно: эти тесты про
    нумерацию и суммирование частей, и гейт по площади (проверенный отдельно)
    не должен их гасить.
    """
    from tests.test_xml_geometry import PART_POINTS, _spatial
    parts = "".join(
        f"<object_part><part_number>{n}</part_number>"
        f"<area><value>{59 + n}</value></area>"
        f"<contours><contour><number_pp>1</number_pp>"
        f"{_spatial(PART_POINTS + [PART_POINTS[0]], sk_id=None)}"
        f"</contour></contours></object_part>"
        for n in range(1, count + 1))
    return land_xml(area=area, with_part=False).replace(
        "</land_record>", f"<object_parts>{parts}</object_parts></land_record>")


def test_many_parts_each_get_own_row(conn, tmp_path):
    W.write_geometry(conn, _geometry(tmp_path, _many_parts_xml()))
    numbers = [r[0] for r in _rows(
        conn, "SELECT part_number FROM egrn_contour WHERE kind='part' "
              "ORDER BY CAST(part_number AS INTEGER)")]
    assert numbers == [str(n) for n in range(1, 8)]


def test_many_parts_do_not_inflate_parcel_area(conn, tmp_path):
    """Семь частей внутри участка не должны увеличить его площадь."""
    W.write_geometry(conn, _geometry(tmp_path, _many_parts_xml()))
    parcel = _rows(conn, "SELECT SUM(area_computed_sqm) FROM v_egrn_parcel_contour")[0][0]
    everything = _rows(conn, "SELECT SUM(area_computed_sqm) FROM egrn_contour")[0][0]
    assert parcel == pytest.approx(1985.6, abs=0.5)
    assert everything > parcel * 1.1, "проверка бессмысленна, если части пустые"


def test_parcel_contour_cad_is_not_the_parcel_itself(conn, tmp_path):
    """Росреестр дублирует КН участка внутри его же контура.

    Записанный как «обособленный участок», он превращает обычный ЗУ в мнимое
    единое землепользование — и участок начинает выглядеть как ЕЗП в каждом
    отчёте.
    """
    W.write_geometry(conn, _geometry(tmp_path, land_xml()))
    contour_cad = _rows(conn, "SELECT contour_cad FROM egrn_contour "
                              "WHERE kind='parcel'")[0][0]
    assert contour_cad is None
