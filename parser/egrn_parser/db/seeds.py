"""
egrn_parser/db/seeds.py — загрузка словарей в code_dictionary.

Команда CLI: egrn-parser dict-load
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from egrn_parser import dictionaries as d
from egrn_parser.db.connection import get_connection


def load_dictionaries(db_path: Path | str) -> int:
    """
    Заполнить code_dictionary из dictionaries.py.
    Возвращает количество добавленных записей.
    Стратегия: INSERT OR IGNORE (идемпотентно).
    """
    db_path = Path(db_path)
    inserted = 0

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")

        # ── Категории со строковыми ключами ──────────────────────────────────
        for cat_name in d.ALL_DICT_CATEGORIES:
            category_dict: dict = getattr(d, cat_name)
            for code, meta in category_dict.items():
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO code_dictionary "
                        "(category, code, value_ru, value_short, source) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            cat_name,
                            str(code),
                            meta.get("value_ru", ""),
                            meta.get("short"),
                            "dictionaries.py",
                        ),
                    )
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1
                except sqlite3.IntegrityError:
                    pass  # already exists

        # ── HIERARCHY_LEVELS (числовые ключи) ────────────────────────────────
        for code, meta in d.HIERARCHY_LEVELS.items():
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO code_dictionary "
                    "(category, code, value_ru, source) VALUES (?, ?, ?, ?)",
                    ("HIERARCHY_LEVELS", str(code), meta["value_ru"], "dictionaries.py"),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass

        conn.execute("COMMIT")

    return inserted
