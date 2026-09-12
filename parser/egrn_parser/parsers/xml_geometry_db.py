"""
egrn_parser/parsers/xml_geometry_db.py — запись контуров из выписки в БД (ADR-007).

ЧТО ЗДЕСЬ ПРОИСХОДИТ. `xml_geometry.extract_geometry` возвращает контуры, этот
модуль кладёт их в три места, и у каждого своя роль:

  1. `egrn_contour` (§8, миграция 0006) — ИСТОЧНИК. По строке на контур, со
     всеми признаками выписки: номер части, мнемоника ЧЗУ, заявленная
     погрешность, исходный `sk_id`, номер выписки. Отсюда строится KML и эссе.
  2. `object_geometries` — ВИТРИНА для того, что уже написано. Её читают
     `xlsx_exporter` (geom_wkt) и `graph_json`; чтобы контур из выписки попал в
     существующие выгрузки, ничего в них менять не нужно — достаточно, чтобы
     строка там появилась.
  3. `land_contours` (ADR-005) — раскладка ЗУ/МКУ/ЕЗП. Пишется через уже
     существующий `land_db.upsert_geometry_contours`, который сам решает, не
     понижает ли новая геометрия известный ЕЗП до МКУ.

Пунктов 2 и 3 может не быть: `land_contours` и `object_geometries` живут в
схеме парсера, а миграцию 0006 применяют и к базам, где этих таблиц нет.
Отсутствие таблицы — не ошибка, а отсутствие витрины; писатель это молча
переживает и сообщает в отчёте, куда он на самом деле написал.

ГЛАВНОЕ ПРАВИЛО: НЕ СОШЛАСЬ ПЛОЩАДЬ — НЕ ПИШЕМ. Неверные параметры зоны МСК
не дают исключения, они дают правдоподобный контур не в том месте (ADR-007 §2).
Единственный признак, ловящий это без внешних источников, — расхождение
вычисленной площади с заявленной в той же выписке. Поэтому `strict=True` по
умолчанию: запись отклоняется, причина возвращается текстом. Снять гейт
(`strict=False`) может человек, который посмотрел на расхождение и решил, что
оно объяснимо — но не автоматический прогон.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from egrn_parser.parsers import land_db as _land_db
from egrn_parser.parsers.xml_geometry import Contour, ExtractGeometry

log = logging.getLogger(__name__)

__all__ = ["ensure_schema", "write_geometry", "MIGRATION_PATH"]

# Миграция лежит в schema/migrations и является источником правды для DDL.
# Дублировать её текст здесь нельзя: два определения таблицы расходятся на
# первой же правке. Путь вычисляется от файла модуля вверх до корня репозитория.
MIGRATION_PATH = (Path(__file__).resolve().parents[3]
                  / "schema" / "migrations" / "0006_egrn_geometry.sql")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone() is not None


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Применить миграцию 0006, если таблицы §8 ещё нет.

    DDL читается из файла миграции, а не повторяется строкой в коде: второе
    определение той же таблицы разъезжается с первым на ближайшей правке.
    """
    if _has_table(conn, "egrn_contour"):
        return
    if not MIGRATION_PATH.exists():
        raise FileNotFoundError(
            f"не найдена миграция {MIGRATION_PATH} — без неё таблицу egrn_contour "
            "создать нечем; проверь, что парсер запущен из дерева репозитория")
    conn.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _rows_for(geometry: ExtractGeometry, *, extract_number: Optional[str],
              extract_date: Optional[str]) -> list[tuple]:
    """`ExtractGeometry` → строки `egrn_contour`.

    Нумерация `contour_no` идёт от 1 отдельно для контуров участка и отдельно
    внутри каждой части: это и есть ключ идемпотентности, и он обязан не
    зависеть от порядка, в котором вызывающий обходит списки.
    """
    assert geometry.zone is not None       # проверено вызывающим
    zone = geometry.zone
    rows: list[tuple] = []

    def add(contour: Contour, kind: str, contour_no: int) -> None:
        centroid = contour.centroid_wgs84(zone)
        outer = contour.outer
        rows.append((
            geometry.cad_number,
            kind,
            contour_no,
            contour.cad_number if kind == "parcel" else None,
            contour.part_number,
            contour.part_mnemonic,
            json.dumps(contour.to_geojson(zone), ensure_ascii=False,
                       separators=(",", ":"), sort_keys=True),
            round(contour.area_sqm(), 2),
            contour.declared_area_sqm if kind == "part" else geometry.declared_area_sqm,
            outer.accuracy_m if outer else None,
            contour.sk_id or geometry.sk_id,
            zone.key,
            centroid[0] if centroid else None,
            centroid[1] if centroid else None,
            "egrn_xml",
            extract_number,
            geometry.source_file,
            extract_date,
        ))

    for i, contour in enumerate(geometry.contours, 1):
        add(contour, "parcel", i)

    per_part: dict[str, int] = {}
    for contour in geometry.parts:
        key = contour.part_number or ""
        per_part[key] = per_part.get(key, 0) + 1
        add(contour, "part", per_part[key])

    return rows


_INSERT = """
INSERT INTO egrn_contour
    (cad_number, kind, contour_no, contour_cad, part_number, part_mnemonic,
     geom_geojson, area_computed_sqm, area_declared_sqm, accuracy_m,
     sk_id, msk_zone, centroid_lon, centroid_lat,
     source, source_extract_number, source_file, extract_date)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (cad_number, kind, COALESCE(part_number, ''), contour_no)
DO UPDATE SET
    contour_cad           = excluded.contour_cad,
    part_mnemonic         = excluded.part_mnemonic,
    geom_geojson          = excluded.geom_geojson,
    area_computed_sqm     = excluded.area_computed_sqm,
    area_declared_sqm     = excluded.area_declared_sqm,
    accuracy_m            = excluded.accuracy_m,
    sk_id                 = excluded.sk_id,
    msk_zone              = excluded.msk_zone,
    centroid_lon          = excluded.centroid_lon,
    centroid_lat          = excluded.centroid_lat,
    -- Реквизиты документа склеиваются через COALESCE, а не перезаписываются:
    -- повторный разбор того же файла без явно переданного номера выписки НЕ
    -- должен стирать уже известный номер. Тот же приём в land_db.upsert_contours.
    source_extract_number = COALESCE(excluded.source_extract_number,
                                     egrn_contour.source_extract_number),
    source_file           = COALESCE(excluded.source_file, egrn_contour.source_file),
    extract_date          = COALESCE(excluded.extract_date, egrn_contour.extract_date),
    captured_at           = datetime('now')
"""


def _polygon_wkt(multipolygon: dict) -> str:
    """GeoJSON MultiPolygon → WKT.

    `object_geometries.geom_wkt` читают `xlsx_exporter` и `graph_json`; формат
    там — строка WKT, и городить ради неё зависимость от shapely незачем.
    """
    polys = []
    for polygon in multipolygon["coordinates"]:
        rings = ", ".join(
            "(" + ", ".join(f"{lon} {lat}" for lon, lat in ring) + ")"
            for ring in polygon)
        polys.append(f"({rings})")
    return "MULTIPOLYGON (" + ", ".join(polys) + ")"


def _mirror_object_geometries(conn: sqlite3.Connection, geometry: ExtractGeometry,
                              geojson: dict, area_sqm: float) -> bool:
    """Витрина `object_geometries`: одна строка на (КН, источник)."""
    if not _has_table(conn, "object_geometries"):
        return False
    conn.execute(
        """INSERT INTO object_geometries
               (object_class, cad_number, geom_type, geom_source, geom_geojson,
                geom_wkt, crs, area_geom_sqm, is_current)
           VALUES (?, ?, ?, 'egrn_xml', ?, ?, 'EPSG:4326', ?, 1)
           ON CONFLICT(cad_number, geom_source) DO UPDATE SET
               geom_type     = excluded.geom_type,
               geom_geojson  = excluded.geom_geojson,
               geom_wkt      = excluded.geom_wkt,
               area_geom_sqm = excluded.area_geom_sqm,
               obtained_at   = datetime('now'),
               is_current    = 1""",
        ("land", geometry.cad_number, geojson["type"],
         json.dumps(geojson, ensure_ascii=False, separators=(",", ":"),
                    sort_keys=True),
         _polygon_wkt(geojson), round(area_sqm, 2)))
    return True


def write_geometry(conn: sqlite3.Connection, geometry: ExtractGeometry, *,
                   extract_number: Optional[str] = None,
                   extract_date: Optional[str] = None,
                   strict: bool = True) -> dict[str, Any]:
    """Записать геометрию выписки. Возвращает отчёт, исключений не бросает.

    `extract_number` / `extract_date` по умолчанию берутся из самой выписки
    (`details_statement`); аргументы нужны лишь тогда, когда геометрия пришла
    не из файла, а собрана вызывающим.

    `strict=False` пишет даже при несошедшейся площади — осознанное решение
    человека, а не режим автоматического прогона (см. преамбулу).
    """
    extract_number = extract_number or geometry.extract_number
    extract_date = extract_date or geometry.extract_date
    report: dict[str, Any] = {
        "cad_number": geometry.cad_number,
        "written": False,
        "skipped": None,
        "contours": 0,
        "parts": 0,
        "mirrored": [],
        "area_check": None,
    }

    if not geometry.has_geometry:
        report["skipped"] = (
            "в выписке нет геометрии"
            + (f"; объект привязан к земле: {', '.join(geometry.land_cad_numbers)}"
               if geometry.land_cad_numbers else ""))
        return report

    if geometry.zone is None:
        report["skipped"] = geometry.zone_error or "система координат не определена"
        return report

    if not geometry.cad_number:
        report["skipped"] = "в выписке нет кадастрового номера — писать не к чему"
        return report

    check = geometry.area_check()
    report["area_check"] = check.describe()
    if not check.ok:
        if strict:
            report["skipped"] = (
                f"{check.describe()}. Расхождение такого размера означает неверные "
                f"параметры зоны {geometry.zone.key} либо перепутанные оси — "
                "запись отклонена (strict=True)")
            return report
        log.warning("%s: %s — пишем по явному указанию (strict=False)",
                    geometry.cad_number, check.describe())

    ensure_schema(conn)
    rows = _rows_for(geometry, extract_number=extract_number,
                     extract_date=extract_date)
    conn.executemany(_INSERT, rows)

    geojson = geometry.to_geojson()
    if geojson is not None and _mirror_object_geometries(
            conn, geometry, geojson, check.computed_sqm):
        report["mirrored"].append("object_geometries")

    if geojson is not None:
        # Через существующий путь ADR-005: он сам классифицирует ЗУ/МКУ и не
        # понижает уже известный ЕЗП. Свою логику раскладки здесь заводить
        # нельзя — она разъедется с той. Наличие `land_contours` не проверяется:
        # таблица не описана в db/schema.sql, её штатно создаёт
        # `land_db.ensure_schema` при первой записи.
        _land_db.upsert_geometry_contours(
            conn, geometry.cad_number, geojson, source="egrn_xml")
        report["mirrored"].append("land_contours")

    conn.commit()
    report["written"] = True
    report["contours"] = len(geometry.contours)
    report["parts"] = len(geometry.parts)
    return report
