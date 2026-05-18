import json
import re
import sys
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Any


CN_RE = re.compile(r"\b\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?\b")
CN_STRICT_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?$")
COND_NUM_RE = re.compile(r"\d{2}-\d{2}-\d{2}/\d{1,4}/\d{4}-\d{1,5}")
AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:кв\.?\s*м|м²|кв\.\s*м\.?)")
OGRN_RE = re.compile(r"\b\d{13}\b")
OGRNIP_RE = re.compile(r"\b\d{15}\b")
INN_LEGAL_RE = re.compile(r"\b\d{10}\b")
INN_PERSON_RE = re.compile(r"\b\d{12}\b")
COORD_PAIR_RE = re.compile(r"\[\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\]")
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}

FIO_PATTERNS = (
    re.compile(r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b"),
    re.compile(r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*\b"),
)
LEGAL_FORM_MARKERS = (
    "общество", "оао", "зао", "ао ", "ао.", "ао,", "ооо", "пао", "тоо", "ип ", "учреждение",
    "компания", "корпорация", "союз", "ассоциация", "фонд", "товарищество",
    "кооператив", "предприятие", "банк", "филиал", "комитет", "министерство",
    "управление", "инспекция", "администрация",
)
MASK_MARKERS = ("🔒", "▒")
PAID_REPORT_MARKERS = ("доступно в отчете", "доступно в отчёте", "оплатите", "paid")
EMPTY_VALUE_MARKERS = ("не найдено", "не указано", "не определено", "", "-", "n/a", "null", "none")

EGRN_OBJECT_CLASS_TO_TYPE = {
    "land": "Земельный участок",
    "building": "Здание",
    "construction": "Сооружение",
    "room": "Помещение",
    "uncompleted": "Объект незавершенного строительства",
}

EGRN_BUILDING_FIELDS = {
    "cad_number": "Кадастровый номер",
    "object_type": "Тип объекта",
    "quarter_cad_number": "Кадастровый квартал",
    "registration_date": "Дата постановки на учёт",
    "old_numbers": "Прежние номера",
    "address": "Адрес",
    "cadastral_value": "Кадастровая стоимость, руб.",
    "cadastral_value_date": "Дата кадастровой стоимости",
    "lifecycle_status_text": "Статус",
    "deregistration_date": "Дата снятия с учёта",
    "permitted_uses": "Виды разрешённого использования",
    "area": "Площадь, кв.м",
    "name": "Наименование",
    "purpose": "Назначение",
    "floors_total": "Количество этажей всего",
    "floors_above_ground": "Этажей надземных",
    "underground_floors": "Этажей подземных",
    "wall_material": "Материал стен",
    "year_used": "Год ввода в эксплуатацию",
    "year_built": "Год завершения строительства",
    "land_cad_numbers": "Кадастровые номера земельных участков",
    "room_type": "Тип помещения",
    "floor": "Этаж",
    "parent_cad_number": "Родительский кадастровый номер",
    "predecessor_cad_numbers": "Предшествующие кадастровые номера",
    "successor_cad_numbers": "Последующие кадастровые номера",
}

EGRN_RIGHT_FIELDS = {
    "right_type": "Вид права",
    "right_number": "Номер регистрации",
    "right_date": "Дата регистрации",
    "right_end_date": "Дата прекращения",
    "right_end_reason": "Основание прекращения",
    "basis": "Документ-основание",
    "share_numerator": "Доля (числитель)",
    "share_denominator": "Доля (знаменатель)",
    "valid_from": "Действует с",
    "valid_until": "Действует по",
    "valid_duration_years": "Срок (лет)",
    "lease_term_description": "Срок аренды",
}

KADBASE_FIELD_ALIASES = {
    "Тип объекта (детально)": "Подтип объекта",
    "Тип_детальный": "Подтип объекта",
    "Тип": "Тип записи",
    "Назначение помещения": "Назначение",
    "Номер этажа": "Этаж",
    "Номер/тип этажа": "Этаж",
    "Тип этажа": "Тип этажа",
    "Площадь, кв. м": "Площадь, кв.м",
    "Площадь": "Площадь, кв.м",
    "Кадастровая стоимость, руб.": "Кадастровая стоимость, руб.",
    "Кадастровая стоимость": "Кадастровая стоимость, руб.",
    "Удельный показатель кадастровой стоимости, руб./кв. м": "Удельный показатель кадастровой стоимости, руб./кв.м",
    "Удельный показатель кадастровой стоимости": "Удельный показатель кадастровой стоимости, руб./кв.м",
    "Кадастровая стоимость (КС)": "Кадастровая стоимость, руб.",
    "Дата постановки на кадастровый учет": "Дата постановки на учёт",
    "На учете с": "Дата постановки на учёт",
    "Статус объекта": "Статус",
    "Дата обновления информации": "Дата обновления",
    "Дата обновления информации\nпо объекту в": "Дата обновления",
    "Координаты центра": "Координаты центра",
    "Округ": "Регион (код)",
    "Район": "Район (код)",
    "Квартал (ОКС)": "Кадастровый квартал",
    "Квартал (Земельные участки)": "Кадастровый квартал ЗУ",
    "Ранее присвоенные номера": "Прежние номера",
    "Инвентарный номер": "Инвентарный номер",
    "Вид жилого помещения": "Вид жилого помещения",
}

KADBASE_TYPE_MAP = {
    "помещение": "Помещение",
    "квартира": "Помещение",
    "комната": "Помещение",
    "здание": "Здание",
    "сооружение": "Сооружение",
    "земельный участок": "Земельный участок",
    "объект капитального строительства": "Помещение",
    "оке": "Помещение",
    "окс": "Помещение",
}

CATEGORY_FOR_TYPE = {
    "Земельный участок": "Земельные участки",
    "Единое землепользование": "Земельные участки",
    "Здание": "Здания",
    "Сооружение": "Сооружения",
    "Помещение": "Помещения",
    "Объект незавершенного строительства": "Объекты незавершенного строительства",
}

SOURCE_PRIORITY = {"egrn": 4, "nspd": 3, "kadbase": 2, "kml": 2, "certificate": 1, "legal_entity": 3}

RIGHT_TYPE_NORMALIZATION = {
    "собственность": "ownership",
    "общая долевая собственность": "ownership_shared",
    "общая совместная собственность": "ownership_joint",
    "хозяйственное ведение": "economic_management",
    "оперативное управление": "operational_management",
    "аренда": "lease",
    "субаренда": "sublease",
    "ипотека": "mortgage",
    "залог": "pledge",
    "сервитут": "servitude",
    "безвозмездное пользование": "free_use",
    "доверительное управление": "trust_management",
    "прочие ограничения прав и обременения объекта недвижимости": "other_encumbrance",
    "объект культурного наследия": "cultural_heritage",
    "арест": "arrest",
    "запрет": "prohibition",
}

STATUS_DEREGISTERED_MARKERS = ("снят с учет", "снято с учет", "снята с учет", "погашен")


def is_masked_value(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    if not s:
        return True
    if any(m in str(v) for m in MASK_MARKERS):
        return True
    if any(m in s for m in PAID_REPORT_MARKERS):
        return True
    if s in EMPTY_VALUE_MARKERS:
        return True
    return False


def is_deregistered(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).lower()
    return any(m in s for m in STATUS_DEREGISTERED_MARKERS)


def normalize_right_type(text: str) -> str:
    if not text:
        return ""
    s = text.strip().lower()
    for key, code in RIGHT_TYPE_NORMALIZATION.items():
        if key in s:
            return code
    return s


def normalize_right_number(num: str) -> str:
    if not num:
        return ""
    return re.sub(r"\s+", "", str(num)).lower()


def normalize_address(addr: str) -> str:
    if not addr:
        return ""
    s = addr.lower()
    s = re.sub(r"[ё]", "е", s)
    s = re.sub(r"\d{6,}\s*,?\s*", "", s)
    s = re.sub(r"\bроссия\b|\bроссийская\s+федерация\b", "", s)
    s = re.sub(r"\bобласть\b|\bобл\.?", "обл", s)
    s = re.sub(r"\bгород\b|\bг\.?", "г", s)
    s = re.sub(r"\bулица\b|\bул\.?", "ул", s)
    s = re.sub(r"\bдом\b|\bд\.?", "д", s)
    s = re.sub(r"\bрайон\b|\bр-н\.?", "р-н", s)
    s = re.sub(r"[№\"',.()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def address_tokens(addr: str) -> set:
    norm = normalize_address(addr)
    stop = {"обл", "г", "д", "р-н", "ростовская", "ростов-на-дону",
            "москва", "россия", "край", "республика", "автономный",
            "район", "ленинский", "кировский", "октябрьский", "первомайский",
            "пролетарский", "советский"}
    return set(t for t in norm.split() if len(t) >= 2 and t not in stop)


def extract_street_signature(addr: str) -> tuple[str, str]:
    if not addr:
        return "", ""
    s = normalize_address(addr)
    street = ""
    m = re.search(r"\bул\s+([а-яёa-z0-9\-/]+)", s)
    if m:
        street = m.group(1)
    if not street:
        for pat in (r"\bпр(?:осп)?\s+([а-яёa-z0-9\-/]+)", r"\bпер\s+([а-яёa-z0-9\-/]+)",
                    r"\bб(?:ульв)?\s+([а-яёa-z0-9\-/]+)", r"\bнаб(?:ережная)?\s+([а-яёa-z0-9\-/]+)",
                    r"\bш(?:оссе)?\s+([а-яёa-z0-9\-/]+)"):
            m = re.search(pat, s)
            if m:
                street = m.group(1)
                break
    house = ""
    m = re.search(r"\bд\s+([0-9]+(?:[/\-][0-9а-яёa-z]+)*)", s)
    if m:
        house = m.group(1)
    return street, house


def address_match_score(addr_a: str, addr_b: str) -> tuple[float, str]:
    if not addr_a or not addr_b:
        return 0.0, ""
    street_a, house_a = extract_street_signature(addr_a)
    street_b, house_b = extract_street_signature(addr_b)
    if not (street_a and street_b):
        return 0.0, ""
    if street_a != street_b:
        if not (street_a.startswith(street_b) or street_b.startswith(street_a) or
                (len(street_a) >= 4 and len(street_b) >= 4 and
                 (street_a in street_b or street_b in street_a))):
            return 0.0, ""
    if house_a and house_b:
        norm_a = house_a.split("/")[0]
        norm_b = house_b.split("/")[0]
        if norm_a != norm_b:
            return 0.0, ""
    a_tok = address_tokens(addr_a)
    b_tok = address_tokens(addr_b)
    if not a_tok or not b_tok:
        return 0.5, f"{street_a} д.{house_a or '?'}"
    overlap = len(a_tok & b_tok) / max(len(a_tok), len(b_tok))
    base = max(0.7, overlap)
    return base, f"{street_a} д.{house_a or '?'}"


def extract_area(text: str) -> float | None:
    if text is None or is_masked_value(text):
        return None
    m = AREA_RE.search(str(text).replace("\u00a0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_numeric_value(text: str) -> float | None:
    if text is None or is_masked_value(text):
        return None
    s = str(text).replace("\u00a0", " ").strip()
    m = re.match(r"^([\d\s]+(?:[.,]\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def stable_hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def looks_like_legal_entity(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if any(m in t for m in LEGAL_FORM_MARKERS):
        return True
    if OGRN_RE.search(text) or OGRNIP_RE.search(text):
        return True
    return False


def looks_like_paid_placeholder(text: str) -> bool:
    if not text:
        return False
    s = text.lower()
    return any(m in s for m in PAID_REPORT_MARKERS)


def extract_entity_keys(text: str) -> dict:
    if not text:
        return {}
    keys = {}
    m_ogrnip = OGRNIP_RE.search(text)
    if m_ogrnip:
        keys["ogrn"] = m_ogrnip.group(0)
    m_ogrn = OGRN_RE.search(text)
    if m_ogrn and "ogrn" not in keys:
        keys["ogrn"] = m_ogrn.group(0)
    m_inn_legal = INN_LEGAL_RE.search(text)
    if m_inn_legal:
        keys["inn"] = m_inn_legal.group(0)
    m_inn_person = INN_PERSON_RE.search(text)
    if m_inn_person and "inn" not in keys:
        keys["inn_person"] = m_inn_person.group(0)
    return keys


def right_dedup_key(type_code: str | None, type_text: str, right_number: str | None) -> str:
    code = (type_code or "").lower() or normalize_right_type(type_text)
    num = normalize_right_number(right_number or "")
    if num:
        return stable_hash(code or "unknown", num)
    return stable_hash(code or "unknown", "no_number", type_text or "")


def beneficiary_key_from_legal(ogrn: str | None, inn: str | None, name: str | None) -> str:
    if ogrn:
        return f"legal::ogrn::{ogrn}"
    if inn:
        return f"legal::inn::{inn}"
    if name:
        return f"legal::name::{stable_hash(name.lower().strip())}"
    return f"unknown::{stable_hash('?')}"


def parse_polygon_string(s: str) -> list[list[float]] | None:
    if not s:
        return None
    pairs = COORD_PAIR_RE.findall(s)
    if len(pairs) < 3:
        return None
    coords = []
    for lon, lat in pairs:
        try:
            coords.append([float(lon), float(lat)])
        except ValueError:
            continue
    if len(coords) < 3:
        return None
    return coords


def parse_kml_coordinates(text: str) -> list[list[float]]:
    if not text:
        return []
    result = []
    for tok in text.replace("\n", " ").split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                result.append([lon, lat])
            except ValueError:
                continue
    return result


def normalize_polygon(coords: list[list[float]], target_points: int = 24) -> dict | None:
    if not coords or len(coords) < 3:
        return None
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    cen_lon = (min_lon + max_lon) / 2
    cen_lat = (min_lat + max_lat) / 2
    span = max(max_lon - min_lon, max_lat - min_lat) or 1e-6
    normalized = []
    for lon, lat in coords:
        x = (lon - cen_lon) / span
        y = (lat - cen_lat) / span
        normalized.append([round(x, 4), round(y, 4)])
    if len(normalized) > target_points:
        step = len(normalized) / target_points
        sampled = [normalized[int(i * step)] for i in range(target_points)]
        normalized = sampled
    if normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return {
        "points_normalized": normalized,
        "center": [round(cen_lon, 6), round(cen_lat, 6)],
        "bbox": [round(min_lon, 6), round(min_lat, 6), round(max_lon, 6), round(max_lat, 6)],
        "points_count": len(coords),
    }


def detect_file_kind(data: Any, path: Path) -> str:
    if path.suffix.lower() == ".kml":
        return "kml"
    if not isinstance(data, dict):
        return "unknown"
    if "tables" in data and isinstance(data.get("tables"), dict):
        return "egrn"
    if "data" in data and isinstance(data.get("data"), dict):
        return "nspd"
    if "entity" in data and isinstance(data.get("entity"), dict) and data.get("query"):
        return "legal_entity"
    if "payload" in data and isinstance(data.get("payload"), dict):
        p = data["payload"]
        if "Кадастровый номер" in p or "Кадастровый номер_детальный" in p:
            return "kadbase"
    if "Условный номер" in data or "Правоподтверждающий документ" in data or "Объект права" in data:
        return "certificate"
    return "unknown"


def maybe_extract_geometry(attrs: dict) -> dict | None:
    geom_raw = None
    for key in list(attrs.keys()):
        if key.lower() in ("контур объекта", "контур", "polygon"):
            geom_raw = attrs.pop(key)
            break
    if not geom_raw:
        return None
    coords = parse_polygon_string(str(geom_raw))
    if not coords:
        return None
    return normalize_polygon(coords)


def parse_nspd(data: dict, source_id: str) -> tuple[dict, list, list]:
    objects = {}
    rights: list = []
    encumbrances = []
    root = data.get("data", {})
    for category, items in root.items():
        if not isinstance(items, dict):
            continue
        for cn, attrs in items.items():
            if not isinstance(attrs, dict):
                continue
            obj_type = attrs.get("Вид объекта недвижимости")
            if not obj_type and category in CATEGORY_FOR_TYPE.values():
                inv = {v: k for k, v in CATEGORY_FOR_TYPE.items()}
                obj_type = inv.get(category, "Неизвестно")
            attrs_clean = {k: v for k, v in attrs.items() if k != "Связанные объекты"}
            geom = maybe_extract_geometry(attrs_clean)
            obj_rec = {
                "Кадастровый номер": cn,
                "Вид объекта недвижимости": obj_type or "Неизвестно",
                "_attrs_raw": attrs_clean,
                "_related_raw": attrs.get("Связанные объекты") or {},
                "_sources_for_attrs": [source_id],
            }
            if geom:
                obj_rec["_geometry"] = geom
            objects[cn] = obj_rec
            cultural = attrs.get(
                "Сведения о включении объекта недвижимости в единый государственный реестр объектов "
                "культурного наследия (памятников истории и культуры) народов Российской Федерации"
            )
            if cultural and str(cultural).strip() not in ("-", ""):
                encumbrances.append({
                    "_object_cn": cn,
                    "_object_key_alt": None,
                    "_beneficiary_text": "",
                    "Вид обременения": "Объект культурного наследия",
                    "Описание": str(cultural).strip(),
                    "_source_id": source_id,
                    "_dedup_key": right_dedup_key("cultural_heritage", "Объект культурного наследия", str(cultural).strip()[:50]),
                })
    return objects, rights, encumbrances


def parse_egrn(data: dict, source_id: str) -> tuple[dict, list, list]:
    tables = data.get("tables", {})
    objects = {}
    extracts_by_num = {e.get("extract_number"): e for e in tables.get("extracts", []) or []}

    for table_name in ("building_objects", "land_objects"):
        for b in tables.get(table_name, []) or []:
            cn = b.get("cad_number")
            if not cn:
                continue
            object_class = b.get("object_type") or ""
            obj_type = EGRN_OBJECT_CLASS_TO_TYPE.get(object_class, "Неизвестно")
            attrs = {}
            for k, ru in EGRN_BUILDING_FIELDS.items():
                v = b.get(k)
                if v is None or v == "":
                    continue
                if k == "object_type":
                    attrs[ru] = obj_type
                    continue
                attrs[ru] = v
            objects[cn] = {
                "Кадастровый номер": cn,
                "Вид объекта недвижимости": obj_type,
                "_attrs_raw": attrs,
                "_related_raw": {},
                "_sources_for_attrs": [source_id],
                "_egrn_old_numbers": b.get("old_numbers") or "",
            }

    rights = []
    encumbrances = []
    for r in tables.get("rights", []) or []:
        kind = (r.get("right_category") or "").lower()
        key_value = r.get("object_key_value")
        record = {}
        for k, ru in EGRN_RIGHT_FIELDS.items():
            v = r.get(k)
            if v is None or v == "":
                continue
            record[ru] = v
        beneficiary_text = (r.get("beneficiary_name") or "").strip()
        src_num = r.get("source_extract_number")
        if src_num and src_num in extracts_by_num:
            ex = extracts_by_num[src_num]
            record["Реквизиты выписки"] = {
                "Номер выписки": src_num,
                "Дата выписки": ex.get("extract_date"),
                "Орган": ex.get("organ"),
                "Файл": ex.get("source_filename"),
            }
        dedup = right_dedup_key(r.get("right_type_code"), r.get("right_type") or "", r.get("right_number"))
        entry = {
            "_object_cn": key_value,
            "_object_key_alt": None,
            "_source_id": source_id,
            "_dedup_key": dedup,
            "_beneficiary_text": beneficiary_text,
            **record,
        }
        if kind == "right":
            rights.append(entry)
        else:
            if "Вид права" in entry:
                entry["Вид обременения"] = entry.pop("Вид права")
            encumbrances.append(entry)
    return objects, rights, encumbrances


def parse_kadbase(data: dict, source_id: str, file_name: str) -> tuple[dict, list, list]:
    payload = data.get("payload") or {}
    rights: list = []
    encumbrances: list = []

    cn = (payload.get("Кадастровый номер") or "").strip()
    if not CN_STRICT_RE.match(cn or ""):
        return {}, [], []

    obj_type_text = (
        payload.get("Вид объекта недвижимости")
        or payload.get("Тип объекта (детально)")
        or payload.get("Тип_детальный")
        or payload.get("Тип объекта")
        or payload.get("Тип")
        or ""
    ).strip().lower()
    obj_type = None
    for key, mapped in KADBASE_TYPE_MAP.items():
        if key in obj_type_text:
            obj_type = mapped
            break
    if not obj_type:
        if cn.count(":") >= 4 or re.search(r":\d{3,}$", cn):
            obj_type = "Помещение"
        else:
            obj_type = "Неизвестно"

    attrs: dict = {}
    related: dict = {}
    geometry = None

    for k, v in payload.items():
        if k == "Кадастровый номер":
            continue
        if v is None:
            continue
        target_key = KADBASE_FIELD_ALIASES.get(k, k)

        if k.lower() in ("контур объекта", "контур", "polygon"):
            coords = parse_polygon_string(str(v))
            if coords:
                geometry = normalize_polygon(coords)
            continue

        if k == "Кадастровый номер здания, сооружения, в котором расположено помещение":
            if isinstance(v, str) and CN_STRICT_RE.match(v.strip()):
                related.setdefault("Кадастровый номер здания, сооружения, в котором расположено помещение", []).append(v.strip())
            continue

        if k == "Является частью ОКС":
            text = str(v)
            first_line = text.split("\n", 1)[0].strip()
            if CN_STRICT_RE.match(first_line):
                related.setdefault("Является частью ОКС", []).append(first_line)
            sanitized = re.sub(r"[🔒▒]+", "[скрыто]", text)
            attrs["Описание родительского ОКС"] = sanitized
            continue

        if isinstance(v, str) and is_masked_value(v):
            continue

        if target_key in ("Кадастровая стоимость, руб.", "Удельный показатель кадастровой стоимости, руб./кв.м"):
            num = parse_numeric_value(v)
            if num is not None:
                attrs[target_key] = num
                continue

        if target_key == "Площадь, кв.м":
            num = extract_area(str(v)) if isinstance(v, str) else None
            if num is None:
                num = parse_numeric_value(v)
            if num is not None:
                attrs[target_key] = num
                continue

        if k == "Связи с другими объектами":
            attrs[target_key] = re.sub(r"\s*🔗\s*", "", str(v)).strip()
            continue

        if k == "Собственник":
            if looks_like_paid_placeholder(str(v)):
                continue
            attrs["Собственник (текст)"] = str(v)
            continue

        if k == "Форма собственности":
            attrs[target_key] = str(v).strip()
            continue

        if isinstance(v, str):
            attrs[target_key] = v.strip()
        else:
            attrs[target_key] = v

    if "Источник (URL)" not in attrs and data.get("source"):
        attrs["Источник (URL)"] = data["source"]

    object_record = {
        "Кадастровый номер": cn,
        "Вид объекта недвижимости": obj_type,
        "_attrs_raw": attrs,
        "_related_raw": related,
        "_sources_for_attrs": [source_id],
    }
    if geometry:
        object_record["_geometry"] = geometry
    return {cn: object_record}, rights, encumbrances


def parse_kml(path: Path, source_id: str) -> tuple[dict, list, list]:
    objects: dict = {}
    try:
        tree = ET.parse(str(path))
    except ET.ParseError:
        return {}, [], []
    root = tree.getroot()
    ns_match = re.match(r"\{(.+)\}", root.tag)
    ns = {"k": ns_match.group(1)} if ns_match else {}
    prefix = "k:" if ns else ""

    for pm in root.iter(f"{{{ns['k']}}}Placemark" if ns else "Placemark"):
        name_el = pm.find(f"{prefix}name", ns) if ns else pm.find("name")
        desc_el = pm.find(f"{prefix}description", ns) if ns else pm.find("description")
        name_text = (name_el.text or "").strip() if name_el is not None and name_el.text else ""
        desc_text = (desc_el.text or "").strip() if desc_el is not None and desc_el.text else ""

        combined = f"{name_text}\n{desc_text}"
        cn_match = CN_RE.search(combined)
        if not cn_match:
            continue
        cn = cn_match.group(0)

        obj_type = "Неизвестно"
        low = combined.lower()
        for key, mapped in KADBASE_TYPE_MAP.items():
            if key in low:
                obj_type = mapped
                break
        if obj_type == "Неизвестно":
            if cn.count(":") >= 4:
                obj_type = "Помещение"

        attrs: dict = {"Наименование": name_text, "Описание (KML)": desc_text}
        area = extract_area(combined)
        if area is not None:
            attrs["Площадь, кв.м"] = area
        addr_match = re.search(r"под\s+(.+?)\s+\d{1,2}:\d", combined)
        if addr_match:
            attrs["Адрес (из KML)"] = addr_match.group(1).strip()
        cent_match = re.search(r"Центр:\s*([\d\.\-]+)\s*,\s*([\d\.\-]+)", combined)
        if cent_match:
            try:
                lat = float(cent_match.group(1))
                lon = float(cent_match.group(2))
                attrs["Координаты центра"] = f"{lon},{lat}"
            except ValueError:
                pass

        polygon_coords: list[list[float]] = []
        for poly in (pm.iter(f"{{{ns['k']}}}Polygon") if ns else pm.iter("Polygon")):
            coord_el = poly.find(f".//{prefix}coordinates", ns) if ns else poly.find(".//coordinates")
            if coord_el is not None and coord_el.text:
                polygon_coords = parse_kml_coordinates(coord_el.text)
                if polygon_coords:
                    break

        point_coord: list[float] | None = None
        for point in (pm.iter(f"{{{ns['k']}}}Point") if ns else pm.iter("Point")):
            coord_el = point.find(f"{prefix}coordinates", ns) if ns else point.find("coordinates")
            if coord_el is not None and coord_el.text:
                pts = parse_kml_coordinates(coord_el.text)
                if pts:
                    point_coord = pts[0]
                    break

        record = {
            "Кадастровый номер": cn,
            "Вид объекта недвижимости": obj_type,
            "_attrs_raw": attrs,
            "_related_raw": {},
            "_sources_for_attrs": [source_id],
        }
        if polygon_coords:
            geom = normalize_polygon(polygon_coords)
            if geom:
                record["_geometry"] = geom
        if point_coord and "Координаты центра" not in attrs:
            attrs["Координаты центра"] = f"{point_coord[0]},{point_coord[1]}"

        if cn in objects:
            existing = objects[cn]
            for k, v in attrs.items():
                if k not in existing["_attrs_raw"]:
                    existing["_attrs_raw"][k] = v
            if "_geometry" in record and "_geometry" not in existing:
                existing["_geometry"] = record["_geometry"]
        else:
            objects[cn] = record

    return objects, [], []


def parse_certificate(data: dict, source_id: str, file_name: str) -> tuple[dict, list, list]:
    objects = {}
    rights = []
    encumbrances: list = []

    cn = (data.get("Кадастровый номер") or "").strip()
    if cn in ("Не найдено", "-", ""):
        cn = None
    if cn and not CN_STRICT_RE.match(cn):
        cn = None

    cond_num = (data.get("Условный номер") or "").strip() or None
    address = data.get("Адрес") or ""
    obj_descr = data.get("Объект права") or ""
    area = extract_area(obj_descr)

    obj_type = "Неизвестно"
    low = obj_descr.lower()
    if "нежилое помещение" in low or "помещение" in low:
        obj_type = "Помещение"
    elif "земельный участок" in low:
        obj_type = "Земельный участок"
    elif "здание" in low or "дом" in low:
        obj_type = "Здание"
    elif "сооружение" in low:
        obj_type = "Сооружение"

    attrs = {"Адрес": address, "Условный номер": cond_num, "Объект права": obj_descr}
    if area is not None:
        attrs["Площадь, кв.м"] = area

    matchable = {
        "Условный номер": cond_num,
        "Адрес (нормализованный)": normalize_address(address),
        "Площадь, кв.м": area,
        "Кадастровый номер": cn,
        "_source_file": file_name,
    }

    placeholder_id = cn or f"cert::{stable_hash(cond_num or '', normalize_address(address), str(area or ''), file_name)}"

    objects[placeholder_id] = {
        "Кадастровый номер": cn,
        "Вид объекта недвижимости": obj_type,
        "_attrs_raw": {k: v for k, v in attrs.items() if v not in (None, "")},
        "_related_raw": {},
        "_sources_for_attrs": [source_id],
        "_certificate_match_keys": matchable,
        "_is_certificate_placeholder": True,
    }

    right_kind = data.get("Вид права") or "Собственность"
    holder = data.get("Субъект права") or ""
    basis = data.get("Документы-основания") or ""
    issue_date = data.get("Дата выдачи") or ""
    issuer = data.get("Выдавший орган") or ""
    doc_type = data.get("Правоподтверждающий документ") or ""

    right_record = {
        "Вид права": right_kind.capitalize() if right_kind else "Собственность",
        "Номер регистрации": cond_num,
        "Документ-основание": basis,
        "Реквизиты свидетельства": {
            "Дата выдачи": issue_date,
            "Выдавший орган": issuer,
            "Тип документа": doc_type,
        },
    }
    right_record = {k: v for k, v in right_record.items() if v not in (None, "")}

    dedup = right_dedup_key(None, right_kind, cond_num)
    rights.append({
        "_object_cn": cn,
        "_object_key_alt": placeholder_id if not cn else None,
        "_cert_match_keys": matchable,
        "_source_id": source_id,
        "_dedup_key": dedup,
        "_beneficiary_text": holder,
        **right_record,
    })
    return objects, rights, encumbrances


def parse_legal_entity(data: dict, source_id: str) -> tuple[dict, list]:
    entity = data.get("entity") or {}
    if not entity:
        return {}, []

    ogrn = entity.get("ogrn")
    inn = entity.get("inn")
    kpp = entity.get("kpp")
    name_full = entity.get("name_full") or entity.get("name_short") or ""

    directors = []
    for d in entity.get("directors", []) or []:
        directors.append({"Должность": d.get("position") or "", "ФИО / тип": "физическое лицо"})

    raw = data.get("raw_data") or {}

    okved_main = entity.get("okved_main") or {}
    okved_main_disp = (f"{okved_main.get('code')} — {okved_main.get('name')}" if okved_main else None)
    okved_additional_disp = [
        f"{o.get('code')} — {o.get('name')}" for o in entity.get("okved_additional", []) or []
    ]

    licences = []
    for lic in raw.get("Лиценз", []) or []:
        licences.append({
            "Номер": lic.get("Номер"),
            "Дата выдачи": lic.get("Дата"),
            "Дата начала": lic.get("ДатаНач"),
            "Орган": lic.get("ЛицОрг"),
            "Виды деятельности": lic.get("ВидДеят"),
        })

    founders_legal = []
    founders_links: list[dict] = []

    for fr in (raw.get("Учред", {}) or {}).get("РосОрг", []) or []:
        rec = {
            "Тип": "Российская организация",
            "ОГРН": fr.get("ОГРН"),
            "ИНН": fr.get("ИНН"),
            "Наименование": fr.get("НаимПолн"),
            "Доля, %": (fr.get("Доля") or {}).get("Процент"),
        }
        founders_legal.append(rec)
        founders_links.append({
            "kind": "legal",
            "ogrn": fr.get("ОГРН"),
            "inn": fr.get("ИНН"),
            "name": fr.get("НаимПолн"),
            "share_percent": (fr.get("Доля") or {}).get("Процент"),
        })

    for fr in (raw.get("Учред", {}) or {}).get("РФ", []) or []:
        org_list = []
        for org in fr.get("ОргОсущПрав", []) or []:
            org_list.append({
                "ОГРН": org.get("ОГРН"),
                "ИНН": org.get("ИНН"),
                "Наименование": org.get("НаимПолн"),
            })
            founders_links.append({
                "kind": "rf_org",
                "ogrn": org.get("ОГРН"),
                "inn": org.get("ИНН"),
                "name": org.get("НаимПолн"),
                "share_percent": (fr.get("Доля") or {}).get("Процент"),
                "context": "Орган, осуществляющий права от имени РФ",
            })
        founders_legal.append({
            "Тип": "Российская Федерация",
            "Регион": (fr.get("Регион") or {}).get("Наим"),
            "Доля, %": (fr.get("Доля") or {}).get("Процент"),
            "Орган, осуществляющий права": org_list,
        })

    for fr in (raw.get("Учред", {}) or {}).get("ИнОрг", []) or []:
        country = fr.get("Страна")
        if isinstance(country, dict):
            country = country.get("Наим")
        rec = {
            "Тип": "Иностранная организация",
            "Наименование": fr.get("НаимПолн") or fr.get("Наим"),
            "Страна": country,
            "Регистрационный номер": fr.get("РегНомер"),
            "Доля, %": (fr.get("Доля") or {}).get("Процент"),
            "Номинал доли": (fr.get("Доля") or {}).get("Номинал"),
        }
        founders_legal.append(rec)
        founders_links.append({
            "kind": "foreign",
            "name": fr.get("НаимПолн") or fr.get("Наим"),
            "reg_number": fr.get("РегНомер"),
            "country": country,
            "share_percent": (fr.get("Доля") or {}).get("Процент"),
        })

    founders_persons_count = len((raw.get("Учред", {}) or {}).get("ФЛ", []) or [])
    if founders_persons_count:
        founders_links.append({
            "kind": "person",
            "count": founders_persons_count,
        })

    branches = []
    for br in (raw.get("Подразд", {}) or {}).get("Филиал", []) or []:
        branches.append({
            "Наименование": br.get("НаимПолн") or br.get("Наим"),
            "КПП": br.get("КПП"),
            "Адрес": br.get("Адрес"),
            "Страна": br.get("Страна"),
        })
    representations = []
    for rp in (raw.get("Подразд", {}) or {}).get("Представ", []) or []:
        representations.append({
            "Наименование": rp.get("НаимПолн") or rp.get("Наим"),
            "КПП": rp.get("КПП"),
            "Адрес": rp.get("Адрес"),
        })

    entity_attrs = {
        "Тип субъекта": "Юридическое лицо",
        "ОГРН": ogrn,
        "ИНН": inn,
        "КПП": kpp,
        "Краткое наименование": entity.get("name_short"),
        "Полное наименование": name_full,
        "Статус": entity.get("status"),
        "Действует": entity.get("is_active"),
        "Дата прекращения": entity.get("termination_date"),
        "Регион": entity.get("region"),
        "Юридический адрес": entity.get("address"),
        "Дата регистрации": entity.get("reg_date"),
        "Основной ОКВЭД": okved_main_disp,
        "Дополнительные ОКВЭД": okved_additional_disp or None,
        "Руководители": directors or None,
        "Учредители (юр.лица и публично-правовые)": founders_legal or None,
        "Учредителей — физических лиц": founders_persons_count or None,
        "Филиалы": branches or None,
        "Представительства": representations or None,
        "Телефоны": (entity.get("contacts") or {}).get("phones"),
        "Электронная почта": (entity.get("contacts") or {}).get("emails"),
        "Сайт": (entity.get("contacts") or {}).get("website"),
        "Лицензии": licences or None,
    }
    entity_attrs = {k: v for k, v in entity_attrs.items() if v not in (None, "", [], {})}

    bkey = beneficiary_key_from_legal(ogrn, inn, name_full)
    return {
        bkey: {
            "_kind": "legal",
            "_ogrn": ogrn,
            "_inn": inn,
            "_kpp": kpp,
            "_name": name_full,
            "_addresses": [(entity.get("address") or "", "Юридический адрес", kpp)] +
                          [(br.get("Адрес"), br.get("Наименование"), br.get("КПП"))
                           for br in branches if br.get("Адрес")],
            "_sources": [source_id],
            "_founders_links": founders_links,
            "attrs": entity_attrs,
        }
    }, founders_links


def load_file(path: Path) -> dict:
    if path.suffix.lower() == ".kml":
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def make_source_descriptor(path: Path, kind: str) -> dict:
    return {
        "id": stable_hash(str(path.resolve()), kind),
        "kind": kind,
        "file": path.name,
        "path": str(path.resolve()),
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    }


def ask_choice(prompt: str, allowed: list[str], default: str) -> str:
    suffix = f" [{('/'.join(allowed))}] (по умолчанию {default}): "
    while True:
        try:
            ans = input(prompt + suffix).strip().lower()
        except EOFError:
            return default
        if not ans:
            return default
        if ans in allowed:
            return ans
        print(f"  Допустимые ответы: {', '.join(allowed)}")


def ask_free_text(prompt: str, default: str) -> str:
    full_prompt = f"{prompt} (по умолчанию: {default}): "
    try:
        ans = input(full_prompt).strip()
    except EOFError:
        return default
    return ans or default


class MatchDecisions:
    def __init__(self, path: Path):
        self.path = path
        self.decisions: dict[str, dict] = {}
        if path.exists():
            try:
                self.decisions = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.decisions = {}

    def get(self, key: str) -> dict | None:
        return self.decisions.get(key)

    def set(self, key: str, value: dict):
        self.decisions[key] = value
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.decisions, ensure_ascii=False, indent=2), encoding="utf-8")


def score_certificate_match(cert_keys: dict, candidate_obj: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    cand_attrs = candidate_obj.get("_attrs_raw", {})
    egrn_old = candidate_obj.get("_egrn_old_numbers", "") or ""

    cert_cond = cert_keys.get("Условный номер")
    if cert_cond:
        in_old = cert_cond in egrn_old
        in_attrs = any(cert_cond in str(v) for v in cand_attrs.values())
        if in_old or in_attrs:
            score += 100
            reasons.append(f"Условный номер {cert_cond} найден в данных кандидата")

    cert_area = cert_keys.get("Площадь, кв.м")
    if cert_area is not None:
        cand_area = cand_attrs.get("Площадь, кв.м")
        if cand_area is None:
            for v in cand_attrs.values():
                a = extract_area(str(v))
                if a is not None:
                    cand_area = a
                    break
        if cand_area is not None:
            try:
                if abs(float(cand_area) - float(cert_area)) <= 0.5:
                    score += 30
                    reasons.append(f"Площадь совпадает: {cert_area} ≈ {cand_area}")
            except (TypeError, ValueError):
                pass

    cert_addr = cert_keys.get("Адрес (нормализованный)") or ""
    cand_addr_raw = cand_attrs.get("Адрес") or ""
    cand_addr = normalize_address(cand_addr_raw)
    if cert_addr and cand_addr:
        cert_tokens = set(cert_addr.split())
        cand_tokens = set(cand_addr.split())
        if cert_tokens and cand_tokens:
            overlap = len(cert_tokens & cand_tokens) / max(len(cert_tokens), len(cand_tokens))
            if overlap >= 0.5:
                score += int(20 * overlap)
                reasons.append(f"Адреса похожи (совпадение токенов {overlap:.0%})")

    return score, reasons


def resolve_certificate_matches(cert_objects: dict, all_objects: dict, decisions: MatchDecisions) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for placeholder_id, cert_obj in cert_objects.items():
        if not cert_obj.get("_is_certificate_placeholder"):
            continue
        keys = cert_obj.get("_certificate_match_keys", {})
        decision_key = "cert::" + stable_hash(
            keys.get("Условный номер") or "",
            keys.get("Адрес (нормализованный)") or "",
            str(keys.get("Площадь, кв.м") or ""),
            keys.get("_source_file") or "",
        )
        prev = decisions.get(decision_key)
        if prev is not None:
            if prev.get("decision") == "match":
                target_cn = prev.get("target_cn")
                if target_cn and target_cn in all_objects:
                    mapping[placeholder_id] = target_cn
                    print(f"[i] Свидетельство → {target_cn} (решение из match_decisions.json)")
                    continue
            elif prev.get("decision") == "standalone":
                print("[i] Свидетельство — самостоятельный узел (решение из match_decisions.json)")
                continue
            elif prev.get("decision") == "skip":
                mapping[placeholder_id] = "__SKIP__"
                continue

        candidates = []
        for obj_id, obj in all_objects.items():
            if obj.get("_is_certificate_placeholder"):
                continue
            if not obj.get("Кадастровый номер"):
                continue
            score, reasons = score_certificate_match(keys, obj)
            if score > 0:
                candidates.append((score, obj_id, obj, reasons))
        candidates.sort(key=lambda x: -x[0])

        print("\n" + "=" * 70)
        print(f"Свидетельство из файла: {keys.get('_source_file')}")
        print(f"  Условный номер: {keys.get('Условный номер')}")
        print(f"  Площадь: {keys.get('Площадь, кв.м')} кв.м")
        print(f"  Адрес: {cert_obj['_attrs_raw'].get('Адрес', '')[:80]}")

        if not candidates:
            print("  Похожих объектов не найдено.")
            ans = ask_choice("Что делать со свидетельством?", ["s", "x"], "s")
            decisions.set(decision_key, {
                "decision": "standalone" if ans == "s" else "skip",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "cert_keys": keys,
            })
            if ans == "x":
                mapping[placeholder_id] = "__SKIP__"
            continue

        print("\nКандидаты на сопоставление:")
        max_show = min(5, len(candidates))
        for i, (score, obj_id, obj, reasons) in enumerate(candidates[:max_show], 1):
            print(f"  [{i}] {obj.get('Кадастровый номер')} ({obj.get('Вид объекта недвижимости')}) — баллы {score}")
            for reason in reasons:
                print(f"        • {reason}")
            addr = obj.get("_attrs_raw", {}).get("Адрес", "")
            if addr:
                print(f"        адрес: {addr[:80]}")
        print("  [s] оставить свидетельство самостоятельным объектом-узлом")
        print("  [x] пропустить (не добавлять)")

        allowed = [str(i) for i in range(1, max_show + 1)] + ["s", "x"]
        ans = ask_choice("Выберите вариант", allowed, "1")

        if ans == "s":
            decisions.set(decision_key, {
                "decision": "standalone",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "cert_keys": keys,
            })
        elif ans == "x":
            decisions.set(decision_key, {
                "decision": "skip",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "cert_keys": keys,
            })
            mapping[placeholder_id] = "__SKIP__"
        else:
            idx = int(ans)
            score, obj_id, obj, reasons = candidates[idx - 1]
            target_cn = obj.get("Кадастровый номер")
            mapping[placeholder_id] = target_cn
            decisions.set(decision_key, {
                "decision": "match",
                "target_cn": target_cn,
                "score": score,
                "reasons": reasons,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "cert_keys": keys,
            })
            print(f"  → сопоставлено с {target_cn}")
    return mapping


def merge_attrs(base: dict, incoming: dict, incoming_source_id: str, source_kinds: dict) -> dict:
    base_attrs = base.get("_attrs_raw", {})
    base_sources = base.setdefault("_attrs_sources", {})
    base_variants = base.setdefault("_attrs_variants", {})
    for k, v in incoming.items():
        if v in (None, "", "-"):
            continue
        if k not in base_attrs:
            base_attrs[k] = v
            base_sources[k] = incoming_source_id
            continue
        if base_attrs[k] == v:
            continue
        cur_src = base_sources.get(k)
        cur_priority = SOURCE_PRIORITY.get(source_kinds.get(cur_src, ""), 0)
        new_priority = SOURCE_PRIORITY.get(source_kinds.get(incoming_source_id, ""), 0)
        if new_priority > cur_priority:
            base_variants.setdefault(k, []).append({"значение": base_attrs[k], "источник_id": cur_src})
            base_attrs[k] = v
            base_sources[k] = incoming_source_id
        else:
            base_variants.setdefault(k, []).append({"значение": v, "источник_id": incoming_source_id})
    base["_attrs_raw"] = base_attrs
    return base


def merge_objects(streams: list[tuple[dict, str]], source_kinds: dict) -> dict:
    merged: dict = {}
    for objects, source_id in streams:
        for key, obj in objects.items():
            real_cn = obj.get("Кадастровый номер")
            target_key = real_cn if real_cn else key
            if target_key not in merged:
                clone = dict(obj)
                clone["_sources_for_attrs"] = list(obj.get("_sources_for_attrs", []))
                clone["_attrs_sources"] = {k: source_id for k in obj.get("_attrs_raw", {}).keys()}
                merged[target_key] = clone
                continue
            existing = merged[target_key]
            merge_attrs(existing, obj.get("_attrs_raw", {}), source_id, source_kinds)
            existing.setdefault("_sources_for_attrs", []).append(source_id)
            existing_related = existing.get("_related_raw") or {}
            incoming_related = obj.get("_related_raw") or {}
            for group, value in incoming_related.items():
                if isinstance(value, list):
                    cur = set(existing_related.get(group, []))
                    cur.update(value)
                    existing_related[group] = sorted(cur)
                else:
                    if group not in existing_related:
                        existing_related[group] = value
            existing["_related_raw"] = existing_related
            cur_type = existing.get("Вид объекта недвижимости") or "Неизвестно"
            new_type = obj.get("Вид объекта недвижимости") or "Неизвестно"
            if cur_type == "Неизвестно" and new_type != "Неизвестно":
                existing["Вид объекта недвижимости"] = new_type
            if obj.get("_egrn_old_numbers") and not existing.get("_egrn_old_numbers"):
                existing["_egrn_old_numbers"] = obj["_egrn_old_numbers"]
            if obj.get("_geometry") and not existing.get("_geometry"):
                existing["_geometry"] = obj["_geometry"]
    return merged


# ────────────────────────────────────────────────────────────────────────────
#  Обогащение этажности ОКС по помещениям (v11.1)
# ────────────────────────────────────────────────────────────────────────────
_FLOOR_WORD_TO_N = {
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "четвёрт": 4,
    "пят": 5, "шест": 6, "седьм": 7, "восьм": 8, "девят": 9, "десят": 10,
}


def _parse_floor_text(text: str) -> tuple[int, int]:
    """
    Аккуратно разбирает строку «Этаж» / часть наименования помещения и
    возвращает (max_above, max_below).

    Считает этажом ТОЛЬКО числа, непосредственно прилегающие к слову «эта…»
    (этаж/этаже/этажа/этажей и т.п.), а также словесные обозначения
    («первого этажа» → 1). Игнорирует номера комнат и любые «оторванные»
    числа, чтобы не словить «25-26» из «комнаты №№25, 26».
    """
    if not text or not isinstance(text, str):
        return 0, 0
    s = text.lower()
    above, below = 0, 0

    if re.search(r"\bподвал\w*", s) or re.search(r"\bполуподвал\w*", s):
        below = max(below, 1)
    if re.search(r"\bцоколь\w*", s) or re.search(r"\bцокольн\w*\s*эта", s):
        below = max(below, 1)

    # Число ПЕРЕД «этаж» (включая диапазон 1-3 / 1–3): «3 этаж», «1-3 этажа»
    for m in re.finditer(r"(\d{1,2})\s*(?:[-–]\s*(\d{1,2})\s*)?эта\w*", s):
        for g in m.groups():
            if g:
                try:
                    above = max(above, int(g))
                except ValueError:
                    pass

    # Число ПОСЛЕ «этаж»: «этаж 3», «этажа 4»
    for m in re.finditer(r"эта\w*\s*(?:№\s*)?(\d{1,2})", s):
        try:
            above = max(above, int(m.group(1)))
        except ValueError:
            pass

    # Словесные числительные: «первого этажа», «второй этаж», «четвёртого этажа»
    for word, n in _FLOOR_WORD_TO_N.items():
        if re.search(rf"\b{word}[а-я]*\s+эта", s):
            above = max(above, n)

    if re.search(r"\bантресол\w*", s):
        m = re.search(r"антресол\w*\s+(?:\w+\s+)?(?:эта\w*\s*)?(\d{1,2})", s)
        if m:
            try:
                above = max(above, int(m.group(1)))
            except ValueError:
                pass
        else:
            # «антресоль первого этажа»
            for word, n in _FLOOR_WORD_TO_N.items():
                if re.search(rf"антресол\w*\s+{word}[а-я]*\s+эта", s):
                    above = max(above, n)
                    break

    if re.search(r"\bмансарда\b|\bмансардн\w*\s*эта", s):
        above = max(above, 1)
    if re.search(r"\bчердак\w*", s):
        above = max(above, 1)

    return above, below


def enrich_floors_from_premises(merged_objects: dict) -> int:
    """
    Если у ОКС (Здание/Сооружение/ОНС) нет «Количество этажей» — выводим из
    максимума «Этаж» по помещениям, перечисленным в «Связанные объекты».

    Возвращает количество обогащённых ОКС.
    """
    affected = 0
    OKS = {"Здание", "Сооружение", "Объект незавершенного строительства"}
    for cn, obj in merged_objects.items():
        if obj.get("Вид объекта недвижимости") not in OKS:
            continue
        attrs = obj.get("_attrs_raw", {}) or {}
        # Уже есть нормальная этажность?
        current_above = attrs.get("Количество этажей") or attrs.get("Количество этажей (в том числе подземных)")
        if current_above and str(current_above).strip() not in ("", "-", "—", "0"):
            continue

        related = obj.get("_related_raw", {}) or {}
        premises_cns: list[str] = []
        for group, value in related.items():
            if not isinstance(value, list):
                continue
            gl = group.lower()
            if "помещен" in gl:
                premises_cns.extend(str(x) for x in value)

        if not premises_cns:
            continue

        max_above, max_below = 0, 0
        observed_premises: list[str] = []
        for prem_cn in premises_cns:
            prem = merged_objects.get(prem_cn)
            if not prem:
                continue
            prem_attrs = prem.get("_attrs_raw", {}) or {}
            floor_text = (
                prem_attrs.get("Этаж")
                or prem_attrs.get("Номер этажа")
                or prem_attrs.get("Этажность")
                or prem_attrs.get("Наименование")    # часто содержит «комнаты на 2 этаже»
                or ""
            )
            a, b = _parse_floor_text(str(floor_text))
            if a or b:
                observed_premises.append(prem_cn)
            max_above = max(max_above, a)
            max_below = max(max_below, b)

        if max_above or max_below:
            attrs["Количество этажей"] = str(max_above) if max_above else "0"
            if max_below:
                attrs["Количество подземных этажей"] = str(max_below)
            attrs["_floors_inferred_from_premises"] = True
            attrs["_floors_inferred_sources"] = observed_premises
            obj["_attrs_raw"] = attrs
            affected += 1
    return affected


def resolve_object_cn(record: dict, cert_mapping: dict) -> str | None:
    obj_cn = record.get("_object_cn")
    obj_alt = record.get("_object_key_alt")
    if not obj_cn and obj_alt:
        mapped = cert_mapping.get(obj_alt)
        if mapped == "__SKIP__":
            return None
        if mapped:
            return mapped
        return obj_alt
    return obj_cn


def resolve_beneficiary(raw_text: str, known_legal: dict) -> tuple[str | None, dict | None]:
    if not raw_text:
        return None, None
    if looks_like_paid_placeholder(raw_text):
        return None, None
    keys = extract_entity_keys(raw_text)
    ogrn = keys.get("ogrn")
    inn = keys.get("inn")

    if ogrn:
        b_key = f"legal::ogrn::{ogrn}"
        if b_key in known_legal:
            return b_key, known_legal[b_key]
        return b_key, {
            "_kind": "legal_text", "_ogrn": ogrn, "_inn": inn,
            "_addresses": [], "_sources": [], "_founders_links": [],
            "attrs": {
                "Тип субъекта": "Юридическое лицо",
                "ОГРН": ogrn,
                "ИНН": inn,
                "Источник текста": raw_text.strip()[:300],
            },
        }
    if looks_like_legal_entity(raw_text):
        name_clean = raw_text.strip()
        b_key = f"legal::name::{stable_hash(name_clean.lower())}"
        if b_key in known_legal:
            return b_key, known_legal[b_key]
        return b_key, {
            "_kind": "legal_text", "_ogrn": None, "_inn": inn,
            "_addresses": [], "_sources": [], "_founders_links": [],
            "attrs": {
                "Тип субъекта": "Юридическое лицо",
                "Наименование (из текста)": name_clean[:200],
                "ИНН": inn,
            },
        }

    b_key = f"person::{stable_hash('anon')}"
    return b_key, {
        "_kind": "person",
        "_addresses": [], "_sources": [], "_founders_links": [],
        "attrs": {
            "Тип субъекта": "Физическое лицо",
            "Примечание": "ФИО и ИНН не публикуются в обезличенном выводе",
        },
    }


def merge_rights_or_encumbrances(streams: list[list[dict]], cert_mapping: dict, known_legal: dict) -> tuple[dict, dict]:
    result: dict[tuple, dict] = {}
    beneficiaries: dict = dict(known_legal)
    for items in streams:
        for r in items:
            src = r.get("_source_id")
            dedup = r.get("_dedup_key")
            obj_cn = resolve_object_cn(r, cert_mapping)
            if obj_cn is None:
                continue
            beneficiary_text = r.get("_beneficiary_text") or ""
            b_key, b_payload = resolve_beneficiary(beneficiary_text, known_legal)
            if b_key and b_key not in beneficiaries and b_payload:
                beneficiaries[b_key] = b_payload
            if b_key and src and b_key in beneficiaries:
                if src not in beneficiaries[b_key].get("_sources", []):
                    beneficiaries[b_key].setdefault("_sources", []).append(src)
            key = (obj_cn, dedup)
            if key not in result:
                rec = {k: v for k, v in r.items() if not k.startswith("_")}
                rec["_object_cn"] = obj_cn
                rec["_dedup_key"] = dedup
                rec["_beneficiary_keys"] = [b_key] if b_key else []
                rec["Источники"] = [{"источник_id": src}]
                result[key] = rec
            else:
                existing = result[key]
                src_ids = {s.get("источник_id") for s in existing.get("Источники", [])}
                if src not in src_ids:
                    existing.setdefault("Источники", []).append({"источник_id": src})
                if b_key and b_key not in existing.get("_beneficiary_keys", []):
                    existing.setdefault("_beneficiary_keys", []).append(b_key)
                for k, v in r.items():
                    if k.startswith("_"):
                        continue
                    if k not in existing or existing[k] in (None, "", "-"):
                        existing[k] = v
                    elif existing[k] != v:
                        existing.setdefault("_варианты", {}).setdefault(k, []).append({
                            "значение": v, "источник_id": src,
                        })
    return result, beneficiaries


def detect_business_units(merged_objects: dict, beneficiaries: dict, decisions: MatchDecisions) -> list[dict]:
    units: list[dict] = []
    object_addrs: list[tuple[str, str, str]] = []
    for cn, obj in merged_objects.items():
        if obj.get("_is_certificate_placeholder"):
            continue
        addr = (obj.get("_attrs_raw", {}) or {}).get("Адрес") or ""
        if not addr:
            continue
        obj_type = obj.get("Вид объекта недвижимости") or "Неизвестно"
        object_addrs.append((cn, addr, obj_type))

    type_priority = {
        "Помещение": 0, "Здание": 1, "Сооружение": 1,
        "Объект незавершенного строительства": 1,
        "Земельный участок": 2, "Единое землепользование": 2, "Неизвестно": 3,
    }

    for b_key, b_data in beneficiaries.items():
        if b_data.get("_kind") not in ("legal", "legal_text"):
            continue
        addresses = b_data.get("_addresses") or []
        for addr_text, addr_label, addr_kpp in addresses:
            if not addr_text:
                continue
            best_match = None
            best_score = 0.0
            for cn, obj_addr, obj_type in object_addrs:
                score, _ = address_match_score(addr_text, obj_addr)
                if score >= 0.6:
                    tp_a = type_priority.get(obj_type, 3)
                    if best_match is None:
                        best_match = (cn, obj_addr, obj_type, score)
                        best_score = score
                        continue
                    cur_tp = type_priority.get(best_match[2], 3)
                    if tp_a < cur_tp or (tp_a == cur_tp and score > best_score):
                        best_match = (cn, obj_addr, obj_type, score)
                        best_score = score
            if not best_match:
                continue
            target_cn, target_addr, target_type, sim = best_match
            suggested_name = addr_label or "Подразделение"
            decision_key = "bu::" + stable_hash(b_key, target_cn, addr_label or "", addr_kpp or "")
            prev = decisions.get(decision_key)
            if prev is not None:
                if prev.get("decision") == "create":
                    units.append({
                        "_bu_key": "bu::" + stable_hash(b_key, target_cn, prev.get("name") or suggested_name),
                        "Наименование": prev.get("name") or suggested_name,
                        "КПП": addr_kpp,
                        "Адрес": addr_text,
                        "_beneficiary_key": b_key,
                        "_object_cn": target_cn,
                        "_kind": "business_unit",
                        "Совпадение адреса, %": int(round(prev.get("similarity", sim) * 100)),
                    })
                continue
            print("\n" + "=" * 70)
            print("Обнаружено совпадение адреса бенефициара и объекта недвижимости:")
            print(f"  Бенефициар: {beneficiaries[b_key].get('attrs', {}).get('Краткое наименование') or b_key}")
            print(f"  Подразделение: {addr_label}")
            if addr_kpp:
                print(f"  КПП: {addr_kpp}")
            print(f"  Адрес подразделения: {addr_text}")
            print(f"  Объект {target_cn} ({target_type})")
            print(f"  Адрес объекта: {target_addr}")
            print(f"  Сходство: {int(round(sim * 100))}%")
            ans = ask_choice("Создать бизнес-единицу?", ["y", "n"], "y")
            if ans == "y":
                name = ask_free_text("  Название бизнес-единицы", suggested_name)
                decisions.set(decision_key, {
                    "decision": "create", "name": name, "similarity": sim,
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "beneficiary_key": b_key, "object_cn": target_cn,
                    "kpp": addr_kpp, "address": addr_text,
                })
                units.append({
                    "_bu_key": "bu::" + stable_hash(b_key, target_cn, name),
                    "Наименование": name, "КПП": addr_kpp, "Адрес": addr_text,
                    "_beneficiary_key": b_key, "_object_cn": target_cn,
                    "_kind": "business_unit",
                    "Совпадение адреса, %": int(round(sim * 100)),
                })
            else:
                decisions.set(decision_key, {
                    "decision": "skip",
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "beneficiary_key": b_key, "object_cn": target_cn, "kpp": addr_kpp,
                })
    return units


def build_founder_chains(beneficiaries: dict) -> list[dict]:
    chains: list[dict] = []
    seen = set()

    def find_beneficiary_for_founder(link: dict) -> str | None:
        ogrn = link.get("ogrn")
        inn = link.get("inn")
        name = link.get("name")
        if ogrn:
            return f"legal::ogrn::{ogrn}"
        if inn:
            for k in beneficiaries.keys():
                if k.startswith("legal::") and beneficiaries[k].get("_inn") == inn:
                    return k
        if name:
            for k, v in beneficiaries.items():
                if v.get("_name") == name:
                    return k
        return None

    for b_key, b_data in list(beneficiaries.items()):
        for link in b_data.get("_founders_links", []) or []:
            if link.get("kind") == "person":
                f_key = f"person::founder::{stable_hash(b_key, 'person', str(link.get('count') or '1'))}"
                if f_key not in beneficiaries:
                    beneficiaries[f_key] = {
                        "_kind": "person", "_addresses": [], "_sources": [],
                        "_founders_links": [],
                        "attrs": {
                            "Тип субъекта": "Физическое лицо (учредитель)",
                            "Количество физических лиц-учредителей": link.get("count"),
                            "Примечание": "ФИО и ИНН не публикуются",
                        },
                    }
                child_key = f_key
            else:
                child_key = find_beneficiary_for_founder(link)
                if not child_key:
                    ogrn = link.get("ogrn")
                    inn = link.get("inn")
                    name = link.get("name")
                    if ogrn:
                        child_key = f"legal::ogrn::{ogrn}"
                    elif name:
                        child_key = f"legal::name::{stable_hash(name.lower())}"
                    elif inn:
                        child_key = f"legal::inn::{inn}"
                    else:
                        continue
                    if child_key not in beneficiaries:
                        beneficiaries[child_key] = {
                            "_kind": "legal_text",
                            "_ogrn": ogrn, "_inn": inn, "_name": name,
                            "_addresses": [], "_sources": [], "_founders_links": [],
                            "attrs": {
                                "Тип субъекта": "Юридическое лицо (учредитель)",
                                "ОГРН": ogrn,
                                "ИНН": inn,
                                "Наименование": name,
                                "Страна": link.get("country"),
                                "Регистрационный номер": link.get("reg_number"),
                            },
                        }
                        beneficiaries[child_key]["attrs"] = {
                            k: v for k, v in beneficiaries[child_key]["attrs"].items()
                            if v not in (None, "")
                        }
            edge_key = (child_key, b_key, link.get("kind") or "")
            if edge_key in seen:
                continue
            seen.add(edge_key)
            chains.append({
                "founder_key": child_key,
                "child_key": b_key,
                "share_percent": link.get("share_percent"),
                "context": link.get("context"),
                "kind": link.get("kind"),
            })
    return chains


def beneficiary_display_name(payload: dict) -> str:
    if not payload:
        return "?"
    if payload.get("_kind") == "person":
        return "физическое лицо"
    attrs = payload.get("attrs", {})
    name = attrs.get("Краткое наименование") or attrs.get("Полное наименование") or attrs.get("Наименование (из текста)") or attrs.get("Наименование")
    if name:
        return name
    inn = attrs.get("ИНН") or payload.get("_inn")
    if inn:
        return f"ИНН {inn}"
    return "юридическое лицо"


def reorder_beneficiary_attrs(attrs: dict) -> dict:
    licences = attrs.pop("Лицензии", None)
    sources = attrs.pop("Источники данных", None)
    out = dict(attrs)
    if licences is not None:
        out["Лицензии"] = licences
    if sources is not None:
        out["Источники данных"] = sources
    return out


def build_output(
    merged_objects: dict, cert_mapping: dict,
    rights_by_key: dict, encumbrances_by_key: dict,
    beneficiaries: dict, business_units: list[dict],
    founder_chains: list[dict], sources: list[dict],
) -> dict:
    sources_index = {s["id"]: s for s in sources}

    def expand_sources(srcs):
        result = []
        seen = set()
        for s in srcs:
            sid = s.get("источник_id") if isinstance(s, dict) else s
            if not sid or sid in seen:
                continue
            seen.add(sid)
            descriptor = sources_index.get(sid)
            if descriptor:
                result.append({"id": sid, "тип": descriptor["kind"], "файл": descriptor["file"]})
            else:
                result.append({"id": sid})
        return result

    def expand_beneficiaries(keys_list):
        out = []
        for k in keys_list or []:
            payload = beneficiaries.get(k)
            if not payload:
                continue
            out.append({
                "ключ": k,
                "наименование": beneficiary_display_name(payload),
                "тип": "физическое лицо" if payload.get("_kind") == "person" else "юридическое лицо",
                "ИНН": payload.get("attrs", {}).get("ИНН") or payload.get("_inn"),
                "ОГРН": payload.get("_ogrn") or payload.get("attrs", {}).get("ОГРН"),
            })
        return out

    final_objects: dict = {}
    for key, obj in merged_objects.items():
        if obj.get("_is_certificate_placeholder") and key in cert_mapping:
            continue
        cn = obj.get("Кадастровый номер") or key
        attrs = obj.get("_attrs_raw", {}).copy()

        clean_attrs: dict = {
            "Кадастровый номер": cn,
            "Вид объекта недвижимости": obj.get("Вид объекта недвижимости") or "Неизвестно",
        }
        for k, v in attrs.items():
            if k in ("Кадастровый номер", "Вид объекта недвижимости"):
                continue
            clean_attrs[k] = v

        if obj.get("_geometry"):
            clean_attrs["_geometry"] = obj["_geometry"]

        variants = obj.get("_attrs_variants") or {}
        if variants:
            expanded_variants = {}
            for k, vlist in variants.items():
                expanded_variants[k] = [
                    {"значение": x.get("значение"), "Источники": expand_sources([x.get("источник_id")])}
                    for x in vlist
                ]
            clean_attrs["_альтернативные_значения"] = expanded_variants

        related = obj.get("_related_raw") or {}
        if related:
            clean_attrs["Связанные объекты"] = related

        rights_list = []
        encumbrances_list = []
        for (obj_cn, _), right in rights_by_key.items():
            if obj_cn != cn:
                continue
            rec = {k: v for k, v in right.items() if not k.startswith("_") and k != "Источники"}
            rec["Источники"] = expand_sources(right.get("Источники", []))
            rec["Бенефициары"] = expand_beneficiaries(right.get("_beneficiary_keys", []))
            if "_варианты" in right:
                rec["_альтернативные_значения"] = right["_варианты"]
            rights_list.append(rec)
        for (obj_cn, _), enc in encumbrances_by_key.items():
            if obj_cn != cn:
                continue
            rec = {k: v for k, v in enc.items() if not k.startswith("_") and k != "Источники"}
            rec["Источники"] = expand_sources(enc.get("Источники", []))
            rec["Бенефициары"] = expand_beneficiaries(enc.get("_beneficiary_keys", []))
            if "_варианты" in enc:
                rec["_альтернативные_значения"] = enc["_варианты"]
            encumbrances_list.append(rec)

        if rights_list:
            clean_attrs["Права"] = rights_list
        if encumbrances_list:
            clean_attrs["Обременения"] = encumbrances_list

        related_bu = [bu for bu in business_units if bu.get("_object_cn") == cn]
        if related_bu:
            clean_attrs["Бизнес-единицы"] = [
                {
                    "ключ": bu["_bu_key"], "наименование": bu["Наименование"],
                    "КПП": bu.get("КПП"),
                    "бенефициар_ключ": bu["_beneficiary_key"],
                    "бенефициар": beneficiary_display_name(beneficiaries.get(bu["_beneficiary_key"], {})),
                }
                for bu in related_bu
            ]

        clean_attrs["Источники данных"] = expand_sources(obj.get("_sources_for_attrs", []))
        final_objects[cn] = clean_attrs

    by_category: dict[str, dict] = {}
    for cn, attrs in final_objects.items():
        cat = CATEGORY_FOR_TYPE.get(attrs.get("Вид объекта недвижимости"), "Другое")
        by_category.setdefault(cat, {})[cn] = attrs

    beneficiaries_out: dict = {}
    for b_key, payload in sorted(beneficiaries.items()):
        attrs = dict(payload.get("attrs", {}))
        attrs["Источники данных"] = expand_sources(payload.get("_sources", []))
        related_bu = [bu for bu in business_units if bu.get("_beneficiary_key") == b_key]
        if related_bu:
            attrs["Бизнес-единицы"] = [
                {"ключ": bu["_bu_key"], "наименование": bu["Наименование"],
                 "КПП": bu.get("КПП"), "объект_кн": bu["_object_cn"]}
                for bu in related_bu
            ]
        founders_in = [c for c in founder_chains if c["child_key"] == b_key]
        if founders_in:
            attrs["Учредители (связи)"] = [
                {"ключ": c["founder_key"],
                 "наименование": beneficiary_display_name(beneficiaries.get(c["founder_key"], {})),
                 "доля_процент": c.get("share_percent"),
                 "примечание": c.get("context")}
                for c in founders_in
            ]
        founded_out = [c for c in founder_chains if c["founder_key"] == b_key]
        if founded_out:
            attrs["Является учредителем"] = [
                {"ключ": c["child_key"],
                 "наименование": beneficiary_display_name(beneficiaries.get(c["child_key"], {})),
                 "доля_процент": c.get("share_percent")}
                for c in founded_out
            ]
        attrs = reorder_beneficiary_attrs(attrs)
        beneficiaries_out[b_key] = {
            "_kind": payload.get("_kind"),
            "Наименование (отображаемое)": beneficiary_display_name(payload),
            **attrs,
        }

    business_units_out = []
    for bu in business_units:
        rec = {
            "Ключ": bu["_bu_key"],
            "Наименование": bu["Наименование"],
            "КПП": bu.get("КПП"),
            "Адрес": bu.get("Адрес"),
            "Объект (КН)": bu.get("_object_cn"),
            "Бенефициар (ключ)": bu.get("_beneficiary_key"),
            "Бенефициар (наименование)": beneficiary_display_name(beneficiaries.get(bu["_beneficiary_key"], {})),
            "Совпадение адреса, %": bu.get("Совпадение адреса, %"),
        }
        business_units_out.append(rec)

    out: dict = {
        "data": by_category,
        "beneficiaries": beneficiaries_out,
        "business_units": business_units_out,
        "founder_chains": founder_chains,
        "metadata": {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "version": "enrich-5.1",
            "sources": sources,
            "objects_count": sum(len(v) for v in by_category.values()),
            "beneficiaries_count": len(beneficiaries_out),
            "business_units_count": len(business_units_out),
            "founder_chains_count": len(founder_chains),
        },
    }
    return out


def main():
    print("=== Обогатитель данных об объектах недвижимости и бенефициарах ===\n")
    paths: list[Path] = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            paths.append(Path(arg.strip().strip('"').strip("'")))
    else:
        print("Введите пути к файлам (один путь в строке). Пустая строка — конец.\n")
        while True:
            try:
                line = input("Файл: ").strip().strip('"').strip("'")
            except EOFError:
                break
            if not line:
                break
            paths.append(Path(line))

    if not paths:
        print("[!] Не указано ни одного файла.")
        sys.exit(1)

    sources: list[dict] = []
    source_kinds: dict[str, str] = {}
    all_object_streams: list[tuple[dict, str]] = []
    all_rights_streams: list[list[dict]] = []
    all_encumbrances_streams: list[list[dict]] = []
    known_legal: dict = {}

    for path in paths:
        if not path.exists():
            print(f"[!] Файл не найден: {path}")
            sys.exit(1)
        try:
            data = load_file(path)
        except Exception as e:
            print(f"[!] Ошибка чтения {path}: {e}")
            sys.exit(1)

        kind = detect_file_kind(data, path)
        if kind == "unknown":
            print(f"[!] Не удалось определить формат файла: {path}")
            sys.exit(1)

        descriptor = make_source_descriptor(path, kind)
        sources.append(descriptor)
        source_id = descriptor["id"]
        source_kinds[source_id] = kind

        if kind == "nspd":
            objs, rs, es = parse_nspd(data, source_id)
            all_object_streams.append((objs, source_id))
            all_rights_streams.append(rs)
            all_encumbrances_streams.append(es)
            print(f"[+] {path.name} → формат: nspd, объектов: {len(objs)}, прав: {len(rs)}, обременений: {len(es)}")
        elif kind == "egrn":
            objs, rs, es = parse_egrn(data, source_id)
            all_object_streams.append((objs, source_id))
            all_rights_streams.append(rs)
            all_encumbrances_streams.append(es)
            print(f"[+] {path.name} → формат: egrn, объектов: {len(objs)}, прав: {len(rs)}, обременений: {len(es)}")
        elif kind == "kadbase":
            objs, rs, es = parse_kadbase(data, source_id, path.name)
            all_object_streams.append((objs, source_id))
            all_rights_streams.append(rs)
            all_encumbrances_streams.append(es)
            print(f"[+] {path.name} → формат: kadbase, объектов: {len(objs)}")
        elif kind == "kml":
            objs, rs, es = parse_kml(path, source_id)
            all_object_streams.append((objs, source_id))
            all_rights_streams.append(rs)
            all_encumbrances_streams.append(es)
            geom_count = sum(1 for o in objs.values() if o.get("_geometry"))
            print(f"[+] {path.name} → формат: kml, объектов: {len(objs)}, с геометрией: {geom_count}")
        elif kind == "certificate":
            objs, rs, es = parse_certificate(data, source_id, path.name)
            all_object_streams.append((objs, source_id))
            all_rights_streams.append(rs)
            all_encumbrances_streams.append(es)
            print(f"[+] {path.name} → формат: certificate, объектов: {len(objs)}, прав: {len(rs)}")
        elif kind == "legal_entity":
            legal, founders = parse_legal_entity(data, source_id)
            for k, v in legal.items():
                if k in known_legal:
                    known_legal[k]["_sources"].extend(v.get("_sources", []))
                    known_legal[k].setdefault("_founders_links", []).extend(v.get("_founders_links", []))
                else:
                    known_legal[k] = v
            name = beneficiary_display_name(legal[next(iter(legal))]) if legal else "?"
            print(f"[+] {path.name} → формат: legal_entity, юрлицо: {name}, учредителей: {len(founders)}")

    merged = merge_objects(all_object_streams, source_kinds)

    floors_enriched = enrich_floors_from_premises(merged)
    if floors_enriched:
        print(f"[+] Этажность обогащена по помещениям: ОКС={floors_enriched}")

    output_path = Path(f"enriched_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    decisions_path = output_path.with_name("match_decisions.json")
    decisions = MatchDecisions(decisions_path)

    cert_only_objects = {k: v for k, v in merged.items() if v.get("_is_certificate_placeholder")}
    if cert_only_objects:
        print("\n--- Сопоставление свидетельств с объектами ---")
        cert_mapping = resolve_certificate_matches(cert_only_objects, merged, decisions)
    else:
        cert_mapping = {}

    rights_by_key, beneficiaries_r = merge_rights_or_encumbrances(all_rights_streams, cert_mapping, known_legal)
    encumbrances_by_key, beneficiaries_e = merge_rights_or_encumbrances(all_encumbrances_streams, cert_mapping, known_legal)

    beneficiaries = dict(known_legal)
    for src_map in (beneficiaries_r, beneficiaries_e):
        for k, v in src_map.items():
            if k not in beneficiaries:
                beneficiaries[k] = v
            else:
                existing_srcs = beneficiaries[k].setdefault("_sources", [])
                for s in v.get("_sources", []):
                    if s not in existing_srcs:
                        existing_srcs.append(s)

    print("\n--- Определение бизнес-единиц по совпадению адресов ---")
    business_units = detect_business_units(merged, beneficiaries, decisions)
    print(f"  Создано бизнес-единиц: {len(business_units)}")

    print("\n--- Построение цепочек учредителей ---")
    founder_chains = build_founder_chains(beneficiaries)
    print(f"  Найдено связей учредитель→дочернее: {len(founder_chains)}")

    output = build_output(merged, cert_mapping, rights_by_key, encumbrances_by_key,
                          beneficiaries, business_units, founder_chains, sources)

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"\n[+] Сохранено: {output_path}")
    print(f"[+] Решения по сопоставлению: {decisions_path}")
    print(f"[+] Объектов: {output['metadata']['objects_count']}")
    print(f"[+] Бенефициаров: {output['metadata']['beneficiaries_count']}")
    print(f"[+] Бизнес-единиц: {output['metadata']['business_units_count']}")
    print(f"[+] Цепочек учредителей: {output['metadata']['founder_chains_count']}")
    total_rights = sum(len(o.get("Права", [])) for cat in output["data"].values() for o in cat.values())
    total_enc = sum(len(o.get("Обременения", [])) for cat in output["data"].values() for o in cat.values())
    print(f"[+] Прав: {total_rights}, обременений: {total_enc}")


if __name__ == "__main__":
    main()
