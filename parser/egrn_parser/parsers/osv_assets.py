"""
egrn_parser/parsers/osv_assets.py — парсер оборотно-сальдовой ведомости (ОСВ)
по основным средствам → реестр `fixed_asset`.

ОСВ (Excel 1С): колонка «Субконто» содержит либо КОД СЧЁТА (01.01, 01.08, …),
либо НАИМЕНОВАНИЕ основного средства (техника) под текущим счётом. Числовые
колонки — сальдо/обороты/количество.

Зачем (ADR-006 §G): техника из ОСВ используется в агро-событиях (обработки/сбор);
ОКС на счёте **01.08** — объекты, права на которые ещё не оформлены (НЕ на
кадастровом учёте) → `on_cadastre=0`. Мост к ADR-005 (постановка ОКС на учёт).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# Код счёта ОСВ: 01, 01.01, 01.08, 01.01.1 …
_ACCOUNT_RE = re.compile(r"^\d{2}(\.\d+)*$")
# Счета ОКС, права на которые не оформлены (не на кадастровом учёте).
_UNREGISTERED_ACCOUNTS = ("01.08",)

_ENSURE_DDL = """
CREATE TABLE IF NOT EXISTS fixed_asset (
    asset_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    account      TEXT,
    cost         REAL,
    qty          REAL,
    units        INTEGER,
    on_cadastre  INTEGER NOT NULL DEFAULT 1,
    cad_number   TEXT,
    osv_period   TEXT,
    source       TEXT NOT NULL DEFAULT 'osv',
    source_file  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, account, osv_period)
);
"""


def _is_account(v: Any) -> bool:
    return isinstance(v, str) and bool(_ACCOUNT_RE.match(v.strip()))


def _nums(row: tuple, start: int) -> list[float]:
    out = []
    for c in row[start:]:
        if isinstance(c, (int, float)):
            out.append(float(c))
        elif isinstance(c, str):
            t = c.replace(" ", "").replace(",", ".")
            try:
                out.append(float(t))
            except ValueError:
                pass
    return out


def _find_subkonto_col(rows: list[tuple]) -> int:
    """Колонка «Субконто» (по заголовку); fallback — первая непустая текстовая."""
    for r in rows[:15]:
        for j, c in enumerate(r):
            if isinstance(c, str) and c.strip() == "Субконто":
                return j
    # fallback: колонка, где впервые встречается код счёта
    for r in rows[:30]:
        for j, c in enumerate(r):
            if _is_account(c):
                return j
    return 0


def parse_osv(xlsx_path: Path | str, *, period: Optional[str] = None) -> list[dict[str, Any]]:
    """ОСВ.xlsx → список ОС: {name, account, cost, qty, on_cadastre}.

    Требует openpyxl. `period` (напр. '2025') — для идемпотентности записи.
    """
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    col = _find_subkonto_col(rows)

    # период из шапки «Период: 2025 г.» если не задан
    if period is None:
        for r in rows[:6]:
            for c in r:
                m = isinstance(c, str) and re.search(r"Период:\s*([0-9]{4})", c)
                if m:
                    period = m.group(1)
                    break

    # Агрегируем одинаковые ОС (3 насоса = 3 строки → 1 запись, units=3,
    # cost/qty суммируются) — реестр по (наименование, счёт).
    agg: dict[tuple[str, Optional[str]], dict[str, Any]] = {}
    account: Optional[str] = None
    for r in rows:
        if col >= len(r):
            continue
        cell = r[col]
        if cell is None or (isinstance(cell, str) and not cell.strip()):
            continue
        if _is_account(cell):
            account = cell.strip()
            continue
        if not isinstance(cell, str) or account is None:
            continue  # шапка до первого счёта / не-строка
        nums = _nums(r, col + 1)
        if not nums:
            continue
        key = (cell.strip(), account)
        a = agg.get(key)
        if a is None:
            a = {
                "name": cell.strip(), "account": account, "cost": 0.0, "qty": 0.0,
                "units": 0,
                "on_cadastre": 0 if account.startswith(_UNREGISTERED_ACCOUNTS) else 1,
                "osv_period": period,
            }
            agg[key] = a
        a["cost"] += nums[0]
        a["qty"] += nums[-1] if nums[-1] <= 100000 else 0
        a["units"] += 1
    return list(agg.values())


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_ENSURE_DDL)


def upsert_assets(conn: sqlite3.Connection, assets: list[dict[str, Any]], *,
                  source_file: Optional[str] = None) -> dict[str, int]:
    """Идемпотентно записать ОС в fixed_asset (по UNIQUE(name,account,period))."""
    ensure_table(conn)
    ins = upd = 0
    for a in assets:
        existed = conn.execute(
            "SELECT 1 FROM fixed_asset WHERE name=? AND IFNULL(account,'')=IFNULL(?,'') "
            "AND IFNULL(osv_period,'')=IFNULL(?,'')",
            (a["name"], a.get("account"), a.get("osv_period"))).fetchone() is not None
        conn.execute(
            """INSERT INTO fixed_asset (name, account, cost, qty, units, on_cadastre,
                                        osv_period, source, source_file)
               VALUES (:name, :account, :cost, :qty, :units, :on_cadastre,
                       :osv_period, 'osv', :sf)
               ON CONFLICT(name, account, osv_period) DO UPDATE SET
                   cost=excluded.cost, qty=excluded.qty, units=excluded.units,
                   on_cadastre=excluded.on_cadastre, source_file=excluded.source_file""",
            {**a, "sf": source_file})
        upd += existed
        ins += not existed
    conn.commit()
    return {"inserted": ins, "updated": upd, "total": len(assets)}
