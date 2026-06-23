"""KML/KMZ → §7 import — CLI.

Импортирует Placemark'ы из KML файла в §7 (geo_entity + history + asset_geo_link)
по логике, согласованной в `obsidian/Database/geo-entities-7.md`.

Использование:
    python -m parser.exporters.etp.import_kml_geo_cli \
        --kml path/to/Олимп_15-06-2026.kml \
        --db ekcelo.sqlite \
        [--valid-from 2026-06-01]          # default: дата из имени файла
        [--asset-type object]              # default: object
        [--dry-run]                         # без записи, только подсчёт

Идемпотентность: повторный запуск с тем же `valid_from` пропускает
`asset_geo_link`, которые уже есть. `geo_entity` — добавляются всегда (история).
Это не идеальный режим — для строгой идемпотентности нужен natural key
(name + cad + valid_from), который добавится при первом проде. Пока — append-only.

См. также: `obsidian/Database/geo-entities-7.md` §«Workflow».
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from backend.app.services.geo import (
    add_contour, add_point, link_asset, register_geo,
)

KML_NS = "{http://www.opengis.net/kml/2.2}"
CAD_RE = re.compile(r"\d+:\d+:\d+:\d+")
HTML_RE = re.compile(r"<[^>]*>")
DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


@dataclass
class ImportStats:
    total: int = 0
    geo_created: int = 0
    contours: int = 0
    points: int = 0
    primary_links: int = 0
    secondary_links: int = 0
    unlinked: int = 0
    skipped_existing: int = 0


def description_label(desc: str) -> str:
    """Метка из description: до первого «·», без HTML, нормализованные пробелы."""
    first = desc.split("·")[0] if desc else ""
    return re.sub(r"\s+", " ", HTML_RE.sub(" ", first)).strip()


def extract_valid_from_from_filename(path: Path) -> str | None:
    """Извлекает дату DD-MM-YYYY из имени файла → ISO 'YYYY-MM-DD'."""
    m = DATE_RE.search(path.name)
    if m is None:
        return None
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def read_kml_text(path: Path) -> str:
    """KML — обычный текст. KMZ — zip с doc.kml внутри."""
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith(".kml"):
                    return z.read(name).decode("utf-8")
            raise ValueError(f"{path}: KMZ не содержит .kml внутри")
    return path.read_text(encoding="utf-8")


def parse_polygon(pm) -> dict | None:
    el = pm.find(f".//{KML_NS}Polygon//{KML_NS}coordinates")
    if el is None or not el.text:
        return None
    ring: list[list[float]] = []
    for tok in el.text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            ring.append([float(parts[0]), float(parts[1])])
    if len(ring) < 3:
        return None
    return {"type": "Polygon", "coordinates": [ring]}


def parse_point(pm) -> tuple[float, float] | None:
    el = pm.find(f".//{KML_NS}Point//{KML_NS}coordinates")
    if el is None or not el.text:
        return None
    parts = el.text.strip().split(",")
    if len(parts) >= 2:
        return float(parts[1]), float(parts[0])  # (lat, lon) — Yandex кладёт lon,lat
    return None


def _link_exists(conn: sqlite3.Connection, asset_type: str, asset_id: str,
                 role: str, valid_from: str) -> bool:
    """True, если у актива в эту дату уже есть линк той же роли."""
    row = conn.execute(
        "SELECT 1 FROM asset_geo_link WHERE asset_type=? AND asset_id=? "
        "AND role=? AND valid_from=? LIMIT 1",
        (asset_type, asset_id, role, valid_from),
    ).fetchone()
    return row is not None


def import_kml(
    conn: sqlite3.Connection,
    kml_text: str,
    valid_from: str,
    *,
    asset_type: str = "object",
    dry_run: bool = False,
) -> ImportStats:
    root = ET.fromstring(kml_text)
    pms = root.findall(f".//{KML_NS}Placemark")
    s = ImportStats(total=len(pms))

    for pm in pms:
        desc_el = pm.find(f"{KML_NS}description")
        name_el = pm.find(f"{KML_NS}name")
        desc = (desc_el.text or "") if desc_el is not None else ""
        raw_name = (name_el.text or "") if name_el is not None else ""

        cads = list(dict.fromkeys(CAD_RE.findall(desc) + CAD_RE.findall(raw_name)))
        primary_cad = cads[0] if cads else None
        secondary_cads = cads[1:]
        label = raw_name or description_label(desc) or (primary_cad or "Без названия")
        poly = parse_polygon(pm)
        pt = parse_point(pm)

        if dry_run:
            s.geo_created += 1
            if poly: s.contours += 1
            if pt: s.points += 1
            if primary_cad:
                s.primary_links += 1
                s.secondary_links += len(secondary_cads)
            else:
                s.unlinked += 1
            continue

        # Идемпотентность на уровне линка (geo_entity всё равно append).
        if primary_cad and _link_exists(conn, asset_type, primary_cad, "primary", valid_from):
            s.skipped_existing += 1
            continue

        uid = register_geo(conn, label, source="kmz")
        s.geo_created += 1
        if poly:
            add_contour(conn, uid, poly, valid_from, source="kmz")
            s.contours += 1
        if pt:
            add_point(conn, uid, pt[0], pt[1], valid_from, source="kmz")
            s.points += 1

        if primary_cad:
            link_asset(conn, asset_type, primary_cad, uid, valid_from,
                       role="primary", source="kmz")
            s.primary_links += 1
            for sc in secondary_cads:
                if not _link_exists(conn, asset_type, sc, "reference", valid_from):
                    link_asset(conn, asset_type, sc, uid, valid_from,
                               role="reference", source="kmz")
                    s.secondary_links += 1
        else:
            s.unlinked += 1

    return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.import_kml_geo_cli",
        description="Импорт KML/KMZ → §7 (geo entities).",
    )
    p.add_argument("--kml", required=True, type=Path)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--valid-from", default=None,
                   help="ISO YYYY-MM-DD; default — из имени файла (DD-MM-YYYY).")
    p.add_argument("--asset-type", default="object",
                   choices=["object", "lot", "oks", "room", "land", "bu", "equipment"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if not args.kml.is_file():
        print(f"ERR: KML not found: {args.kml}", file=sys.stderr)
        return 2
    if not args.db.is_file():
        print(f"ERR: DB not found: {args.db}; запустите init_db_cli", file=sys.stderr)
        return 2

    valid_from = args.valid_from or extract_valid_from_from_filename(args.kml)
    if valid_from is None:
        print(f"ERR: не удалось извлечь дату из имени {args.kml.name}; "
              "укажи --valid-from YYYY-MM-DD", file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        stats = import_kml(
            conn, read_kml_text(args.kml), valid_from,
            asset_type=args.asset_type, dry_run=args.dry_run,
        )
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    tag = "DRY-RUN" if args.dry_run else "OK"
    print(f"[{tag}] {args.kml.name} → {args.db.name}  valid_from={valid_from}")
    print(f"  placemark'ов:    {stats.total}")
    print(f"  geo_entity:      {stats.geo_created}")
    print(f"  контуров:        {stats.contours}")
    print(f"  точек:           {stats.points}")
    print(f"  primary линки:   {stats.primary_links}")
    print(f"  reference:       {stats.secondary_links}")
    print(f"  unlinked:        {stats.unlinked}")
    print(f"  skipped (re-run):{stats.skipped_existing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
