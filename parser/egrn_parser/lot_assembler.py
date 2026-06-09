"""
egrn_parser/lot_assembler.py — Lot-сборщик (C5, SPEC_parser §6).

Детерминированный отбор состава лота из `objects` по правилам include/exclude и
дате `as_of` → запись `lots`/`lot_items` + фрагмент `manifest.lot` по контракту
`contracts/bundle/bundle.schema.json` (`{lot_id, as_of_date, include, exclude,
members[]}`).

include/exclude — словарь правил отбора:
    {"cads": ["<кн>", …],      # явные КН
     "globs": ["61:44:*", …],  # маски КН (fnmatch)
     "types": ["land", …]}     # по objects.object_type
Кандидаты = объединение правил include минус объединение exclude. Порядок членов
детерминированный (сортировка по cad_number) — round-trip даёт тот же members[].
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import sqlite3
from typing import Any, Optional

# objects.object_type → lot_items.role (CHECK: building|land|room|equipment|structure).
_ROLE_BY_TYPE = {
    "land": "land",
    "building": "building",
    "construction": "structure",
    "structure": "structure",
    "flat": "room",
    "room": "room",
    "equipment": "equipment",
}


def _role_for(object_type: Optional[str]) -> str:
    return _ROLE_BY_TYPE.get((object_type or "").lower(), "building")


def _matches(cad: str, object_type: Optional[str], rules: Optional[dict]) -> bool:
    if not rules:
        return False
    if cad in (rules.get("cads") or []):
        return True
    if any(fnmatch.fnmatchcase(cad, g) for g in (rules.get("globs") or [])):
        return True
    if (object_type or "") in (rules.get("types") or []):
        return True
    return False


def select_members(conn: sqlite3.Connection, *, include: Optional[dict] = None,
                   exclude: Optional[dict] = None,
                   as_of: Optional[str] = None) -> list[dict[str, Any]]:
    """Отобрать объекты по include/exclude (+as_of) → [{cad_number, object_type, role}].

    `as_of` (YYYY-MM-DD) — снимок: берутся объекты, известные на дату
    (`objects.updated_at <= as_of` конец дня), если колонка есть. Детерминированный
    порядок по cad_number."""
    rows = conn.execute("SELECT cad_number, object_type, updated_at FROM objects").fetchall()
    cutoff = f"{as_of} 23:59:59" if as_of else None
    out = []
    for cad, otype, updated in rows:
        if cutoff and updated and str(updated) > cutoff:
            continue
        if _matches(cad, otype, include) and not _matches(cad, otype, exclude):
            out.append({"cad_number": cad, "object_type": otype, "role": _role_for(otype)})
    out.sort(key=lambda r: r["cad_number"])
    return out


def assemble_lot(conn: sqlite3.Connection, lot_id: str, name: str, *,
                 include: Optional[dict] = None, exclude: Optional[dict] = None,
                 as_of: Optional[str] = None, primary_cad: Optional[str] = None,
                 roles: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Собрать лот: отбор членов → запись `lots`+`lot_items` (идемпотентно,
    детерминированно) → фрагмент `manifest.lot`.

    `roles` — переопределение роли по КН (иначе по object_type). `primary_cad` —
    главный КН (по умолч. первый член)."""
    as_of = as_of or _dt.date.today().isoformat()
    members = select_members(conn, include=include, exclude=exclude, as_of=as_of)
    if roles:
        for m in members:
            m["role"] = roles.get(m["cad_number"], m["role"])
    primary = primary_cad or (members[0]["cad_number"] if members else None)

    conn.execute(
        "INSERT INTO lots(lot_id, name, primary_cad_number) VALUES(?,?,?) "
        "ON CONFLICT(lot_id) DO UPDATE SET name=excluded.name, "
        "primary_cad_number=excluded.primary_cad_number",
        (lot_id, name, primary))
    conn.execute("DELETE FROM lot_items WHERE lot_id=?", (lot_id,))   # чистая пересборка
    for ord_, m in enumerate(members, 1):
        conn.execute(
            "INSERT INTO lot_items(lot_id, cad_number, role, ord) VALUES(?,?,?,?)",
            (lot_id, m["cad_number"], m["role"], ord_))
    conn.commit()
    return lot_manifest(conn, lot_id, as_of=as_of, include=include, exclude=exclude)


def lot_manifest(conn: sqlite3.Connection, lot_id: str, *, as_of: Optional[str] = None,
                 include: Optional[dict] = None, exclude: Optional[dict] = None) -> dict[str, Any]:
    """Фрагмент `manifest.lot` из сохранённого состава (members по ord, cad)."""
    rows = conn.execute(
        "SELECT cad_number FROM lot_items WHERE lot_id=? ORDER BY ord, cad_number",
        (lot_id,)).fetchall()
    frag: dict[str, Any] = {
        "lot_id": lot_id,
        "as_of_date": as_of or _dt.date.today().isoformat(),
        "members": [r[0] for r in rows],
    }
    if include is not None:
        frag["include"] = include
    if exclude is not None:
        frag["exclude"] = exclude
    return frag
