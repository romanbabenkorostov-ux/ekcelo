"""
egrn_parser/parsers/xml_parser.py — парсер XML-выписок ЕГРН.

Корневые теги:
  extract_about_property_land         → land
  extract_about_property_build        → building
  extract_about_property_room         → room
  extract_about_property_construction → structure
  extract_about_property_parking      → parking
  extract_about_property_ons          → ons

Поля «personal_data_consent_*» / «personal_data_provision_*»
и теги <recipient_statement> НИКОГДА не сохраняются.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from egrn_parser.parsers._common import (
    parse_date_any,
    parse_date_ru,
    parse_number,
    parse_share,
    extract_all_cad_numbers,
    normalize_cad_number,
    cad_quarter,
    extract_inn,
    normalize_whitespace,
    is_absent,
    clean_value,
)
from egrn_parser.utils.personal_data_filter import filter_personal_data
from egrn_parser.parsers.pdf_parser import _clean_status_text
from egrn_parser.parsers.restrictions_common import classify_restriction_type
from egrn_parser.dictionaries import (
    OBJECT_TYPE_RU_TO_CODE,
    XML_ROOT_TO_OBJECT_TYPE,
    RIGHT_TYPE_RU_TO_CODE,
    ENCUMBRANCE_RU_TO_CODE,
)

log = logging.getLogger(__name__)

# Теги персональных данных для пропуска при обходе XML
_PERSONAL_DATA_TAGS = frozenset({
    "personal_data_consent",
    "personal_data_provision",
    "personal_data_consent_info",
    "personal_data_provision_info",
    "recipient_statement",  # получатель выписки — не сохраняем
})


def _is_egrn_xml(xml_path: Path) -> bool:
    """Проверить, является ли файл XML-выпиской ЕГРН."""
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        tag = root.tag.lower().split("}")[-1]  # убрать namespace
        return tag in XML_ROOT_TO_OBJECT_TYPE or "extract_about_property" in tag
    except Exception:
        return False


def _tag(elem) -> str:
    """Получить локальное имя тега без namespace."""
    tag = elem.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.lower()


def _text(elem, default: str = "") -> str:
    """Получить текст элемента или default."""
    if elem is None:
        return default
    return (elem.text or "").strip()


def _find(root, *path) -> Optional[ET.Element]:
    """Найти вложенный элемент по цепочке локальных тегов."""
    current = root
    for tag in path:
        if current is None:
            return None
        found = None
        for child in current:
            if _tag(child) == tag.lower():
                found = child
                break
        current = found
    return current


def _findall(root, tag: str) -> list[ET.Element]:
    """Найти все прямые дочерние элементы с данным локальным тегом."""
    return [child for child in root if _tag(child) == tag.lower()]


def _find_text(root, *path) -> Optional[str]:
    """Найти текст по пути тегов."""
    elem = _find(root, *path)
    if elem is None:
        return None
    t = _text(elem)
    return None if is_absent(t) else t


def _find_recursive(root, tag: str) -> Optional[ET.Element]:
    """Найти первый элемент с тегом рекурсивно по всему дереву."""
    tag_low = tag.lower()
    for elem in root.iter():
        if _tag(elem) == tag_low:
            return elem
    return None


def _find_all_recursive(root, tag: str) -> list[ET.Element]:
    """Найти все элементы с тегом рекурсивно."""
    tag_low = tag.lower()
    return [e for e in root.iter() if _tag(e) == tag_low]


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг общих данных объекта
# ─────────────────────────────────────────────────────────────────────────────


def _parse_xml_old_numbers(root: ET.Element) -> Optional[str]:
    """Извлечь ранее присвоенные номера из <old_numbers><old_number> (Fix 38c).
    
    Формат вывода: plain text «Инвентарный номер 143/2; Условный номер 61-...»
    """
    old_ns = _find_recursive(root, "old_numbers")
    if old_ns is None:
        return None
    parts = []
    for old_num in old_ns:
        if _tag(old_num) != "old_number":
            continue
        type_e = _find(old_num, "number_type")
        num_e  = _find(old_num, "number")
        num_text = _text(num_e)
        if not num_text or is_absent(num_text):
            continue
        type_text = None
        if type_e is not None:
            val_e = _find(type_e, "value")
            type_text = _text(val_e) if val_e is not None else _text(type_e)
        part = f"{type_text} {num_text}".strip() if type_text else num_text
        if part and part not in parts:
            parts.append(part)
    return "; ".join(parts) if parts else None


def _parse_common_data(root: ET.Element, object_type: str) -> dict:
    """Общие поля для всех типов объектов."""
    result: dict[str, Any] = {}

    # Кадастровый номер
    cad_elem = _find_recursive(root, "cad_number")
    result["cad_number"] = _text(cad_elem) if cad_elem is not None else None

    # Кадастровый квартал
    quarter_elem = _find_recursive(root, "quarter_cad_number")
    result["quarter_cad_number"] = _text(quarter_elem) if quarter_elem is not None else None
    if result["cad_number"] and not result["quarter_cad_number"]:
        result["quarter_cad_number"] = cad_quarter(result["cad_number"])

    # Адрес
    addr_elem = _find_recursive(root, "readable_address")
    result["address"] = clean_value(_text(addr_elem))

    # Кадастровая стоимость
    cost_elem = _find_recursive(root, "cost")
    val_elem  = _find(cost_elem, "value") if cost_elem is not None else None
    result["cadastral_value"] = parse_number(_text(val_elem) if val_elem is not None else "")

    # Статус
    status_elem = _find_recursive(root, "status")
    status_text = _text(status_elem)
    result["lifecycle_status"] = (
        "deregistered" if status_text and "снят" in status_text.lower() else "active"
    )
    result["lifecycle_status_text"] = _clean_status_text(status_text) if status_text else None

    # Дата регистрации в ЕГРН — приоритет: <record_info><registration_date>
    # (не из <right_records> которые содержат даты регистрации прав)
    record_info_e = _find(root, "record_info")
    if record_info_e is None:
        # Попробовать найти в *_record элементах (land_record, room_record, etc.)
        for child in root:
            if "record" in _tag(child):
                ri = _find(child, "record_info")
                if ri is not None:
                    record_info_e = ri
                    break
    if record_info_e is not None:
        reg_e = _find(record_info_e, "registration_date")
        result["registration_date"] = parse_date_any(_text(reg_e)) if reg_e is not None else None
    else:
        reg_elem = _find_recursive(root, "registration_date")
        result["registration_date"] = parse_date_any(_text(reg_elem)) if reg_elem is not None else None

    # Ранее присвоенные государственные учётные номера (Fix 38c)
    result["old_numbers"] = _parse_xml_old_numbers(root)

    # Трансформации: предшественники / преемники
    prev_nums = [_text(e) for e in _find_all_recursive(root, "prev_cad_number")
                 if _find_recursive(e, "cad_number") is not None]
    prev_cads = [_text(_find_recursive(e, "cad_number")) for e in _find_all_recursive(root, "prev_cad_number")]
    prev_cads = [c for c in prev_cads if c]

    new_cads = [_text(_find_recursive(e, "cad_number")) for e in _find_all_recursive(root, "new_cad_number")]
    new_cads = [c for c in new_cads if c]

    result["predecessor_cad_numbers"] = json.dumps(prev_cads, ensure_ascii=False) if prev_cads else None
    result["successor_cad_numbers"]   = json.dumps(new_cads, ensure_ascii=False) if new_cads else None

    return result


def _parse_land_params(root: ET.Element) -> dict:
    """Специфичные поля земельного участка (Fix 26: category, area+inaccuracy, permitted_use)."""
    result: dict[str, Any] = {}

    # Площадь + погрешность из <area><value>/<inaccuracy>
    area_top = _find_recursive(root, "area")
    if area_top is not None:
        val_e  = _find(area_top, "value")
        inac_e = _find(area_top, "inaccuracy")
        result["area"]       = parse_number(_text(val_e))
        result["area_error"] = parse_number(_text(inac_e)) if inac_e is not None else None

    # Категория земель из <category><type><value>
    cat_elem = _find_recursive(root, "category")
    if cat_elem is not None:
        type_e = _find(cat_elem, "type")
        if type_e is not None:
            val_e = _find(type_e, "value")
            result["land_category"] = clean_value(_text(val_e))
        if not result.get("land_category"):
            val_e = _find(cat_elem, "value")
            result["land_category"] = clean_value(_text(val_e) or _text(cat_elem))

    # ВРИ из <permitted_use_established><by_document> и <permitted_use><value>
    perm_uses = []
    for pu_elem in _find_all_recursive(root, "permitted_use_established"):
        by_doc = _find(pu_elem, "by_document")
        if by_doc is not None and _text(by_doc) and not is_absent(_text(by_doc)):
            perm_uses.append(_text(by_doc))
    if not perm_uses:
        for pe in _find_all_recursive(root, "permitted_use"):
            val_e = _find(pe, "value")
            t = _text(val_e) if val_e is not None else _text(pe)
            if t and not is_absent(t) and t not in perm_uses:
                perm_uses.append(t)
    result["permitted_uses"] = "; ".join(perm_uses) if perm_uses else None

    # Вложенные объекты
    nested = [_text(_find_recursive(e, "cad_number"))
              for e in _find_all_recursive(root, "inner_cadastral_numbers")]
    result["nested_objects"] = "; ".join(c for c in nested if c) or None

    return result

def _parse_building_params(root: ET.Element) -> dict:
    """Специфичные поля здания."""
    result: dict[str, Any] = {}

    params = _find_recursive(root, "params")
    if params is not None:
        area_e = _find(params, "area")
        result["area"] = parse_number(_text(area_e))

        name_e = _find(params, "name")
        result["name"] = clean_value(_text(name_e))

        purpose_e = _find(params, "purpose")
        if purpose_e is not None:
            pv = _find(purpose_e, "value")
            result["purpose"] = clean_value(_text(pv) or _text(purpose_e))
            pc = _find(purpose_e, "code")
            result["purpose_code"] = _text(pc) if pc is not None else None

        # Этажность
        floors_e = _find(params, "floors")
        if floors_e is not None:
            result["floors_total"] = int(_text(floors_e)) if _text(floors_e).isdigit() else None

        ug_e = _find(params, "underground_floors")
        if ug_e is not None and _text(ug_e).isdigit():
            result["underground_floors"] = int(_text(ug_e))
        else:
            result["underground_floors"] = 0

        # floors_above_ground = floors_total - underground_floors
        ft  = result.get("floors_total")
        fug = result.get("underground_floors", 0) or 0
        if ft is not None:
            result["floors_above_ground"] = ft - fug

        year_e = _find(params, "year_built")
        result["year_built"] = int(_text(year_e)) if _text(year_e).isdigit() else None

    # ЗУ-носители
    land_cad_elems = _find_all_recursive(root, "land_cad_number")
    land_cads = [_text(_find_recursive(e, "cad_number")) for e in land_cad_elems]
    land_cads = [c for c in land_cads if c]
    result["land_cad_numbers"] = "; ".join(land_cads) if land_cads else None

    return result


def _parse_room_params(root: ET.Element) -> dict:
    """Специфичные поля помещения."""
    result: dict[str, Any] = {}

    params = _find_recursive(root, "params")
    if params is not None:
        area_e = _find(params, "area")
        result["area"] = parse_number(_text(area_e))

        name_e = _find(params, "name")
        result["name"] = clean_value(_text(name_e))

        purpose_e = _find(params, "purpose")
        if purpose_e is not None:
            pv = _find(purpose_e, "value")
            result["purpose"] = clean_value(_text(pv) or _text(purpose_e))

        room_type_e = _find(params, "type")
        if room_type_e is not None:
            rtv = _find(room_type_e, "value")
            result["room_type"] = clean_value(_text(rtv) or _text(room_type_e))

    # Родительский объект (здание)
    parent_elems = _find_all_recursive(root, "parent_cad_number")
    for pe in parent_elems:
        cad_e = _find_recursive(pe, "cad_number")
        if cad_e is not None:
            result["parent_cad_number"] = _text(cad_e)
            break

    # Если нет явного parent_cad_number — ищем в build_record
    if not result.get("parent_cad_number"):
        build_cad = _find_recursive(root, "build_cad_number")
        if build_cad is not None:
            result["parent_cad_number"] = _text(build_cad)

    return result


def _parse_structure_params(root: ET.Element) -> dict:
    """Специфичные поля сооружения."""
    result: dict[str, Any] = {}

    params = _find_recursive(root, "params")
    if params is not None:
        name_e = _find(params, "name")
        result["name"] = clean_value(_text(name_e))

        purpose_e = _find(params, "purpose")
        if purpose_e is not None:
            pv = _find(purpose_e, "value")
            result["purpose"] = clean_value(_text(pv) or _text(purpose_e))

        # Основная характеристика
        mc_e = _find(params, "main_characteristics")
        if mc_e is not None:
            type_e  = _find(mc_e, "type")
            value_e = _find(mc_e, "value")
            unit_e  = _find(mc_e, "unit")
            result["main_char_type"] = clean_value(_text(type_e))
            result["main_value"]     = parse_number(_text(value_e))
            result["main_unit"]      = clean_value(_text(unit_e))

        year_e = _find(params, "year_built")
        result["year_built"] = int(_text(year_e)) if _text(year_e).isdigit() else None

    # ЗУ-носители
    land_cad_elems = _find_all_recursive(root, "land_cad_number")
    land_cads = [_text(_find_recursive(e, "cad_number")) for e in land_cad_elems]
    land_cads = [c for c in land_cads if c]
    result["land_cad_numbers"] = "; ".join(land_cads) if land_cads else None

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг прав и обременений из XML
# ─────────────────────────────────────────────────────────────────────────────

def _parse_xml_rights(root: ET.Element, cad_number: str, object_type: str, extract_number: Optional[str]) -> list[dict]:
    """Разобрать записи прав/обременений из XML (right_records, restrict_records)."""
    rights: list[dict] = []

    # ── Права (right_records) ────────────────────────────────────────────────
    for right_rec in _find_all_recursive(root, "right_record"):
        # Пропускаем теги персональных данных
        rec = _parse_xml_right_record(right_rec, cad_number, object_type, extract_number, "right")
        if rec:
            rights.append(rec)

    # ── Обременения/ограничения прав (restrict_records) ──────────────────────
    for restr_rec in _find_all_recursive(root, "restrict_record"):
        rec = _parse_xml_restrict_record(restr_rec, cad_number, object_type, extract_number)
        if rec:
            rights.append(rec)

    return rights


def _parse_xml_restrict_record(
    rec_elem,
    cad_number: str,
    object_type: str,
    extract_number,
) -> dict:
    """Парсинг restrict_record (обременения/ограничения прав из XML) (Fix 27)."""
    from egrn_parser.parsers._common import parse_date_any
    rec: dict = {
        "object_class":      object_type,
        "object_key_type":   "cad_number",
        "object_key_value":  cad_number,
        "is_active":         1,
        "source_extract_number": extract_number,
        "source_format":     "xml",
    }

    # Данные обременения из <restrictions_encumbrances_data>
    enc_data = _find(rec_elem, "restrictions_encumbrances_data")
    if enc_data is None:
        return None

    # Номер
    num_e = _find(enc_data, "restriction_encumbrance_number")
    rec["right_number"] = clean_value(_text(num_e))

    # Тип
    enc_type_e = _find(enc_data, "restriction_encumbrance_type")
    if enc_type_e is not None:
        val_e = _find(enc_type_e, "value")
        enc_type_str = _text(val_e) or _text(enc_type_e)
        rec["right_type"] = clean_value(enc_type_str)
        from egrn_parser.dictionaries import ENCUMBRANCE_RU_TO_CODE
        code = ENCUMBRANCE_RU_TO_CODE.get((enc_type_str or "").lower(), "other")
        rec["right_type_code"] = code

    # Категория: restriction если нет бенефициара, encumbrance если есть
    holders_e = _find(rec_elem, "right_holders")
    has_defined_holder = False
    if holders_e is not None:
        for h in holders_e:
            for sub in h:
                if _tag(sub) != "undefined":
                    has_defined_holder = True
                    break
    rec["right_category"] = "encumbrance" if has_defined_holder else "restriction"

    # Дата регистрации
    rec_info = _find(rec_elem, "record_info")
    date_e = _find_recursive(rec_info, "registration_date") if rec_info is not None else None
    if date_e is not None:
        rec["right_date"] = parse_date_any(_text(date_e))

    # Срок
    start_e = _find_recursive(enc_data, "start_date") or _find_recursive(enc_data, "starting_date")
    end_e   = _find_recursive(enc_data, "end_date")
    if start_e is not None:
        rec["valid_from"] = parse_date_any(_text(start_e))
    if end_e is not None:
        rec["valid_until"] = parse_date_any(_text(end_e))

    # Документ-основание
    doc_e = _find_recursive(rec_elem, "underlying_document")
    if doc_e is not None:
        basis_parts = [
            _text(_find(doc_e, "document_name")),
            _text(_find(doc_e, "document_number")),
            _text(_find(doc_e, "document_date")),
            _text(_find(doc_e, "document_issuer")),
        ]
        rec["basis"] = ", ".join(p for p in basis_parts if p and not is_absent(p))[:500]

    if not rec.get("right_number"):
        return None

    from egrn_parser.utils.personal_data_filter import filter_personal_data
    return filter_personal_data(rec)


def _parse_xml_right_record(
    rec_elem: ET.Element,
    cad_number: str,
    object_type: str,
    extract_number: Optional[str],
    default_category: str,
) -> Optional[dict]:
    """Разобрать один элемент right_record или restrict_record."""
    rec: dict[str, Any] = {
        "object_class":      object_type if object_type != "unknown" else "building",
        "object_key_type":   "cad_number",
        "object_key_value":  cad_number,
        "is_active":         1,
        "source_extract_number": extract_number,
        "source_format":     "xml",
    }

    # Вид права
    right_type_e = _find_recursive(rec_elem, "right_type")
    if right_type_e is not None:
        type_val_e = _find(right_type_e, "value")
        rt = _text(type_val_e) if type_val_e is not None else _text(right_type_e)
        rec["right_type"] = clean_value(rt)
        code = RIGHT_TYPE_RU_TO_CODE.get((rt or "").lower(), None)
        if code:
            rec["right_type_code"] = code
            rec["right_category"]  = "right"
        else:
            code = ENCUMBRANCE_RU_TO_CODE.get((rt or "").lower(), "other")
            rec["right_type_code"] = code
            rec["right_category"]  = "encumbrance"
    else:
        rec["right_category"] = default_category

    # Номер права
    right_num_e = _find_recursive(rec_elem, "right_number")
    if right_num_e is None:
        right_num_e = _find_recursive(rec_elem, "number")
    rec["right_number"] = clean_value(_text(right_num_e))

    # Дата регистрации из <record_info> (приоритет) или <right_data>
    record_info = _find(rec_elem, "record_info")
    right_date_e = (_find_recursive(record_info, "registration_date")
                    if record_info is not None
                    else _find_recursive(rec_elem, "registration_date"))
    if right_date_e is not None:
        rec["right_date"] = parse_date_any(_text(right_date_e))

    # Доля
    share_e = _find_recursive(rec_elem, "share")
    if share_e is not None:
        # Числитель/знаменатель из дочерних элементов <numerator>/<denominator>
        num_e = _find(share_e, "numerator")
        den_e = _find(share_e, "denominator")
        if num_e is not None and den_e is not None:
            try:
                rec["share_numerator"]   = int(_text(num_e))
                rec["share_denominator"] = int(_text(den_e))
            except ValueError:
                pass
        else:
            num, den = parse_share(_text(share_e))
            rec["share_numerator"]   = num
            rec["share_denominator"] = den

    # Правообладатели (пропускаем personal_data_*)
    holders = []
    for holder_e in _find_all_recursive(rec_elem, "right_holder"):
        holder_info = _parse_xml_holder(holder_e)
        if holder_info:
            holders.append(holder_info)
    rec["_holders"] = holders  # временный ключ, убирается при записи в БД

    # Определить категорию по наличию бенефициара
    if rec["right_category"] == "encumbrance" and holders:
        # Если есть держатель — это обременение
        pass
    elif rec["right_category"] == "encumbrance" and not holders:
        rec["right_category"] = "restriction"

    # Срок
    duration_e = _find_recursive(rec_elem, "duration")
    if duration_e is not None:
        from egrn_parser.parsers._common import parse_term
        term_text = " ".join(c.text or "" for c in duration_e)
        term = parse_term(term_text)
        rec.update(term)

    return filter_personal_data(rec)


def _parse_xml_holder(holder_elem: ET.Element) -> Optional[dict]:
    """Разобрать правообладателя из XML, игнорируя персональные данные."""
    result: dict[str, Any] = {}

    # Пропустить элементы с тегами персональных данных
    for child in holder_elem:
        child_tag = _tag(child)
        if any(pd_tag in child_tag for pd_tag in _PERSONAL_DATA_TAGS):
            continue

    # ЮЛ — несколько вариантов структуры XML
    org_e = _find(holder_elem, "organization")
    if org_e is None:
        org_e = _find(holder_elem, "legal_entity")
    if org_e is not None:
        # Имя может быть в <name>, <full_name>, <entity/resident/name>
        name_e = (_find(org_e, "name")
                  or _find_recursive(org_e, "full_name")
                  or _find_recursive(org_e, "name"))
        inn_e  = _find_recursive(org_e, "inn")
        ogrn_e = _find_recursive(org_e, "ogrn")
        result["holder_type"] = "legal_entity"
        result["name"] = clean_value(_text(name_e) if name_e is not None else None)
        result["inn"]  = _text(inn_e) if inn_e is not None else None
        result["ogrn"] = _text(ogrn_e) if ogrn_e is not None else None
        return result

    # Публичный субъект — структура: <public_formation><public_formation_type><russia><name><value>
    pub_e = _find(holder_elem, "public_formation")
    if pub_e is None:
        pub_e = _find(holder_elem, "subject_rf")
    if pub_e is not None:
        # Ищем имя рекурсивно — может быть в <russia><name><value> или <name><value>
        val_e = _find_recursive(pub_e, "value")
        name_e = _find(pub_e, "name")
        name_text = (_text(val_e) if val_e is not None
                     else (_text(name_e) if name_e is not None else "Российская Федерация"))
        result["holder_type"] = "public"
        result["name"] = clean_value(name_text)
        return result

    # Физлицо — сохраняем только если есть ИНН (без ФИО)
    phys_e = _find(holder_elem, "individual") or _find(holder_elem, "person")
    if phys_e is not None:
        inn_e = _find(phys_e, "inn") or _find_recursive(phys_e, "inn")
        result["holder_type"] = "individual"
        result["inn"]  = _text(inn_e) if inn_e is not None else None
        result["name"] = None  # ФИО физлица не сохраняется
        return result

    return None if not result else result


# ─────────────────────────────────────────────────────────────────────────────
#  Главная функция
# ─────────────────────────────────────────────────────────────────────────────

def parse_egrn_xml(xml_path: Path | str) -> Optional[dict]:
    """
    Разобрать XML-выписку ЕГРН.
    Возвращает dict той же структуры, что parse_egrn_pdf, или None.
    """
    xml_path = Path(xml_path)
    log.debug("Парсинг XML: %s", xml_path.name)

    if not _is_egrn_xml(xml_path):
        log.warning("Файл не является XML-выпиской ЕГРН: %s", xml_path.name)
        return None

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError as e:
        log.error("Ошибка разбора XML %s: %s", xml_path.name, e)
        return None

    # Определить тип объекта по корневому тегу
    root_tag = _tag(root)
    object_type = XML_ROOT_TO_OBJECT_TYPE.get(root_tag, "unknown")
    if object_type == "unknown":
        # Попытка через атрибут type или вложенные теги
        for known_tag, known_type in XML_ROOT_TO_OBJECT_TYPE.items():
            if known_tag in root_tag:
                object_type = known_type
                break

    # Метаданные выписки
    header: dict[str, Any] = {}
    top_req = _find_recursive(root, "group_top_requisites")
    if top_req is not None:
        header["organ"]          = clean_value(_find_text(top_req, "organ_registr_rights"))
        header["extract_date"]   = parse_date_any(_find_text(top_req, "date_formation") or "")
        header["extract_number"] = _find_text(top_req, "registration_number")
    header["extract_template"] = "full"  # XML всегда полная выписка
    header["source_format"]    = "xml"

    # Общие данные объекта
    obj_data = _parse_common_data(root, object_type)
    obj_data["object_type"]  = object_type
    obj_data["data_source"]  = xml_path.name
    obj_data["source_file"]  = xml_path.name
    obj_data["is_primary"]   = 1

    cad_number = obj_data.get("cad_number")
    if not cad_number:
        log.warning("Кадастровый номер не найден в XML %s", xml_path.name)
        return None

    # Тип-специфичные поля
    if object_type == "land":
        obj_data.update(_parse_land_params(root))
        # Fix 40b: автогенерация name для ЗУ (как в pdf_parser)
        if cad_number and not obj_data.get("name"):
            area = obj_data.get("area")
            area_str = f", {area} кв.м" if area else ""
            obj_data["name"] = f"Земельный участок {cad_number}{area_str}"
    elif object_type == "building":
        obj_data.update(_parse_building_params(root))
    elif object_type in ("room", "parking"):
        obj_data.update(_parse_room_params(root))
    elif object_type in ("structure", "ons"):
        obj_data.update(_parse_structure_params(root))

    # Права и обременения
    rights = _parse_xml_rights(root, cad_number, object_type, header.get("extract_number"))

    # Object restrictions (из special_notes / restrictions_encumbrances XML-блоков)
    object_restrictions = _parse_xml_object_restrictions(root, header.get("extract_number"))
    obj_data["object_restrictions"] = (
        json.dumps(object_restrictions, ensure_ascii=False) if object_restrictions else None
    )

    # Content hash
    content_hash = _compute_content_hash_xml(obj_data, rights, object_restrictions)
    obj_data["content_hash"] = content_hash

    result = filter_personal_data({
        "header":              header,
        "object":              obj_data,
        "rights":              rights,
        "object_restrictions": object_restrictions,
        "cad_number":          cad_number,
        "object_type":         object_type,
        "source_filename":     xml_path.name,
    })

    log.info(
        "✓ Разобрана XML-выписка %s: %s (%s), прав: %d",
        header.get("extract_number", "?"),
        cad_number,
        object_type,
        len(rights),
    )
    return result


def _parse_xml_object_restrictions(root: ET.Element, extract_number: Optional[str]) -> list[dict]:
    """Извлечь ограничения объекта из XML (Fix 27).
    
    Источники:
    - <restrictions_encumbrances><restriction_encumbrance> (ст. 56 ЗК)
    - <special_notes> (Особые отметки)
    - <zones_and_boundaries> (ЗОУИТ)
    """
    restrictions: list[dict] = []
    seen_reg_nums: set = set()

    # Источник 1: <restriction_encumbrance> (основной для ЗУ)
    for enc in _find_all_recursive(root, "restriction_encumbrance"):
        # Реестровый номер границы
        reg_num_e = _find_recursive(enc, "number") or _find_recursive(enc, "reg_number_border")
        reg_num = _text(_find(reg_num_e, "number") if reg_num_e is not None else None)
        if not reg_num:
            reg_num = _text(reg_num_e)

        # Описание
        content_e = _find_recursive(enc, "content_restrict_encumbrances")
        enc_type_e = _find_recursive(enc, "encumbrance_type")
        enc_val_e  = _find(enc_type_e, "value") if enc_type_e is not None else None
        type_name  = _text(enc_val_e) if enc_val_e is not None else ""
        desc       = _text(content_e)[:200] if content_e is not None else type_name

        # Дедупликация
        key = reg_num or desc[:50]
        if key in seen_reg_nums:
            continue
        seen_reg_nums.add(key)

        # Классификация (единый алгоритм с PDF)
        restr_type = classify_restriction_type(type_name, desc)

        # Документ-основание
        doc_elem = _find_recursive(enc, "underlying_document")
        basis_doc = {}
        if doc_elem is not None:
            basis_doc = {
                "type":   _text(_find_recursive(doc_elem, "value")),
                "number": _text(_find_recursive(doc_elem, "document_number")),
                "date":   parse_date_any(_text(_find_recursive(doc_elem, "document_date")) or ""),
            }

        restrictions.append({
            "type":            restr_type,
            "description":     clean_value(desc),
            "registry_number": reg_num or None,
            "basis_doc":       basis_doc or None,
            "source_extract":  extract_number,
        })

    # Источник 2: <special_notes> (Особые отметки — plain text)
    sn = _find_recursive(root, "special_notes")
    if sn is not None and _text(sn) and not is_absent(_text(sn)):
        sn_text = _text(sn)
        _FP = ("сведения, необходимые", "данные отсутствуют", "план расположения")
        if not any(fp in sn_text.lower() for fp in _FP):
            restrictions.append({
                "type":           "other",
                "description":    sn_text[:300],
                "registry_number":None,
                "basis_doc":      None,
                "source_extract": extract_number,
            })

    return restrictions


def _compute_content_hash_xml(obj_data: dict, rights: list, restrictions: list) -> str:
    """SHA-256 для XML-выписки."""
    payload = json.dumps(
        {
            "cad_number":          obj_data.get("cad_number"),
            "area":                obj_data.get("area"),
            "cadastral_value":     obj_data.get("cadastral_value"),
            "address":             obj_data.get("address"),
            "object_restrictions": restrictions,
            "rights_count":        len(rights),
        },
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
