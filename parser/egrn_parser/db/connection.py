"""
egrn_parser/db/connection.py — фабрика SQLite-подключений.

Два режима:
  - writer (чтение + запись): WAL + foreign_keys ON
  - reader (только чтение):   mode=ro URI

Использование:
    with get_connection(db_path) as conn:
        conn.execute("SELECT ...")
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def get_connection(db_path: Path | str, readonly: bool = False):
    """
    Контекстный менеджер для подключения к SQLite.
    Автоматически коммитит или откатывает транзакцию.
    """
    db_path = Path(db_path)

    if readonly:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -32000")   # ~32 МБ кэша

    conn.row_factory = sqlite3.Row  # доступ по имени колонки

    try:
        yield conn
    except Exception:
        if not readonly:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str, schema_sql_path: Path | str | None = None) -> None:
    """
    Создать/инициализировать БД по schema.sql.
    Если schema_sql_path не задан — берёт db/schema.sql рядом с этим модулем.
    """
    from pathlib import Path as _Path
    db_path = _Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if schema_sql_path is None:
        schema_sql_path = _Path(__file__).parent / "schema.sql"

    schema_sql_path = _Path(schema_sql_path)
    if not schema_sql_path.exists():
        raise FileNotFoundError(f"Файл схемы не найден: {schema_sql_path}")

    sql = schema_sql_path.read_text(encoding="utf-8")

    with get_connection(db_path) as conn:
        # Выполняем блоки, разделяя по «;» но внимательно — схема содержит INSERT
        conn.executescript(sql)

    return db_path


def check_db(db_path: Path | str) -> bool:
    """Проверить, что БД существует и содержит таблицу system_meta с версией."""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    try:
        with get_connection(db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key='egrn_parser_version'"
            ).fetchone()
            return row is not None
    except Exception:
        return False


def get_schema_version(db_path: Path | str) -> str | None:
    """Вернуть версию схемы из system_meta или None."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        with get_connection(db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key='schema_version'"
            ).fetchone()
            return row["value"] if row else None
    except Exception:
        return None
