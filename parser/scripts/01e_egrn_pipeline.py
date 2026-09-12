"""
01e_egrn_pipeline.py — весь проход одной командой: выписки → SQLite → KML + эссе.

Продолжение линейки 01b (контуры НСПД в sidecar) / 01c (sidecar в БД) /
01d (геометрия выписки в БД). Отличие от 01d: тот пишет только контуры, а этот
делает полный проход — карточка объекта, права, ограничения, геометрия, затем
выгрузки. Именно его вызывает графическая оболочка (`parser/gui/`).

Usage:
  python 01e_egrn_pipeline.py --xml <файл|папка> --db egrn.db
  python 01e_egrn_pipeline.py --xml inbox/ --db egrn.db --out выгрузка/
  python 01e_egrn_pipeline.py --xml inbox/ --db egrn.db --no-parts --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egrn_parser.geo_pipeline import run_pipeline   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", required=True, help="XML-выписка или папка с ними")
    ap.add_argument("--db", required=True, help="Путь к SQLite БД")
    ap.add_argument("--out", help="Куда складывать выгрузки (по умолчанию рядом с БД)")
    ap.add_argument("--no-kml", action="store_true", help="Не создавать KML")
    ap.add_argument("--no-essays", action="store_true", help="Не создавать эссе")
    ap.add_argument("--no-schema-doc", action="store_true",
                    help="Не обновлять описание схемы БД")
    ap.add_argument("--no-html", action="store_true",
                    help="Не собирать HTML-отчёт (граф, хронология, эссе)")
    ap.add_argument("--no-parts", action="store_true",
                    help="Не выводить в KML части участка (ЧЗУ)")
    ap.add_argument("--skip-card", action="store_true",
                    help="Только геометрия, без карточки и прав")
    ap.add_argument("--force", action="store_true",
                    help="Писать контур даже при несошедшейся площади (ADR-007 §3)")
    ap.add_argument("--date", help="Зафиксировать дату в выгрузках (YYYY-MM-DD)")
    args = ap.parse_args()

    source = Path(args.xml)
    if not source.exists():
        print(f"[!] не найдено: {source}")
        return 1

    result = run_pipeline(
        source, args.db,
        out_dir=args.out,
        make_kml=not args.no_kml,
        make_essays=not args.no_essays,
        make_schema_doc=not args.no_schema_doc,
        make_html=not args.no_html,
        with_parts=not args.no_parts,
        force=args.force,
        skip_card=args.skip_card,
        generated_on=args.date,
        on_step=print,
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
