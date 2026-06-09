"""
01c_contours_to_db.py — запись sidecar контуров в БД (ADR-005, шаг ingest→DB).

Читает `<project>/_data/contours.json` (вывод 01b_ingest_contours) и пишет
геометрию в `land_contours` через land_ingest/land_db: классификация ЗУ/МКУ по
числу полигонов, идемпотентно по (parent_cad, contour_no). Объекты без `geojson`
(screenshot_cv без georeference) пропускаются.

Usage:
  python 01c_contours_to_db.py --project /path/to/project --db /path/to/egrn.db
  python 01c_contours_to_db.py --project . --db egrn.db --dry-run
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from egrn_parser.parsers import land_ingest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="Корень проекта (с _data/contours.json)")
    ap.add_argument("--db", required=True, help="Путь к SQLite БД")
    ap.add_argument("--dry-run", action="store_true", help="Не коммитить, только лог")
    args = ap.parse_args()

    sidecar_path = Path(args.project).resolve() / "_data" / "contours.json"
    if not sidecar_path.exists():
        print(f"[!] нет {sidecar_path} — сначала запусти 01b_ingest_contours")
        return 1

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(args.db)
    try:
        res = land_ingest.ingest_sidecar_contours(conn, sidecar)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    t = res["totals"]
    print(f"[i] объектов в sidecar: {t['objects']}")
    print(f"    записано: {t['written']} (контуров: {t['contours']})")
    print(f"    пропущено без geojson: {t['skipped']}")
    for w in res["written"][:20]:
        print(f"      ✓ {w['cad']:<22} {w['layout']:<4} контуров={w['contours']}")
    if res["skipped_no_geom"]:
        print(f"    без геометрии: {', '.join(res['skipped_no_geom'][:10])}"
              + (" …" if len(res["skipped_no_geom"]) > 10 else ""))
    if args.dry_run:
        print("[dry-run] изменения откатаны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
