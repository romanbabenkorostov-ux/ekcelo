"""export_json: экспорт object_etp_profile / lots / lot_items в JSON для viewer.

Stage 4b. Закрывает trigger viewer-team (см. obsidian/Changelog/2026-05-28-etp-viewer-roadmap.md):
viewer admin/etp-profile/<cad_number> переключит fetch с фикстуры на этот JSON.

Контракт: **байт-в-байт совпадает с фикстурой**
`parser/tests/fixtures/etp/object_etp_profile_sample.json` —
ключи `object_etp_profile[]`, `lots[]`, `lot_items[]` с теми же полями.

Путь по умолчанию: `parser/exports/etp/<project_slug>/object_etp_profile.json`.
- `project_slug=None` (default) → `parser/exports/etp/object_etp_profile.json`
  (один глобальный экспорт без проектной группировки).
- `project_slug="pirushin"` → фильтрует лоты по префиксу `lot:pirushin:*` и
  все КН, упомянутые в этих лотах + их профили.

Файл коммитится в репо — viewer на GitHub Pages читает его через fetch.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("parser/exports/etp")
DEFAULT_FILENAME = "object_etp_profile.json"


# ─────────────────────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────────────────────

def build_export_payload(
    conn: sqlite3.Connection,
    *,
    project_slug: str | None = None,
) -> dict[str, Any]:
    """Собрать payload в формате фикстуры.

    Args:
        conn: соединение с БД (миграция 0001 применена).
        project_slug: префикс лотов (по шаблону lot:<slug>:NNN). None → все.

    Returns:
        dict с ключами object_etp_profile[], lots[], lot_items[] + метаданными.
    """
    conn.row_factory = sqlite3.Row
    lots = _fetch_lots(conn, project_slug)
    lot_ids = [l["lot_id"] for l in lots]
    lot_items = _fetch_lot_items(conn, lot_ids) if project_slug else _fetch_all_lot_items(conn)
    cad_numbers = _collect_cads(lots, lot_items)
    profiles = _fetch_profiles(conn, cad_numbers if project_slug else None)

    return {
        "$schema_version": "1.0",
        "$source": "parser/exporters/etp/export_json.py",
        "$project_slug": project_slug,
        "object_etp_profile": profiles,
        "lots": lots,
        "lot_items": lot_items,
    }


def write_export(
    conn: sqlite3.Connection,
    out_root: str | Path = DEFAULT_OUT_DIR,
    *,
    project_slug: str | None = None,
) -> Path:
    """Сохранить экспорт в файл. Возвращает путь."""
    payload = build_export_payload(conn, project_slug=project_slug)
    out_dir = Path(out_root) / project_slug if project_slug else Path(out_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / DEFAULT_FILENAME
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
#  Загрузчики
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_profiles(
    conn: sqlite3.Connection,
    cads: set[str] | None,
) -> list[dict[str, Any]]:
    if cads is None:
        rows = conn.execute(
            "SELECT * FROM object_etp_profile ORDER BY cad_number"
        ).fetchall()
    elif not cads:
        return []
    else:
        placeholders = ",".join("?" * len(cads))
        rows = conn.execute(
            f"SELECT * FROM object_etp_profile WHERE cad_number IN ({placeholders}) "
            f"ORDER BY cad_number",
            tuple(cads),
        ).fetchall()
    return [_profile_row_to_dict(r) for r in rows]


def _fetch_lots(
    conn: sqlite3.Connection,
    project_slug: str | None,
) -> list[dict[str, Any]]:
    if project_slug is None:
        rows = conn.execute("SELECT * FROM lots ORDER BY lot_id").fetchall()
    else:
        # Лот относится к проекту, если совпадает префикс lot:<slug>: или lot_<slug>_
        rows = conn.execute(
            "SELECT * FROM lots WHERE lot_id LIKE ? OR lot_id LIKE ? ORDER BY lot_id",
            (f"lot:{project_slug}:%", f"lot_{project_slug}_%"),
        ).fetchall()
    return [_lot_row_to_dict(r) for r in rows]


def _fetch_lot_items(
    conn: sqlite3.Connection,
    lot_ids: list[str],
) -> list[dict[str, Any]]:
    if not lot_ids:
        return []
    placeholders = ",".join("?" * len(lot_ids))
    rows = conn.execute(
        f"SELECT lot_id, cad_number, role, ord FROM lot_items "
        f"WHERE lot_id IN ({placeholders}) ORDER BY lot_id, ord, cad_number",
        tuple(lot_ids),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_all_lot_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT lot_id, cad_number, role, ord FROM lot_items "
        "ORDER BY lot_id, ord, cad_number"
    ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
#  Сериализация
# ─────────────────────────────────────────────────────────────────────────────

def _profile_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "cad_number": row["cad_number"],
        "location_extra": _parse_json(row["location_extra"]),
        "building_extra": _parse_json(row["building_extra"]),
        "layout": _parse_json(row["layout"]),
        "legal_extra": _parse_json(row["legal_extra"]),
        "risks": _parse_json(row["risks"]),
        "extras": _parse_json(row["extras"]),
        "source": row["source"],
        "confidence": row["confidence"],
        "updated_at": row["updated_at"],
    }


def _lot_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "lot_id": row["lot_id"],
        "name": row["name"],
        "platform_targets": _parse_json(row["platform_targets"]),
        "procedure_type": row["procedure_type"],
        "deal_type": row["deal_type"],
        "primary_cad_number": row["primary_cad_number"],
        "notes_md": row["notes_md"],
        "created_at": row["created_at"],
    }


def _parse_json(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _collect_cads(lots: list[dict], items: list[dict]) -> set[str]:
    cads: set[str] = set()
    for lot in lots:
        if lot.get("primary_cad_number"):
            cads.add(lot["primary_cad_number"])
    for it in items:
        cads.add(it["cad_number"])
    return cads
