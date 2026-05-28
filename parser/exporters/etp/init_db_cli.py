"""CLI: инициализация ekcelo.sqlite для разработки/смоук-теста.

Usage:
    # минимальная БД (только objects + миграция 0001)
    python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite

    # + загрузка baseline-шаблона для немедленного смоук-теста
    python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite --with-template

    # пересоздать существующую БД (предупреждение перед перезаписью)
    python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite --force

Что делает:
- Создаёт пустую SQLite БД.
- Применяет минимальную схему ЕГРН-слоя (objects + связанные) — достаточно
  для FK-инвариантов ЭТП-таблиц.
- Применяет миграцию 0001 (object_etp_profile / lots / lot_items).
- Если --with-template — загружает дефолтный osv_template.yaml: 3 baseline
  объекта в objects + профиль/лот из template.

Для production используйте полноценный egrn_parser с миграциями
(parser/egrn_parser/db/migrations.py). Этот CLI — для разработки.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_0001 = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
TEMPLATE_YAML = REPO_ROOT / "parser" / "exporters" / "etp" / "templates" / "osv_template.yaml"

# Минимальная схема ЕГРН-слоя — достаточно для FK из object_etp_profile/lots/lot_items.
_MIN_EGRN_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    cad_number    TEXT PRIMARY KEY,
    object_type   TEXT NOT NULL,
    address       TEXT,
    area          REAL,
    category      TEXT,
    permitted_use TEXT,
    purpose       TEXT,
    floors        INTEGER,
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS entity_registry (
    inn         TEXT PRIMARY KEY,
    name_full   TEXT NOT NULL,
    name_short  TEXT,
    ogrn        TEXT,
    entity_type TEXT
);
CREATE TABLE IF NOT EXISTS rights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number TEXT NOT NULL REFERENCES objects(cad_number),
    right_type TEXT NOT NULL,
    right_holder_inn TEXT REFERENCES entity_registry(inn),
    share_numerator INTEGER, share_denominator INTEGER,
    registration_number TEXT, registration_date TEXT, source_extract_id INTEGER
);
CREATE TABLE IF NOT EXISTS object_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number TEXT NOT NULL REFERENCES objects(cad_number),
    restrict_type TEXT, description TEXT, registry_number TEXT,
    valid_from TEXT, valid_to TEXT, basis_doc TEXT
);
"""

# Дефолтные объекты для baseline (соответствуют osv_template.yaml + фикстуре).
_BASELINE_OBJECTS = [
    ("61:44:0050706:31", "room", "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII", 125.4, "офис", 3),
    ("61:44:0050706:42", "room", "г. Ростов-на-Дону, ул. Промышленная, 5", 380.0, "склад", 1),
    ("61:44:0050706:7",  "land", "Ростовская обл., с. Иваново, уч. 7", 5000.0, None, None),
]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db)

    if db_path.exists():
        if not args.force:
            print(f"error: db already exists: {db_path}\n"
                  f"use --force to overwrite.", file=sys.stderr)
            return 1
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_MIN_EGRN_SCHEMA)
    conn.executescript(MIGRATION_0001.read_text(encoding="utf-8"))

    for cad, ot, addr, area, purpose, floors in _BASELINE_OBJECTS:
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area, purpose, floors) "
            "VALUES (?,?,?,?,?,?)",
            (cad, ot, addr, area, purpose, floors),
        )
    conn.commit()

    if args.with_template:
        # Lazy import чтобы init_db работал без pyyaml.
        from parser.exporters.etp.etl_osv import apply_osv, load_osv
        report = apply_osv(conn, load_osv(TEMPLATE_YAML))
        print(f"[template] profiles: +{report.profiles_inserted}  "
              f"lots: +{report.lots_inserted}  "
              f"lot_items: +{report.lot_items_inserted}")

    conn.close()
    print(f"[init-db] ok: {db_path} ({len(_BASELINE_OBJECTS)} objects)")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.init_db_cli",
        description="Инициализация dev-SQLite для ЭТП-экспортёра.",
    )
    p.add_argument("--db", required=True,
                   help="Путь к новой SQLite БД (расширение .sqlite или .db).")
    p.add_argument("--force", action="store_true",
                   help="Перезаписать существующую БД.")
    p.add_argument("--with-template", action="store_true",
                   help="После init дополнительно применить osv_template.yaml "
                        "(baseline для смоук-теста).")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
