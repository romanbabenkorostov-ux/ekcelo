"""CLI: экспорт ЭТП-профиля из БД в JSON для viewer.

Usage:
    # Глобальный экспорт (всё из БД) → parser/exports/etp/object_etp_profile.json
    python -m parser.exporters.etp.export_json_cli --db path/to/ekcelo.sqlite

    # Проект-специфичный → parser/exports/etp/pirushin/object_etp_profile.json
    python -m parser.exporters.etp.export_json_cli --db ... --project pirushin

    # Кастомный путь
    python -m parser.exporters.etp.export_json_cli --db ... --out viewer-data/etp/
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from parser.exporters.etp.export_json import DEFAULT_OUT_DIR, write_export


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    out_path = write_export(conn, args.out, project_slug=args.project)
    print(out_path)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.export_json_cli",
        description="Экспорт object_etp_profile / lots / lot_items в JSON для viewer.",
    )
    p.add_argument("--db", required=True, help="Путь к SQLite БД с миграцией 0001.")
    p.add_argument("--out", default=str(DEFAULT_OUT_DIR),
                   help=f"Корневая директория экспорта (по умолчанию: {DEFAULT_OUT_DIR}).")
    p.add_argument("--project", default=None,
                   help="Project slug для фильтрации лотов lot:<slug>:* (по умолчанию: всё).")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
