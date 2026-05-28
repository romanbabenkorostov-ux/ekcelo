"""CLI: импорт ОСВ survey-листа в БД.

Usage:
    python -m parser.exporters.etp.etl_osv_cli \\
        --yaml path/to/survey.yaml \\
        --db path/to/ekcelo.sqlite \\
        [--dry-run] [--export]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from parser.exporters.etp.auto_export import add_export_args, run_export_if_requested
from parser.exporters.etp.etl_osv import apply_osv, load_osv


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"error: yaml not found: {yaml_path}", file=sys.stderr)
        return 2
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2

    try:
        doc = load_osv(yaml_path)
    except (ValueError, Exception) as e:
        print(f"error: invalid yaml: {e}", file=sys.stderr)
        return 3

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    report = apply_osv(conn, doc, dry_run=args.dry_run)

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[{mode}] profiles: +{report.profiles_inserted}/~{report.profiles_updated}  "
        f"lots: +{report.lots_inserted}/~{report.lots_updated}  "
        f"lot_items: +{report.lot_items_inserted}/-{report.lot_items_deleted}"
    )

    run_export_if_requested(conn, args, dry_run=args.dry_run, source_label="osv")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.etl_osv_cli",
        description="Импорт ОСВ survey-листа (YAML) в object_etp_profile / lots / lot_items.",
    )
    p.add_argument("--yaml", required=True, help="Путь к YAML survey-листу.")
    p.add_argument("--db", required=True, help="Путь к SQLite БД с миграцией 0001.")
    p.add_argument("--dry-run", action="store_true",
                   help="Только валидация + reporting; БД не меняется.")
    add_export_args(p)
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
