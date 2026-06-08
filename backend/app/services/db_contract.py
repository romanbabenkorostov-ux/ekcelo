"""DB-контракт C2 — загрузка `contracts/db/schema.json` + валидация sqlite.

Реализует `SPEC_backend.md §P0.1` (sub-stage P0.1.1): машиночитаемый
DB-контракт interchange-схемы Bundle. Источник правды DDL —
`schema/egrn_current_schema.sql`; контракт — его JSON-зеркало
(`contracts/db/schema.json`).

Зачем (ADR-001 + CLAUDE.md §3):
- Bundle's `db.sqlite` использует упрощённую §1..§6 модель backend'а (не
  богатую parser-схему). Этот контракт фиксирует, ЧТО ровно должно быть в
  interchange-БД, машиночитаемо — чтобы:
  1. parser знал какие колонки эмитить при down-проекции своей модели;
  2. backend мог провалидировать входящий Bundle до импорта;
  3. CI ловил дрейф между `schema/*.sql` и контрактом.

Функции:
- `load_contract()` → dict (parsed schema.json).
- `validate_db(db_path)` → list[str] нарушений (пусто = ок). Проверяет, что
  все таблицы контракта существуют и содержат required-колонки нужных типов.
- `check_contract_matches_ddl(ddl_text)` → list[str] расхождений контракт↔DDL.
  Используется sync-guard'ом (тест), чтобы контракт не отставал от schema.sql.

См. также: `backend/app/services/bundle.py` (импортёр, который читает эти
таблицы), `contracts/db/DB_SPEC.md` (человекочитаемый контракт).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = _REPO_ROOT / "contracts" / "db" / "schema.json"
_DDL_PATH = _REPO_ROOT / "schema" / "egrn_current_schema.sql"


# ─────────────────────────────────────────────────────────────────────────────
#  Загрузка контракта
# ─────────────────────────────────────────────────────────────────────────────

def load_contract(path: Path | None = None) -> dict[str, Any]:
    """Читает и парсит `contracts/db/schema.json`."""
    p = path or _CONTRACT_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def contract_tables(contract: dict[str, Any] | None = None) -> dict[str, Any]:
    return (contract or load_contract())["tables"]


# ─────────────────────────────────────────────────────────────────────────────
#  Валидация БД против контракта
# ─────────────────────────────────────────────────────────────────────────────

def validate_db(
    db_path: Path,
    *,
    contract: dict[str, Any] | None = None,
    require_section6: bool = False,
) -> list[str]:
    """Проверяет, что sqlite-БД соответствует C2-контракту.

    Возвращает список нарушений (пустой = соответствует).

    - Все таблицы §1..§5 контракта обязаны существовать с required-колонками.
    - Таблицы §6 (restorable=false) проверяются только если `require_section6`
      ИЛИ если они физически присутствуют в БД (тогда — на корректность колонок).
      Это отражает ADR-001: §6 может отсутствовать в чистом ЕГРН-слепке.
    - Тип колонки сверяется по SQLite affinity (TEXT/INTEGER/REAL).
    - Лишние колонки в БД НЕ являются нарушением (схема расширяема вперёд).
    """
    contract = contract or load_contract()
    tables = contract["tables"]
    violations: list[str] = []

    conn = sqlite3.connect(db_path)
    try:
        for tname, tdef in tables.items():
            is_s6 = str(tdef.get("section")) == "6"
            present = _table_exists(conn, tname)
            if not present:
                if is_s6 and not require_section6:
                    continue  # §6 опционален в ЕГРН-слепке
                violations.append(f"отсутствует таблица: {tname}")
                continue
            violations.extend(_validate_columns(conn, tname, tdef))
    finally:
        conn.close()
    return violations


def _validate_columns(conn: sqlite3.Connection, tname: str,
                      tdef: dict[str, Any]) -> list[str]:
    out: list[str] = []
    actual = {row[1]: row for row in conn.execute(f"PRAGMA table_info({tname})")}
    # row = (cid, name, type, notnull, dflt_value, pk)
    for col, cdef in tdef["columns"].items():
        if col not in actual:
            out.append(f"{tname}: отсутствует колонка {col}")
            continue
        want = str(cdef["type"]).upper()
        got = str(actual[col][2]).upper()
        if not _affinity_compatible(want, got):
            out.append(
                f"{tname}.{col}: тип {got or '∅'} не совместим с контрактом {want}"
            )
    return out


def _affinity_compatible(want: str, got: str) -> bool:
    """SQLite affinity терпимее строгих типов; пустой got (нет типа) — ок для TEXT."""
    if got == "" or got == want:
        return True
    # Числовые семейства
    numeric = {"INTEGER", "REAL", "NUMERIC"}
    if want in numeric and got in numeric:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Sync-guard: контракт ↔ DDL
# ─────────────────────────────────────────────────────────────────────────────

def check_contract_matches_ddl(
    *,
    contract: dict[str, Any] | None = None,
    ddl_text: str | None = None,
) -> list[str]:
    """Сверяет таблицы/колонки контракта с `schema/egrn_current_schema.sql`.

    Возвращает список расхождений (пусто = в синхроне). Ловит:
    - таблицу в контракте, которой нет в DDL (и наоборот);
    - колонку в контракте, которой нет в DDL (и наоборот).

    Это lightweight-парсер DDL (regex по `CREATE TABLE ... ( ... )`), не полный
    SQL-движок: достаточно для guard'а «контракт не отстал от schema.sql».
    """
    contract = contract or load_contract()
    ddl = ddl_text if ddl_text is not None else _DDL_PATH.read_text(encoding="utf-8")
    ddl_tables = _parse_ddl_tables(ddl)
    contract_tables_ = contract["tables"]

    issues: list[str] = []

    c_names = set(contract_tables_)
    d_names = set(ddl_tables)
    for missing in sorted(c_names - d_names):
        issues.append(f"таблица {missing} есть в контракте, но НЕ в DDL")
    for extra in sorted(d_names - c_names):
        issues.append(f"таблица {extra} есть в DDL, но НЕ в контракте")

    for tname in sorted(c_names & d_names):
        c_cols = set(contract_tables_[tname]["columns"])
        d_cols = set(ddl_tables[tname])
        for missing in sorted(c_cols - d_cols):
            issues.append(f"{tname}.{missing}: в контракте, но НЕ в DDL")
        for extra in sorted(d_cols - c_cols):
            issues.append(f"{tname}.{extra}: в DDL, но НЕ в контракте")
    return issues


_CREATE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)

_COMMENT_RE = re.compile(r"--[^\n]*")


def _parse_ddl_tables(ddl: str) -> dict[str, list[str]]:
    """Грубый парсер: {table: [column, ...]}. Игнорирует table-level constraints
    и `-- ...` комментарии в SQL."""
    out: dict[str, list[str]] = {}
    ddl_clean = _COMMENT_RE.sub("", ddl)
    for m in _CREATE_RE.finditer(ddl_clean):
        tname = m.group(1)
        body = m.group(2)
        cols: list[str] = []
        for raw in _split_top_level(body):
            line = raw.strip()
            if not line:
                continue
            first = line.split(None, 1)[0].upper()
            # пропустить table-level constraints
            if first in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
                continue
            col = line.split(None, 1)[0].strip('"`')
            cols.append(col)
        out[tname] = cols
    return out


def _split_top_level(body: str) -> list[str]:
    """Разбивает тело CREATE TABLE по запятым ВЕРХНЕГО уровня (вне скобок)."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


# ─────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None
