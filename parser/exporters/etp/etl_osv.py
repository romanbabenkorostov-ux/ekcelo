"""etl_osv: импорт survey-листа экономиста (YAML) в БД.

Закрывает SPEC §7: «Источник правды для гэп-полей — survey-лист
экономиста + EXIF UserComment». Этот модуль реализует первый источник;
EXIF — отдельным модулем `etl_exif.py` (план).

Формат YAML — см. `parser/exporters/etp/templates/osv_template.yaml`.
Контракт write-API зафиксирован в `obsidian/Architecture/etl-osv.md`.

Поведение:
- `profiles[]` → UPSERT в `object_etp_profile` по `cad_number`.
- `lots[]` → UPSERT в `lots` по `lot_id`; `items[]` лота — полная замена
  (`DELETE FROM lot_items WHERE lot_id=? + INSERT`). Это позволяет
  экономисту перетасовывать состав лота без накопления stale-rows.
- Транзакционно: либо все строки документа применяются, либо ни одной
  (rollback на любой ошибке).
- `source` / `confidence` берутся из записи; при отсутствии — из
  `default_source` / `default_confidence` документа; при отсутствии тех —
  `osv` / `1.0` (предположение: ручной ввод экономиста).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_VALID_SOURCES = {"osv", "exif", "manual", "nspd", "llm"}
_VALID_DEAL_TYPES = {"sale", "lease", "other"}
_VALID_ROLES = {"building", "land", "room", "equipment", "structure"}
_LOT_ID_RE = re.compile(r"^[A-Za-z0-9_:/-]+$")


# ─────────────────────────────────────────────────────────────────────────────
#  Контракт документа
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OsvDocument:
    """In-memory представление survey-листа после валидации."""
    schema_version: str
    default_source: str = "osv"
    default_confidence: float = 1.0
    profiles: list[dict[str, Any]] = field(default_factory=list)
    lots: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ApplyReport:
    profiles_inserted: int = 0
    profiles_updated: int = 0
    lots_inserted: int = 0
    lots_updated: int = 0
    lot_items_inserted: int = 0
    lot_items_deleted: int = 0
    dry_run: bool = False


# ─────────────────────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────────────────────

def load_osv(path: str | Path) -> OsvDocument:
    """Прочитать и провалидировать YAML survey-лист.

    Raises:
        FileNotFoundError: если файла нет.
        ValueError: на структурные ошибки (неизвестный source, плохой lot_id,
                    confidence вне 0..1, role вне enum, дубликат cad_number/lot_id).
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Top-level YAML must be a mapping.")

    schema = str(raw.get("schema_version") or "1.0")
    default_source = str(raw.get("default_source") or "osv")
    default_confidence = float(raw.get("default_confidence", 1.0))

    if default_source not in _VALID_SOURCES:
        raise ValueError(f"default_source must be one of {sorted(_VALID_SOURCES)}, got {default_source!r}")
    if not 0.0 <= default_confidence <= 1.0:
        raise ValueError(f"default_confidence must be in [0,1], got {default_confidence}")

    profiles = list(raw.get("profiles") or [])
    lots = list(raw.get("lots") or [])

    _validate_profiles(profiles, default_source, default_confidence)
    _validate_lots(lots)

    return OsvDocument(
        schema_version=schema,
        default_source=default_source,
        default_confidence=default_confidence,
        profiles=profiles,
        lots=lots,
    )


def apply_osv(
    conn: sqlite3.Connection,
    doc: OsvDocument,
    *,
    dry_run: bool = False,
) -> ApplyReport:
    """Применить документ к БД. Транзакционно.

    Returns: ApplyReport с количеством insert/update.
    """
    report = ApplyReport(dry_run=dry_run)
    try:
        for p in doc.profiles:
            inserted = _apply_profile(conn, p, doc.default_source, doc.default_confidence)
            if inserted:
                report.profiles_inserted += 1
            else:
                report.profiles_updated += 1

        for lot in doc.lots:
            ins, items_ins, items_del = _apply_lot(conn, lot)
            if ins:
                report.lots_inserted += 1
            else:
                report.lots_updated += 1
            report.lot_items_inserted += items_ins
            report.lot_items_deleted += items_del

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return report


# ─────────────────────────────────────────────────────────────────────────────
#  Валидация
# ─────────────────────────────────────────────────────────────────────────────

def _validate_profiles(profiles: list[dict], default_src: str, default_conf: float) -> None:
    seen: set[str] = set()
    for i, p in enumerate(profiles):
        if not isinstance(p, dict):
            raise ValueError(f"profiles[{i}] must be a mapping, got {type(p).__name__}")
        cad = p.get("cad_number")
        if not cad or not isinstance(cad, str):
            raise ValueError(f"profiles[{i}].cad_number is required (non-empty string)")
        if cad in seen:
            raise ValueError(f"Duplicate profile for cad_number {cad!r}")
        seen.add(cad)
        src = p.get("source", default_src)
        conf = float(p.get("confidence", default_conf))
        if src not in _VALID_SOURCES:
            raise ValueError(f"profiles[{i}].source must be one of {sorted(_VALID_SOURCES)}, got {src!r}")
        if not 0.0 <= conf <= 1.0:
            raise ValueError(f"profiles[{i}].confidence must be in [0,1], got {conf}")


def _validate_lots(lots: list[dict]) -> None:
    seen: set[str] = set()
    for i, lot in enumerate(lots):
        if not isinstance(lot, dict):
            raise ValueError(f"lots[{i}] must be a mapping, got {type(lot).__name__}")
        lid = lot.get("lot_id")
        if not lid or not isinstance(lid, str):
            raise ValueError(f"lots[{i}].lot_id is required (non-empty string)")
        if not _LOT_ID_RE.match(lid) or len(lid) > 256:
            raise ValueError(
                f"lots[{i}].lot_id must match [A-Za-z0-9_:/-]+ and be ≤256 chars (got {lid!r})"
            )
        if lid in seen:
            raise ValueError(f"Duplicate lot_id {lid!r}")
        seen.add(lid)
        if not lot.get("name"):
            raise ValueError(f"lots[{i}].name is required")
        deal = lot.get("deal_type")
        if deal is not None and deal not in _VALID_DEAL_TYPES:
            raise ValueError(f"lots[{i}].deal_type must be one of {sorted(_VALID_DEAL_TYPES)} or null, got {deal!r}")

        items = lot.get("items") or []
        for j, it in enumerate(items):
            if not isinstance(it, dict):
                raise ValueError(f"lots[{i}].items[{j}] must be a mapping")
            if not it.get("cad_number"):
                raise ValueError(f"lots[{i}].items[{j}].cad_number is required")
            role = it.get("role")
            if role not in _VALID_ROLES:
                raise ValueError(
                    f"lots[{i}].items[{j}].role must be one of {sorted(_VALID_ROLES)}, got {role!r}"
                )


# ─────────────────────────────────────────────────────────────────────────────
#  Apply helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_profile(
    conn: sqlite3.Connection,
    p: dict[str, Any],
    default_src: str,
    default_conf: float,
) -> bool:
    """UPSERT профиля. Возвращает True если insert, False если update."""
    cad = p["cad_number"]
    src = p.get("source", default_src)
    conf = float(p.get("confidence", default_conf))

    existing = conn.execute(
        "SELECT 1 FROM object_etp_profile WHERE cad_number = ?", (cad,)
    ).fetchone()

    def _j(key: str) -> str | None:
        val = p.get(key)
        return json.dumps(val, ensure_ascii=False) if val is not None else None

    if existing:
        conn.execute(
            "UPDATE object_etp_profile SET location_extra=?, building_extra=?, layout=?, "
            "legal_extra=?, risks=?, extras=?, source=?, confidence=?, updated_at=datetime('now') "
            "WHERE cad_number=?",
            (_j("location_extra"), _j("building_extra"), _j("layout"),
             _j("legal_extra"), _j("risks"), _j("extras"), src, conf, cad),
        )
        return False
    else:
        conn.execute(
            "INSERT INTO object_etp_profile(cad_number, location_extra, building_extra, layout,"
            " legal_extra, risks, extras, source, confidence) VALUES (?,?,?,?,?,?,?,?,?)",
            (cad, _j("location_extra"), _j("building_extra"), _j("layout"),
             _j("legal_extra"), _j("risks"), _j("extras"), src, conf),
        )
        return True


def _apply_lot(conn: sqlite3.Connection, lot: dict[str, Any]) -> tuple[bool, int, int]:
    """UPSERT лота + полная замена items. Возвращает (inserted, items_ins, items_del)."""
    lid = lot["lot_id"]
    name = lot["name"]
    platforms = lot.get("platform_targets")
    procedure = lot.get("procedure_type")
    deal = lot.get("deal_type")
    primary = lot.get("primary_cad_number")
    notes = lot.get("notes_md")

    platforms_json = json.dumps(platforms, ensure_ascii=False) if platforms is not None else None

    existing = conn.execute("SELECT 1 FROM lots WHERE lot_id = ?", (lid,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE lots SET name=?, platform_targets=?, procedure_type=?, deal_type=?, "
            "primary_cad_number=?, notes_md=? WHERE lot_id=?",
            (name, platforms_json, procedure, deal, primary, notes, lid),
        )
        inserted = False
    else:
        conn.execute(
            "INSERT INTO lots(lot_id, name, platform_targets, procedure_type, deal_type,"
            " primary_cad_number, notes_md) VALUES (?,?,?,?,?,?,?)",
            (lid, name, platforms_json, procedure, deal, primary, notes),
        )
        inserted = True

    items_del = conn.execute("DELETE FROM lot_items WHERE lot_id = ?", (lid,)).rowcount
    items = lot.get("items") or []
    for it in items:
        conn.execute(
            "INSERT INTO lot_items(lot_id, cad_number, role, ord) VALUES (?,?,?,?)",
            (lid, it["cad_number"], it["role"], int(it.get("ord", 1))),
        )
    return inserted, len(items), max(items_del, 0)
