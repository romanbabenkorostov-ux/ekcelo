"""
kml_apply_nspd_contours.py — заменяет полигоны в существующем KML на
контуры из НСПД (`_data/contours.json`, схема — ADR
`2026-05-25-contour-sidecar-architecture.md`, §6 «KMZ Polygon»).

В отличие от `08_build_kmz_*.py` (пересобирают KMZ проекта с нуля из
`structure.json`) — здесь входной KML УЖЕ есть (например, ручная разметка
площадок в Yandex Map Constructor, где кадастровый номер записан прямо в
`<description>` Placemark'а, а полигон — от руки, неточный). Задача —
точечно заменить геометрию только тех Placemark'ов, для которых нашёлся
кадастровый номер и есть пригодный контур в `contours.json`; всё
остальное (name, description, style, Point-плейсмарки, полигоны без
распознанного КН) остаётся как есть.

Кадастровый номер ищется в `<description>` регэкспом `\\d{1,2}:\\d{1,2}:
\\d{1,7}:\\d+` — тем же форматом, что ключи `contours.json`.

Это ТРЕТИЙ, финальный шаг конвейера — первые два (сбор контуров) нужно
выполнить ДО этого скрипта, локально, не в headless/сетеизолированной
среде:
    1. `01_parsing_nspd_v8.py` — интерактивный Playwright-скрейпер НСПД.
       Открывает видимый браузер (`headless=False`), спрашивает КН из
       stdin, ходит на nspd.gov.ru/pkk.rosreestr.ru. Не запускается там,
       где нет графического браузера и/или доступа к этим сайтам.
    2. `01b_ingest_contours.py --project <project>` — консолидирует вывод
       шага 1 в `<project>/_data/contours.json`.
    3. Этот скрипт — читает contours.json + существующий KML → пишет KML
       с заменёнными полигонами.

Usage:
    python parser/scripts/kml_apply_nspd_contours.py \\
        --kml исходный.kml --contours _data/contours.json --out результат.kml
    python parser/scripts/kml_apply_nspd_contours.py ... --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)

CN_RE = re.compile(r"\d{1,2}:\d{1,2}:\d{1,7}:\d+")

# Источники, дающие настоящие WGS84-координаты объекта (не CV-fallback без
# геореференса) — та же граница, что ADR §6 «KMZ Polygon», п.2/3.
WGS84_SOURCES = {"wfs", "pkk", "ol_state", "network_capture", "manual"}


def _q(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _cadastre_in_description(placemark: ET.Element) -> str | None:
    desc_el = placemark.find(_q("description"))
    if desc_el is None or not desc_el.text:
        return None
    m = CN_RE.search(desc_el.text)
    return m.group(0) if m else None


def _ring_coords_text(ring: list) -> str:
    # GeoJSON ring: [[lon, lat], ...] → KML "lon,lat,0 lon,lat,0 ..."
    return " ".join(f"{pt[0]},{pt[1]},0" for pt in ring)


def _one_polygon(coordinates: list) -> ET.Element:
    # GeoJSON Polygon coordinates: [outer_ring, hole1, hole2, ...]
    polygon = ET.Element(_q("Polygon"))
    outer = ET.SubElement(polygon, _q("outerBoundaryIs"))
    outer_ring = ET.SubElement(outer, _q("LinearRing"))
    ET.SubElement(outer_ring, _q("coordinates")).text = _ring_coords_text(coordinates[0])
    for hole in coordinates[1:]:
        inner = ET.SubElement(polygon, _q("innerBoundaryIs"))
        inner_ring = ET.SubElement(inner, _q("LinearRing"))
        ET.SubElement(inner_ring, _q("coordinates")).text = _ring_coords_text(hole)
    return polygon


def _build_geometry_element(geojson: dict) -> ET.Element:
    geom_type = geojson.get("type")
    if geom_type == "Polygon":
        return _one_polygon(geojson["coordinates"])
    if geom_type == "MultiPolygon":
        multi = ET.Element(_q("MultiGeometry"))
        for poly_coords in geojson["coordinates"]:
            multi.append(_one_polygon(poly_coords))
        return multi
    raise ValueError(f"неизвестный тип геометрии: {geom_type}")


def apply_contours(kml_path: Path, contours: dict) -> tuple[ET.ElementTree, dict]:
    tree = ET.parse(kml_path)
    root = tree.getroot()
    objects = contours.get("objects", {})

    report = {"replaced": [], "no_cn": 0, "no_contour": [], "bad_source": []}

    for placemark in root.iter(_q("Placemark")):
        # Точечные Placemark'и не трогаем — заменяем геометрию только там,
        # где сейчас Polygon/MultiGeometry (кадастровые поля из задания).
        old_geom = placemark.find(_q("Polygon"))
        old_tag = "Polygon"
        if old_geom is None:
            old_geom = placemark.find(_q("MultiGeometry"))
            old_tag = "MultiGeometry"
        if old_geom is None:
            continue

        cn = _cadastre_in_description(placemark)
        if not cn:
            report["no_cn"] += 1
            continue
        entry = objects.get(cn)
        if not entry:
            report["no_contour"].append(cn)
            continue
        source = entry.get("источник")
        geojson = entry.get("geojson")
        if source not in WGS84_SOURCES or not geojson:
            report["bad_source"].append((cn, source))
            continue

        new_geom = _build_geometry_element(geojson)
        idx = list(placemark).index(old_geom)
        placemark.remove(old_geom)
        placemark.insert(idx, new_geom)
        report["replaced"].append((cn, source))

    return tree, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--kml", required=True, type=Path)
    ap.add_argument("--contours", required=True, type=Path, help="_data/contours.json")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.kml.exists():
        print(f"error: kml не найден: {args.kml}", file=sys.stderr)
        return 2
    if not args.contours.exists():
        print(f"error: contours.json не найден: {args.contours}", file=sys.stderr)
        return 2

    contours = json.loads(args.contours.read_text(encoding="utf-8"))
    tree, report = apply_contours(args.kml, contours)

    print(f"[i] заменено полигонов: {len(report['replaced'])}")
    for cn, src in report["replaced"]:
        print(f"    + {cn} (источник: {src})")
    if report["no_contour"]:
        print(f"[i] КН без записи в contours.json: {len(report['no_contour'])}")
        for cn in report["no_contour"]:
            print(f"    ? {cn}")
    if report["bad_source"]:
        print(f"[i] КН есть в contours.json, но геометрия непригодна "
              f"(screenshot_cv без геореференса / нет geojson): {len(report['bad_source'])}")
        for cn, src in report["bad_source"]:
            print(f"    x {cn} (источник: {src})")
    if report["no_cn"]:
        print(f"[i] Placemark с полигоном без распознанного КН в description: {report['no_cn']}")

    if args.dry_run:
        print("\n[dry-run] выходной файл не записан")
        return 0

    tree.write(args.out, encoding="UTF-8", xml_declaration=True)
    print(f"\n[+] записан {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
