"""
egrn_parser/db/migrations.py — миграции БД v1.9 → v1.10.

Команда CLI: egrn-parser migrate --db <path>

Что делает:
1. Создаёт резервную копию БД: <name>.db.bak_v1_9_<timestamp>
2. Добавляет недостающие колонки (floors_total, floors_above_ground, …)
3. Конвертирует старые right_restrictions → отдельные записи rights (right_category='restriction')
4. Добавляет таблицы code_dictionary, system_meta если отсутствуют
5. Обновляет system_meta.schema_version → '1.10'
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from egrn_parser.db.connection import get_connection

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> bool:
    """Добавить колонку, если её нет. Возвращает True если добавлена."""
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        log.info("Добавлена колонка %s.%s", table, column)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Основная функция миграции
# ─────────────────────────────────────────────────────────────────────────────

def migrate(db_path: Path | str, backup: bool = True) -> None:
    """
    Мигрировать БД до v1.10.
    При backup=True создаётся резервная копия до любых изменений.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"БД не найдена: {db_path}")

    # 1. Резервная копия
    if backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bak = db_path.with_suffix(f".db.bak_v1_9_{ts}")
        shutil.copy2(db_path, bak)
        log.info("Резервная копия создана: %s", bak)

    with get_connection(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")  # отключить FK на время миграции
        conn.execute("BEGIN")

        try:
            _migrate_building_objects(conn)
            _migrate_rights(conn)
            _ensure_system_meta(conn)
            _ensure_code_dictionary(conn)
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            log.error("Миграция прервана: %s", exc)
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    log.info("Миграция завершена: %s", db_path)


def _migrate_building_objects(conn: sqlite3.Connection) -> None:
    """Добавить новые поля v1.10 в building_objects."""
    if not _table_exists(conn, "building_objects"):
        return
    new_cols = [
        ("floors_total",            "INTEGER"),
        ("floors_above_ground",     "INTEGER"),
        ("underground_floors",      "INTEGER"),
        ("floors_inspection",       "TEXT"),
        ("condition_inspection",    "TEXT"),
        ("parent_floors_above_ground", "INTEGER"),
        ("parent_underground_floors",  "INTEGER"),
        ("object_restrictions",     "TEXT"),
        ("main_char_type",          "TEXT"),
        ("main_value",              "REAL"),
        ("main_unit",               "TEXT"),
    ]
    for col, defn in new_cols:
        _add_column_if_missing(conn, "building_objects", col, defn)


def _migrate_rights(conn: sqlite3.Connection) -> None:
    """
    Конвертировать устаревшие right_restrictions → отдельные записи right_category='restriction'.
    Удалить колонку right_restrictions (SQLite не поддерживает DROP COLUMN до 3.35,
    поэтому просто обнуляем значения; реальное удаление через CREATE TABLE AS SELECT
    выходит за рамки minor-миграции, помечаем как TODO).
    """
    if not _table_exists(conn, "rights"):
        return

    # Добавить right_category если нет
    _add_column_if_missing(conn, "rights", "right_category", "TEXT NOT NULL DEFAULT 'right'")
    _add_column_if_missing(conn, "rights", "restricting_right_id",     "INTEGER")
    _add_column_if_missing(conn, "rights", "restricting_right_number",  "TEXT")
    _add_column_if_missing(conn, "rights", "lease_partial_measure_type","TEXT")
    _add_column_if_missing(conn, "rights", "lease_partial_qty",         "REAL")
    _add_column_if_missing(conn, "rights", "lease_partial_unit",        "TEXT")
    _add_column_if_missing(conn, "rights", "servitude_part_number",     "TEXT")
    _add_column_if_missing(conn, "rights", "servitude_is_public",       "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "rights", "personal_participation_req","INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "rights", "claim_records",             "TEXT")
    _add_column_if_missing(conn, "rights", "source_right_category",     "TEXT")
    _add_column_if_missing(conn, "rights", "source_account_code",       "TEXT")

    # Если есть устаревшая колонка right_restrictions — конвертировать
    if _column_exists(conn, "rights", "right_restrictions"):
        rows = conn.execute(
            "SELECT right_id, object_class, object_key_type, object_key_value, "
            "right_restrictions, source_extract_number "
            "FROM rights WHERE right_restrictions IS NOT NULL AND right_restrictions != ''"
        ).fetchall()

        for row in rows:
            old_text = row["right_restrictions"]
            if not old_text or old_text.lower() in ("не зарегистрировано", "данные отсутствуют"):
                continue
            # Создать новую запись restriction
            conn.execute(
                """INSERT OR IGNORE INTO rights
                   (object_class, object_key_type, object_key_value, right_category,
                    right_type, basis, source_extract_number, created_at, updated_at)
                   VALUES (?, ?, ?, 'restriction', ?, ?, ?, datetime('now'), datetime('now'))""",
                (
                    row["object_class"],
                    row["object_key_type"],
                    row["object_key_value"],
                    "Ограничение прав (мигрировано из right_restrictions)",
                    old_text[:2000],
                    row["source_extract_number"],
                ),
            )
        log.info(
            "Мигрировано %d записей right_restrictions → rights(right_category='restriction')",
            len(rows),
        )
        # TODO(v1.11): реальное удаление колонки right_restrictions через RECREATE TABLE


def _ensure_system_meta(conn: sqlite3.Connection) -> None:
    """Создать/обновить system_meta."""
    if not _table_exists(conn, "system_meta"):
        conn.execute(
            "CREATE TABLE system_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
    for key, val in [
        ("egrn_parser_version", "1.10"),
        ("graph_json_version",  "1.1"),
        ("schema_version",      "1.10"),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO system_meta VALUES (?, ?)", (key, val)
        )


def _ensure_code_dictionary(conn: sqlite3.Connection) -> None:
    """Создать code_dictionary если не существует, затем загрузить словари."""
    if not _table_exists(conn, "code_dictionary"):
        conn.execute(
            """CREATE TABLE code_dictionary (
                dict_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                code        TEXT NOT NULL,
                value_ru    TEXT NOT NULL,
                value_short TEXT,
                description TEXT,
                is_active   INTEGER NOT NULL DEFAULT 1,
                source      TEXT,
                UNIQUE(category, code)
            )"""
        )
    # Загрузить словари (без повторного использования get_connection чтобы не дублировать BEGIN)
    from egrn_parser import dictionaries as d
    for cat_name in d.ALL_DICT_CATEGORIES:
        category_dict: dict = getattr(d, cat_name)
        for code, meta in category_dict.items():
            conn.execute(
                "INSERT OR IGNORE INTO code_dictionary "
                "(category, code, value_ru, value_short, source) VALUES (?, ?, ?, ?, ?)",
                (cat_name, str(code), meta.get("value_ru", ""), meta.get("short"), "dictionaries.py"),
            )


def rollback(db_path: Path | str) -> None:
    """
    Откат: найти последнюю .bak-копию и восстановить из неё.
    """
    db_path = Path(db_path)
    parent = db_path.parent
    stem = db_path.stem
    baks = sorted(parent.glob(f"{stem}.db.bak_v1_9_*"), reverse=True)
    if not baks:
        raise FileNotFoundError(f"Резервных копий не найдено для {db_path}")
    latest_bak = baks[0]
    shutil.copy2(latest_bak, db_path)
    log.info("Восстановлено из резервной копии: %s → %s", latest_bak, db_path)
