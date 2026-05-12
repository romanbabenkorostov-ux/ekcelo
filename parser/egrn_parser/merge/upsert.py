"""
egrn_parser/merge/upsert.py — стратегии записи данных в SQLite (ТЗ раздел 9.12).

UPSERT-стратегии:
  land_objects / building_objects → INSERT OR REPLACE + object_events
  accessories / valuations / rights / object_events / right_events
    → INSERT OR IGNORE
  entity_registry / company_groups → INSERT OR IGNORE
  extracts → INSERT OR IGNORE
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from egrn_parser.db.connection import get_connection
from egrn_parser.merge.differ import diff_objects
from egrn_parser.merge.content_hash import compute_content_hash, build_rights_summary

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Запись выписки (extract)
# ─────────────────────────────────────────────────────────────────────────────

def upsert_extract(conn: sqlite3.Connection, header: dict, cad_number: str,
                   object_type: str, content_hash: str, source_filename: str) -> None:
    """Сохранить запись о выписке в таблицу extracts (INSERT OR IGNORE)."""
    conn.execute(
        """
        INSERT OR IGNORE INTO extracts
        (extract_number, extract_date, object_class, cad_number, organ,
         source_format, source_filename, content_hash, total_sheets,
         total_sections, extract_template)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            header.get("extract_number"),
            header.get("extract_date"),
            object_type,
            cad_number,
            header.get("organ"),
            header.get("source_format", "pdf"),
            source_filename,
            content_hash,
            header.get("total_sheets"),
            header.get("total_sections"),
            header.get("extract_template", "full"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Запись земельного участка
# ─────────────────────────────────────────────────────────────────────────────

def upsert_land_object(conn: sqlite3.Connection, obj: dict, policy: str = "replace") -> str:
    """
    Сохранить / обновить земельный участок.

    Стратегия: INSERT OR REPLACE + object_events при изменениях.
    Возвращает действие: 'inserted' | 'replaced' | 'skipped'.
    """
    cad = obj.get("cad_number")
    if not cad:
        return "skipped"

    existing = conn.execute(
        "SELECT * FROM land_objects WHERE cad_number = ?", (cad,)
    ).fetchone()

    if existing:
        existing_dict = dict(existing)
        # Проверка content_hash
        if existing_dict.get("content_hash") == obj.get("content_hash"):
            log.info("Объект %s без изменений (hash совпадает) — пропуск", cad)
            return "skipped"

        changed = diff_objects(existing_dict, obj, "land")
        if changed:
            _create_object_event(conn, "land", cad, "modified", changed,
                                 obj.get("content_hash"))

        if policy == "enrich":
            _enrich_land(conn, existing_dict, obj)
            return "enriched"
        if policy == "ask_enrich":
            from egrn_parser.merge.interactive import ask_enrich_fields
            decisions = ask_enrich_fields(cad, changed)
            _enrich_selective(conn, "land_objects", existing_dict, obj, decisions)
            return "enriched"

    # INSERT OR REPLACE
    conn.execute(
        """
        INSERT OR REPLACE INTO land_objects
        (cad_number, inventory_number, name, quarter_cad_number, registration_date,
         old_numbers, address, cadastral_value, cadastral_value_date,
         lifecycle_status, lifecycle_status_text, deregistration_date,
         permitted_uses, area, area_error, land_category,
         nested_objects, predecessor_cad_numbers, successor_cad_numbers,
         transformation_type, transformation_date, transformation_basis,
         object_restrictions, is_primary, monitored, data_source, source_file,
         enrichment_depth, content_hash, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """,
        (
            cad,
            obj.get("inventory_number"),
            obj.get("name"),
            obj.get("quarter_cad_number"),
            obj.get("registration_date"),
            obj.get("old_numbers"),
            obj.get("address"),
            obj.get("cadastral_value"),
            obj.get("cadastral_value_date"),
            obj.get("lifecycle_status", "active"),
            obj.get("lifecycle_status_text"),
            obj.get("deregistration_date"),
            obj.get("permitted_uses"),
            obj.get("area"),
            obj.get("area_error"),
            obj.get("land_category"),
            obj.get("nested_objects"),
            obj.get("predecessor_cad_numbers"),
            obj.get("successor_cad_numbers"),
            obj.get("transformation_type"),
            obj.get("transformation_date"),
            obj.get("transformation_basis"),
            obj.get("object_restrictions"),
            obj.get("is_primary", 1),
            obj.get("monitored", 0),
            obj.get("data_source"),
            obj.get("source_file"),
            obj.get("enrichment_depth", 0),
            obj.get("content_hash"),
        ),
    )

    if not existing:
        _create_object_event(conn, "land", cad, "created", {}, obj.get("content_hash"))
        return "inserted"
    return "replaced"


def _enrich_land(conn: sqlite3.Connection, existing: dict, new: dict) -> None:
    updates = {}
    for field in ["address", "cadastral_value", "area", "area_error", "land_category",
                  "permitted_uses", "object_restrictions", "content_hash", "name",
                  "registration_date", "old_numbers"]:
        if existing.get(field) is None and new.get(field) is not None:
            updates[field] = new[field]
    # Fix 40a: накопить data_source через "|"
    new_src = new.get("data_source") or new.get("source_file") or ""
    if new_src:
        existing_src = existing.get("data_source") or ""
        if new_src not in existing_src:
            updates["data_source"] = (existing_src + " | " + new_src).strip(" |")
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE land_objects SET {set_clause}, updated_at = datetime('now') WHERE cad_number = ?",
            list(updates.values()) + [existing["cad_number"]],
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Запись здания / помещения / сооружения
# ─────────────────────────────────────────────────────────────────────────────

def upsert_building_object(conn: sqlite3.Connection, obj: dict, policy: str = "replace") -> str:
    """Сохранить / обновить ОКС."""
    cad = obj.get("cad_number")
    if not cad:
        return "skipped"

    existing = conn.execute(
        "SELECT * FROM building_objects WHERE cad_number = ?", (cad,)
    ).fetchone()

    if existing:
        existing_dict = dict(existing)
        if existing_dict.get("content_hash") == obj.get("content_hash"):
            log.info("Объект %s без изменений — пропуск", cad)
            return "skipped"

        changed = diff_objects(existing_dict, obj, obj.get("object_type", "building"))
        if changed:
            _create_object_event(conn, "building", cad, "modified", changed,
                                 obj.get("content_hash"))

        if policy == "enrich":
            _enrich_building(conn, existing_dict, obj)
            return "enriched"
        if policy == "ask_enrich":
            from egrn_parser.merge.interactive import ask_enrich_fields
            decisions = ask_enrich_fields(cad, changed)
            _enrich_selective(conn, "building_objects", existing_dict, obj, decisions)
            return "enriched"

    # Fix 38a: если area есть, а main_value нет → заполнить основную характеристику из площади
    if obj.get("area") and not obj.get("main_value"):
        obj.setdefault("main_char_type", "площадь")
        obj["main_value"] = obj["area"]
        obj.setdefault("main_unit", "в квадратных метрах")

    conn.execute(
        """
        INSERT OR REPLACE INTO building_objects
        (cad_number, inventory_number, object_type, quarter_cad_number,
         registration_date, old_numbers, address, cadastral_value, cadastral_value_date,
         lifecycle_status, lifecycle_status_text, deregistration_date,
         area, name, purpose, purpose_code,
         floors_total, floors_above_ground, underground_floors,
         floors_inspection, condition_inspection, wall_material,
         year_used, year_built, land_cad_numbers,
         room_type, floor, plan_number, parent_cad_number, parent_object_class,
         parent_floors_above_ground, parent_underground_floors,
         main_char_type, main_value, main_unit,
         predecessor_cad_numbers, successor_cad_numbers,
         transformation_type, transformation_date, transformation_basis,
         object_restrictions, is_primary, monitored, data_source,
         enrichment_depth, content_hash, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """,
        (
            cad,
            obj.get("inventory_number"),
            obj.get("object_type", "building"),
            obj.get("quarter_cad_number"),
            obj.get("registration_date"),
            obj.get("old_numbers"),
            obj.get("address"),
            obj.get("cadastral_value"),
            obj.get("cadastral_value_date"),
            obj.get("lifecycle_status", "active"),
            obj.get("lifecycle_status_text"),
            obj.get("deregistration_date"),
            obj.get("area"),
            obj.get("name"),
            obj.get("purpose"),
            obj.get("purpose_code"),
            obj.get("floors_total"),
            obj.get("floors_above_ground"),
            obj.get("underground_floors"),
            obj.get("floors_inspection"),
            obj.get("condition_inspection"),
            obj.get("wall_material"),
            obj.get("year_used"),
            obj.get("year_built"),
            obj.get("land_cad_numbers"),
            obj.get("room_type"),
            obj.get("floor"),
            obj.get("plan_number"),
            obj.get("parent_cad_number"),
            obj.get("parent_object_class"),
            obj.get("parent_floors_above_ground"),
            obj.get("parent_underground_floors"),
            obj.get("main_char_type"),
            obj.get("main_value"),
            obj.get("main_unit"),
            obj.get("predecessor_cad_numbers"),
            obj.get("successor_cad_numbers"),
            obj.get("transformation_type"),
            obj.get("transformation_date"),
            obj.get("transformation_basis"),
            obj.get("object_restrictions"),
            obj.get("is_primary", 1),
            obj.get("monitored", 0),
            obj.get("data_source"),
            obj.get("enrichment_depth", 0),
            obj.get("content_hash"),
        ),
    )

    if not existing:
        _create_object_event(conn, "building", cad, "created", {}, obj.get("content_hash"))
        return "inserted"
    return "replaced"


def _enrich_building(conn: sqlite3.Connection, existing: dict, new: dict) -> None:
    updates = {}
    for field in ["address", "cadastral_value", "area", "name", "purpose",
                  "floors_total", "floors_above_ground", "underground_floors",
                  "object_restrictions", "land_cad_numbers", "parent_cad_number", "content_hash"]:
        if existing.get(field) is None and new.get(field) is not None:
            updates[field] = new[field]
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE building_objects SET {set_clause}, updated_at = datetime('now') WHERE cad_number = ?",
            list(updates.values()) + [existing["cad_number"]],
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Запись прав / правообладателей
# ─────────────────────────────────────────────────────────────────────────────

def upsert_right(conn: sqlite3.Connection, right: dict) -> Optional[int]:
    """
    Сохранить право/обременение/ограничение (INSERT OR IGNORE по right_number).
    Возвращает right_id или None.
    """
    right_number = right.get("right_number")

    if right_number:
        existing = conn.execute(
            "SELECT right_id FROM rights WHERE right_number = ?", (right_number,)
        ).fetchone()
        if existing:
            return existing["right_id"]

    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO rights
            (object_class, object_key_type, object_key_value, right_category,
             right_type, right_type_code, right_number, right_date,
             share_numerator, share_denominator,
             valid_from, valid_until, valid_duration_years,
             beneficiary_name, beneficiary_inn, basis,
             lease_term_description, lease_party_type,
             lease_partial, lease_partial_measure_type, lease_partial_qty, lease_partial_unit,
             servitude_part_number, servitude_is_public,
             personal_participation_req, claim_records,
             source_extract_number, source_format, source_file, is_active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                right.get("object_class", "building"),
                right.get("object_key_type", "cad_number"),
                right.get("object_key_value"),
                right.get("right_category", "right"),
                right.get("right_type"),
                right.get("right_type_code"),
                right_number,
                right.get("right_date"),
                right.get("share_numerator"),
                right.get("share_denominator"),
                right.get("valid_from"),
                right.get("valid_until"),
                right.get("valid_duration_years"),
                right.get("beneficiary_name"),
                right.get("beneficiary_inn"),
                right.get("basis"),
                right.get("lease_term_description"),
                right.get("lease_party_type"),
                right.get("lease_partial", 0),
                right.get("lease_partial_measure_type"),
                right.get("lease_partial_qty"),
                right.get("lease_partial_unit"),
                right.get("servitude_part_number"),
                right.get("servitude_is_public", 0),
                right.get("personal_participation_req", 0),
                right.get("claim_records"),
                right.get("source_extract_number"),
                right.get("source_format"),
                right.get("source_file"),
                right.get("is_active", 1),
            ),
        )
        right_id_row = conn.execute("SELECT last_insert_rowid()").fetchone()
        return right_id_row[0] if right_id_row else None
    except sqlite3.Error as e:
        log.warning("Ошибка при записи права %s: %s", right_number, e)
        return None


def upsert_right_holder(conn: sqlite3.Connection, right_id: int, holder: dict) -> None:
    """Сохранить правообладателя + entity_registry (Fix 25, Fix 40g)."""
    if right_id is None or holder is None:
        return

    inn  = holder.get("inn")
    name = holder.get("name")
    ogrn = holder.get("ogrn")
    holder_type = holder.get("holder_type", "unknown")
    # Fix 40g: нормализовать ООО/ПАО/АО в имени правообладателя
    if name:
        from egrn_parser.parsers.pdf_parser import _normalize_org_name
        name = _normalize_org_name(name)

    # entity_registry — INSERT OR IGNORE по INN
    if inn:
        entity_type = {
            "individual":   "individual",
            "legal_entity": "legal_entity",
            "public":       "public_entity",
            "municipal":    "public_entity",
        }.get(holder_type, "legal_entity")
        conn.execute(
            """INSERT OR IGNORE INTO entity_registry
               (inn, ogrn, entity_type, name_full, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (inn, ogrn, entity_type, name),
        )
        # Обновить имя если было пустым
        if name:
            conn.execute(
                """UPDATE entity_registry
                   SET name_full = COALESCE(NULLIF(name_full,''), ?),
                       updated_at = datetime('now')
                   WHERE inn = ?""",
                (name, inn),
            )

    # Fix 40f: UUID для физлиц (у которых нет ИНН)
    import uuid as _uuid
    subject_uuid = None
    if holder_type == "individual" and not inn:
        # Использовать имя как seed для стабильного UUID
        subject_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_OID, name or "unknown_individual"))

    conn.execute(
        """INSERT INTO right_holders
           (right_id, holder_type, name, inn, ogrn, email, mailing_address,
            subject_uuid, first_seen_file)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (right_id, holder_type, name, inn, ogrn,
         holder.get("email"), holder.get("mailing_address"),
         subject_uuid, holder.get("source_file") or holder.get("first_seen_file")),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Запись принадлежностей и оценок
# ─────────────────────────────────────────────────────────────────────────────

def upsert_accessory(conn: sqlite3.Connection, acc: dict) -> Optional[int]:
    """INSERT OR IGNORE для принадлежности."""
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO accessories
            (item_name, inventory_number, re_cad_number, re_object_class,
             cad_number_fragment, entity_name, entity_inn,
             period_from, period_to, account_code,
             right_category, right_type, is_disposed, disposed_date, source_file)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                acc.get("item_name"),
                acc.get("inventory_number"),
                acc.get("re_cad_number"),
                acc.get("re_object_class"),
                acc.get("cad_number_fragment"),
                acc.get("entity_name"),
                acc.get("entity_inn"),
                acc.get("period_from"),
                acc.get("period_to"),
                acc.get("account_code"),
                acc.get("right_category"),
                acc.get("right_type"),
                acc.get("is_disposed", 0),
                acc.get("disposed_date"),
                acc.get("source_file"),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0] if row else None
    except sqlite3.Error as e:
        log.warning("Ошибка записи принадлежности «%s»: %s", acc.get("item_name"), e)
        return None


def upsert_valuation(conn: sqlite3.Connection, val: dict) -> None:
    """INSERT OR IGNORE для оценки стоимости."""
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO valuations
            (object_class, cad_number, accessory_name, inventory_number,
             valuation_type, amount, currency, doc_date,
             period_label, source_file, source_type, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                val.get("object_class"),
                val.get("cad_number"),
                val.get("accessory_name"),
                val.get("inventory_number"),
                val.get("valuation_type"),
                val.get("amount"),
                val.get("currency", "RUB"),
                val.get("doc_date"),
                val.get("period_label"),
                val.get("source_file"),
                val.get("source_type", "osv"),
                val.get("notes"),
            ),
        )
    except sqlite3.Error as e:
        log.warning("Ошибка записи оценки %s: %s", val.get("valuation_type"), e)


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _create_object_event(
    conn: sqlite3.Connection,
    object_class: str,
    cad_number: str,
    event_type: str,
    changed_fields: dict,
    content_hash: Optional[str],
) -> None:
    """Добавить запись в object_events (INSERT OR IGNORE по cad+seq)."""
    # Получить следующий seq
    row = conn.execute(
        "SELECT COALESCE(MAX(event_seq), 0) + 1 FROM object_events WHERE cad_number = ?",
        (cad_number,),
    ).fetchone()
    event_seq = row[0]

    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO object_events
            (object_class, cad_number, event_seq, event_type, event_date,
             changed_fields, source_extract_number)
            VALUES (?,?,?,?,datetime('now'),?,?)
            """,
            (
                object_class,
                cad_number,
                event_seq,
                event_type,
                json.dumps(changed_fields, ensure_ascii=False, default=str) if changed_fields else None,
                content_hash,
            ),
        )
    except sqlite3.Error as e:
        log.warning("Ошибка записи event для %s: %s", cad_number, e)


# ─────────────────────────────────────────────────────────────────────────────
#  Главная функция: сохранить результат парсинга
# ─────────────────────────────────────────────────────────────────────────────

def save_parsed_result(
    db_path: Path | str,
    parsed: dict,
    policy: str = "replace",
) -> dict:
    """
    Сохранить полный результат парсинга (из parse_egrn_pdf / parse_egrn_xml)
    в SQLite.

    Возвращает статистику: {"inserted": N, "replaced": N, "skipped": N, ...}
    """
    from egrn_parser.db.seeds import load_dictionaries

    db_path = Path(db_path)
    stats: dict[str, int] = {"inserted": 0, "replaced": 0, "skipped": 0,
                              "rights": 0, "errors": 0}

    obj_data   = parsed.get("object", {})
    header     = parsed.get("header", {})
    rights     = parsed.get("rights", [])
    object_type = parsed.get("object_type", "unknown")
    cad_number  = parsed.get("cad_number")

    if not cad_number:
        log.error("save_parsed_result: нет cad_number")
        stats["errors"] += 1
        return stats

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")
        try:
            # 1. Выписка
            upsert_extract(
                conn, header, cad_number, object_type,
                obj_data.get("content_hash", ""),
                parsed.get("source_filename", ""),
            )

            # 2. Объект
            if object_type == "land":
                action = upsert_land_object(conn, obj_data, policy)
            else:
                action = upsert_building_object(conn, obj_data, policy)
            stats[action] = stats.get(action, 0) + 1

            # 3. Права / обременения / ограничения прав
            for right in rights:
                right_id = upsert_right(conn, right)
                if right_id and right.get("_holders"):
                    for holder in right["_holders"]:
                        upsert_right_holder(conn, right_id, holder)
                if right_id:
                    stats["rights"] += 1

            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            log.error("Ошибка сохранения %s: %s", cad_number, exc)
            stats["errors"] += 1
            raise

    return stats


def save_osv_result(
    db_path: Path | str,
    osv_data: dict,
    include_accessories: bool = True,
) -> dict:
    """Сохранить результат парсинга ОСВ."""
    db_path = Path(db_path)
    stats = {"accessories": 0, "valuations": 0, "errors": 0}

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")
        try:
            if include_accessories:
                for acc in osv_data.get("accessories", []):
                    upsert_accessory(conn, acc)
                    stats["accessories"] += 1

            for val in osv_data.get("valuations", []):
                upsert_valuation(conn, val)
                stats["valuations"] += 1

            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            log.error("Ошибка сохранения ОСВ: %s", exc)
            stats["errors"] += 1
            raise

    return stats

def _enrich_selective(conn, table: str, existing: dict, new: dict, decisions: dict) -> None:
    """Применить только выбранные пользователем поля при обогащении."""
    updates = {}
    for field, decision in decisions.items():
        if decision == "accept" and new.get(field) is not None:
            updates[field] = new[field]
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE {table} SET {set_clause}, updated_at = datetime('now') WHERE cad_number = ?",
            list(updates.values()) + [existing["cad_number"]],
        )
