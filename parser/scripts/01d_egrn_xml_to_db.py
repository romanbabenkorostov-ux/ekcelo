"""
01d_egrn_xml_to_db.py — контуры из XML-выписок ЕГРН в БД (ADR-007, шаг ingest→DB).

Соседний `01c_contours_to_db.py` делает то же самое для контуров из НСПД/ПКК
(через sidecar `_data/contours.json`). Отличие принципиальное и стоит того,
чтобы держать два входа рядом: НСПД — чужая выгрузка, доступная только через
браузер и живую сессию пользователя, а XML-выписка — подписанный ЭП документ,
который лежит на диске и читается офлайн. Там, где есть выписка, она точнее.

Скрипт намеренно НЕ трогает ничего, кроме геометрии: карточку объекта, права и
ограничения из той же выписки разбирает `egrn_parser.parsers.xml_parser`, и
дублировать его работу здесь незачем.

По умолчанию действует гейт по площади (ADR-007 §3): выписка, у которой площадь
по контуру не сходится с заявленной, НЕ пишется, а попадает в отчёт с причиной.
`--force` снимает гейт — это решение человека, посмотревшего на расхождение.

Usage:
  python 01d_egrn_xml_to_db.py --xml <файл|папка> --db <path>
  python 01d_egrn_xml_to_db.py --xml inbox/ --db egrn.db --dry-run
  python 01d_egrn_xml_to_db.py --xml inbox/ --db egrn.db --force
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egrn_parser.parsers import xml_geometry_db as _writer   # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry  # noqa: E402


def _xml_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.xml") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", required=True, help="XML-выписка или папка с ними")
    ap.add_argument("--db", required=True, help="Путь к SQLite БД")
    ap.add_argument("--dry-run", action="store_true",
                    help="Разобрать и показать отчёт, ничего не писать")
    ap.add_argument("--force", action="store_true",
                    help="Писать даже при несошедшейся площади (ADR-007 §3)")
    args = ap.parse_args()

    target = Path(args.xml).resolve()
    if not target.exists():
        print(f"[!] не найдено: {target}")
        return 1

    files = _xml_files(target)
    if not files:
        print(f"[!] в {target} нет .xml")
        return 1

    conn = sqlite3.connect(args.db)
    totals = {"файлов": len(files), "записано": 0, "контуров": 0,
              "чзу": 0, "пропущено": 0}
    try:
        for path in files:
            try:
                geometry = extract_geometry(path)
            except Exception as exc:                       # noqa: BLE001
                print(f"  ✗ {path.name}: не разобрался — {exc}")
                totals["пропущено"] += 1
                continue

            if args.dry_run:
                check = geometry.area_check()
                status = ("нет геометрии" if not geometry.has_geometry
                          else geometry.zone_error or check.describe())
                print(f"  · {geometry.cad_number or path.name}: {status}")
                continue

            report = _writer.write_geometry(conn, geometry, strict=not args.force)
            if report["written"]:
                totals["записано"] += 1
                totals["контуров"] += report["contours"]
                totals["чзу"] += report["parts"]
                mirrors = ", ".join(report["mirrored"]) or "—"
                print(f"  ✓ {report['cad_number']}: контуров {report['contours']}, "
                      f"ЧЗУ {report['parts']}; {report['area_check']}; "
                      f"витрины: {mirrors}")
            else:
                totals["пропущено"] += 1
                print(f"  ✗ {report['cad_number'] or path.name}: {report['skipped']}")
    finally:
        conn.close()

    print("\n" + "; ".join(f"{k}: {v}" for k, v in totals.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
