import json
import re
import sys
import html
import hashlib
import math
from pathlib import Path
from datetime import datetime


CN_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?$")
CN_PART_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+/\d+$")

TYPE_COLORS = {
    "Земельный участок": {"bg": "#7fc97f", "border": "#2d5a2d", "font": "#0a1f0a"},
    "Единое землепользование": {"bg": "#5fa55f", "border": "#1f4a1f", "font": "#000000"},
    "Здание": {"bg": "#fdae6b", "border": "#7a4515", "font": "#2a1505"},
    "Сооружение": {"bg": "#bcbddc", "border": "#3d3d70", "font": "#0a0a30"},
    "Помещение": {"bg": "#9ecae1", "border": "#1f4d6f", "font": "#04253b"},
    "Объект незавершенного строительства": {"bg": "#fcbba1", "border": "#7a3818", "font": "#2a0f05"},
    "Часть ЗУ": {"bg": "#d9d9d9", "border": "#5a5a5a", "font": "#202020"},
    "Часть ОКС": {"bg": "#d9d9d9", "border": "#5a5a5a", "font": "#202020"},
    "Право": {"bg": "#6baed6", "border": "#3182bd", "font": "#ffffff"},
    "Обременение": {"bg": "#3182bd", "border": "#08519c", "font": "#ffffff"},
    "Бенефициар (юр.лицо)": {"bg": "#e85b5b", "border": "#a83a3a", "font": "#ffffff"},
    "Бенефициар (физ.лицо)": {"bg": "#f8a5a5", "border": "#c87575", "font": "#5a1a1a"},
    "Бизнес-единица": {"bg": "#d94545", "border": "#8a2020", "font": "#ffffff"},
    "Уровень": {"bg": "#f5d76e", "border": "#a08020", "font": "#3a2a08"},
    "Оборудование": {"bg": "#dcdcdc", "border": "#707070", "font": "#202020"},
    "Неизвестно": {"bg": "#e8e8e8", "border": "#a0a0a0", "font": "#606060"},
}

CATEGORY_COLORS = {
    "Земельные участки": {"bg": "#2d6a2d", "border": "#1a4a1a", "font": "#ffffff"},
    "Здания": {"bg": "#a64d1a", "border": "#6e3010", "font": "#ffffff"},
    "Сооружения": {"bg": "#5a4a8a", "border": "#3a2e60", "font": "#ffffff"},
    "Помещения": {"bg": "#2a6a8a", "border": "#1a4a60", "font": "#ffffff"},
    "Объекты незавершенного строительства": {"bg": "#a05030", "border": "#703a20", "font": "#ffffff"},
    "Права": {"bg": "#08519c", "border": "#08306b", "font": "#ffffff"},
    "Обременения": {"bg": "#08306b", "border": "#041632", "font": "#ffffff"},
    "Бенефициары": {"bg": "#a83a3a", "border": "#6a1a1a", "font": "#ffffff"},
    "Бизнес-единицы": {"bg": "#8a2020", "border": "#5a0e0e", "font": "#ffffff"},
    "Уровни": {"bg": "#a07020", "border": "#604010", "font": "#ffffff"},
    "Оборудование": {"bg": "#606060", "border": "#303030", "font": "#ffffff"},
    "Другое": {"bg": "#404040", "border": "#202020", "font": "#ffffff"},
}

EDGE_COLORS = {
    "category": {"color": "#888888", "dashes": True},
    "land_to_building": {"color": "#4a8a4a", "dashes": False},
    "building_to_land": {"color": "#4a8a4a", "dashes": False},
    "building_to_premises": {"color": "#c67c3a", "dashes": False},
    "part": {"color": "#969696", "dashes": True},
    "ezp": {"color": "#7c7eb3", "dashes": True},
    "right": {"color": "#3182bd", "dashes": False},
    "encumbrance": {"color": "#08519c", "dashes": False},
    "beneficiary": {"color": "#a83a3a", "dashes": False},
    "business_unit": {"color": "#d94545", "dashes": False},
    "founder": {"color": "#c060c0", "dashes": False},
    "level_in_building":   {"color": "#a08020", "dashes": False},
    "equipment_on_level":  {"color": "#606060", "dashes": False},
    "equipment_at_object": {"color": "#606060", "dashes": True},
    "equipment_in_bu":     {"color": "#8a2020", "dashes": True},
    "other": {"color": "#999999", "dashes": False},
}

FILTER_GROUPS = [
    {"key": "land", "label": "Земельные участки", "category": "Земельные участки", "color": "#7fc97f"},
    {"key": "land_parts", "label": "Части ЗУ", "category": "Части ЗУ", "color": "#d9d9d9"},
    {"key": "building", "label": "Здания", "category": "Здания", "color": "#fdae6b"},
    {"key": "construction", "label": "Сооружения", "category": "Сооружения", "color": "#bcbddc"},
    {"key": "premises", "label": "Помещения", "category": "Помещения", "color": "#9ecae1"},
    {"key": "uncompleted", "label": "Незавершённое строительство", "category": "Объекты незавершенного строительства", "color": "#fcbba1"},
    {"key": "rights", "label": "Права", "category": "Права", "color": "#6baed6"},
    {"key": "encumbrances", "label": "Обременения", "category": "Обременения", "color": "#3182bd"},
    {"key": "beneficiaries", "label": "Бенефициары", "category": "Бенефициары", "color": "#e85b5b"},
    {"key": "business_units", "label": "Бизнес-единицы", "category": "Бизнес-единицы", "color": "#d94545"},
    {"key": "levels", "label": "Уровни (этажи)", "category": "Уровни", "color": "#f5d76e"},
    {"key": "equipment", "label": "Оборудование (ОС)", "category": "Оборудование", "color": "#dcdcdc"},
    {"key": "categories", "label": "Категории", "category": "_categories_", "color": "#888888"},
]


def stable_hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:12]


def detect_type(cn: str, attrs: dict) -> str:
    v = attrs.get("Вид объекта недвижимости")
    if isinstance(v, str) and v.strip():
        return v.strip()
    if CN_PART_RE.match(cn or ""):
        return "Часть ЗУ"
    return "Неизвестно"


def category_for_type(t: str) -> str:
    mapping = {
        "Земельный участок": "Земельные участки",
        "Единое землепользование": "Земельные участки",
        "Здание": "Здания",
        "Сооружение": "Сооружения",
        "Помещение": "Помещения",
        "Объект незавершенного строительства": "Объекты незавершенного строительства",
    }
    return mapping.get(t, "Другое")


def filter_key_for_node(node: dict) -> str | None:
    kind = node.get("kind")
    t = node.get("type")
    if kind == "object" or kind == "stub":
        if t in ("Земельный участок", "Единое землепользование"):
            return "land"
        if t == "Здание":
            return "building"
        if t == "Сооружение":
            return "construction"
        if t == "Помещение":
            return "premises"
        if t == "Объект незавершенного строительства":
            return "uncompleted"
        if "Часть" in (t or ""):
            return "land"
        return None
    if kind == "right":
        return "rights"
    if kind == "enc":
        return "encumbrances"
    if kind == "beneficiary":
        return "beneficiaries"
    if kind == "business_unit":
        return "business_units"
    if kind == "level":
        return "levels"
    if kind == "equipment":
        return "equipment"
    return None


def parse_input(data: dict):
    root = data.get("data", data) if isinstance(data, dict) else {}
    objects = {}
    rights_records = []
    encumbrances_records = []
    for category, items in root.items():
        if not isinstance(items, dict):
            continue
        for cn, attrs in items.items():
            if not isinstance(attrs, dict):
                continue
            t = detect_type(cn, attrs)
            real_category = category_for_type(t) if t != "Неизвестно" else (category or "Другое")
            objects[cn] = {"cn": cn, "type": t, "category": real_category, "attrs": attrs}
            for r in attrs.get("Права", []) or []:
                if isinstance(r, dict):
                    rights_records.append((cn, r))
            for e in attrs.get("Обременения", []) or []:
                if isinstance(e, dict):
                    encumbrances_records.append((cn, e))
    beneficiaries = data.get("beneficiaries", {}) if isinstance(data, dict) else {}
    business_units = data.get("business_units", []) if isinstance(data, dict) else []
    founder_chains = data.get("founder_chains", []) if isinstance(data, dict) else []
    return objects, rights_records, encumbrances_records, beneficiaries, business_units, founder_chains


def parse_structure(structure: dict):
    """
    Парсит structure_*.json из 052_make_structure_v1.py и возвращает:
      levels:       [{id, number, type, label, cadastral_source, …}]
      equipment:    [{id, name, account, amounts, links:{…}}]
      bu_extra:     [{Ключ, Наименование, КПП, Адрес, Объект (КН), …}]
                    — бизнес-единицы из 052, которые ещё не присутствуют в
                    enriched.business_units (matching по anchor_cadastral
                    или по совпадению ключа).
      enterprise:   dict из 052 (для информационного узла).
    """
    if not isinstance(structure, dict):
        return [], [], [], {}
    levels: list[dict] = []
    for cad in structure.get("cadastre_objects", []) or []:
        cn = cad.get("cadastral_number")
        for lvl in cad.get("levels", []) or []:
            if not isinstance(lvl, dict):
                continue
            row = dict(lvl)
            row["cadastral_source"] = row.get("cadastral_source") or cn
            levels.append(row)
    equipment = [e for e in (structure.get("equipment", []) or []) if isinstance(e, dict)]
    bu_extra: list[dict] = []
    for bu in structure.get("business_units", []) or []:
        if not isinstance(bu, dict):
            continue
        # Если ключ уже выглядит как enrich-bu::… — это «поглощённая» BU,
        # она будет нарисована из enrich; пропускаем.
        if str(bu.get("id", "")).startswith("bu::"):
            continue
        bu_extra.append({
            "Ключ": bu["id"],
            "Наименование": bu.get("name") or "Бизнес-единица",
            "КПП": None,
            "Адрес": bu.get("address"),
            "Объект (КН)": bu.get("anchor_cadastral"),
            "Бенефициар (ключ)": bu.get("beneficiary_key"),
            "Бенефициар (наименование)": None,
            "_from_structure": True,
        })
    enterprise = structure.get("enterprise", {}) or {}
    return levels, equipment, bu_extra, enterprise


def classify_edge_group(group_name: str) -> tuple[str, str]:
    g = (group_name or "").lower()
    if "помещен" in g:
        return "building_to_premises", "Помещения"
    if "здания" in g and "сооружен" in g and "которо" in g:
        return "building_to_premises", "Помещение в здании"
    if "земельного участка" in g and ("границах" in g or "расположен" in g):
        return "land_to_building", "На участке расположен"
    if "является частью окс" in g:
        return "building_to_premises", "Часть здания"
    if "список объектов" in g or "здания и сооружения" in g or "объект недвижимости" in g:
        return "land_to_building", "На участке расположен"
    if "часть" in g and ("зу" in g or "земельн" in g):
        return "part", "Часть ЗУ"
    if "часть" in g and "окс" in g:
        return "part", "Часть ОКС"
    if "состав" in g and "езп" in g:
        return "ezp", "Состав ЕЗП"
    return "other", group_name or "Связан"


def right_node_id(obj_cn: str, kind_prefix: str, record: dict) -> str:
    number = record.get("Номер регистрации") or record.get("Условный номер") or ""
    type_text = record.get("Вид права") or record.get("Вид обременения") or ""
    base = stable_hash(kind_prefix, obj_cn or "", str(number), type_text)
    return f"{kind_prefix}::{base}"


def right_node_label(record: dict) -> str:
    head = record.get("Вид права") or record.get("Вид обременения") or "Право"
    num = record.get("Номер регистрации") or ""
    if num:
        return f"{head}\n№ {num}"
    return head


def beneficiary_label(b_data: dict) -> str:
    name = b_data.get("Наименование (отображаемое)") or "?"
    inn = b_data.get("ИНН") or b_data.get("_inn")
    if b_data.get("_kind") == "person":
        return name
    if inn:
        return f"{name}\nИНН {inn}"
    return name


def collect_areas_by_category(objects: dict) -> dict:
    by_cat: dict[str, list[float]] = {}
    for cn, obj in objects.items():
        attrs = obj.get("attrs", {}) or {}
        area = attrs.get("Площадь, кв.м") or attrs.get("Площадь")
        try:
            f = float(str(area).replace(",", ".").split()[0]) if area is not None else None
        except (ValueError, AttributeError):
            f = None
        if f is None or f <= 0:
            continue
        cat = obj.get("category") or "Другое"
        by_cat.setdefault(cat, []).append(f)
    return by_cat


def compute_size_for_object(obj: dict, by_cat_stats: dict) -> int:
    base = 22
    attrs = obj.get("attrs", {}) or {}
    area = attrs.get("Площадь, кв.м") or attrs.get("Площадь")
    try:
        f = float(str(area).replace(",", ".").split()[0]) if area is not None else None
    except (ValueError, AttributeError):
        f = None
    if not f or f <= 0:
        return base
    cat = obj.get("category") or "Другое"
    stats = by_cat_stats.get(cat)
    if not stats or len(stats) < 1:
        return base
    log_vals = [math.log(max(x, 1.0)) for x in stats]
    cur = math.log(max(f, 1.0))
    min_l, max_l = min(log_vals), max(log_vals)
    if max_l - min_l < 1e-6:
        return base
    rel = (cur - min_l) / (max_l - min_l)
    return int(round(14 + rel * 22))


def is_deregistered_attrs(attrs: dict) -> bool:
    for k in ("Статус", "Статус объекта"):
        v = attrs.get(k)
        if v is None:
            continue
        s = str(v).lower()
        if "снят" in s or "погашен" in s:
            return True
    return False


def build_graph(objects: dict, rights_records: list, encumbrances_records: list,
                beneficiaries: dict, business_units: list, founder_chains: list,
                levels: list | None = None, equipment: list | None = None):
    levels = levels or []
    equipment = equipment or []
    nodes = []
    edges = []
    seen_node_ids = set()
    seen_edge_keys = set()

    by_cat_stats = collect_areas_by_category(objects)

    categories_in_use: dict = {}
    for cn, obj in objects.items():
        categories_in_use.setdefault(obj["category"], []).append(cn)
    if rights_records:
        categories_in_use["Права"] = [r for _, r in rights_records]
    if encumbrances_records:
        categories_in_use["Обременения"] = [e for _, e in encumbrances_records]
    if beneficiaries:
        categories_in_use["Бенефициары"] = list(beneficiaries.keys())
    if business_units:
        categories_in_use["Бизнес-единицы"] = [bu.get("Ключ") for bu in business_units]
    if levels:
        categories_in_use["Уровни"] = [lvl.get("id") for lvl in levels]
    if equipment:
        categories_in_use["Оборудование"] = [eq.get("id") for eq in equipment]

    for cat, items in categories_in_use.items():
        node_id = f"cat::{cat}"
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        colors = CATEGORY_COLORS.get(cat, CATEGORY_COLORS["Другое"])
        nodes.append({
            "id": node_id, "label": cat,
            "kind": "category", "type": cat,
            "color": colors, "size": 20, "shape": "hexagon",
            "tooltip": f"Категория: {cat}\nЭлементов: {len(items)}",
            "attrs": {"_количество_элементов": len(items)},
        })

    for cn, obj in objects.items():
        if cn in seen_node_ids:
            continue
        seen_node_ids.add(cn)
        t = obj["type"]
        colors = TYPE_COLORS.get(t, TYPE_COLORS["Неизвестно"])
        shape = "dot"
        if t in ("Здание", "Сооружение", "Объект незавершенного строительства"):
            shape = "square"
        elif t in ("Земельный участок", "Единое землепользование"):
            shape = "diamond"
        elif t == "Помещение":
            shape = "dot"
        elif "Часть" in t:
            shape = "triangle"

        size = compute_size_for_object(obj, by_cat_stats)
        deregistered = is_deregistered_attrs(obj.get("attrs", {}) or {})

        nodes.append({
            "id": cn, "label": cn,
            "kind": "object", "type": t,
            "color": colors, "size": size, "shape": shape,
            "tooltip": f"{t}\n{cn}",
            "attrs": obj["attrs"],
            "deregistered": deregistered,
            "geometry": obj["attrs"].get("_geometry"),
        })

    def add_edge(a, b, label, kind):
        if a == b:
            return
        key = (tuple(sorted([a, b])), label, kind)
        if key in seen_edge_keys:
            return
        seen_edge_keys.add(key)
        e = EDGE_COLORS.get(kind, EDGE_COLORS["other"])
        edges.append({
            "from": a, "to": b, "label": label,
            "color": e["color"], "dashes": e["dashes"], "kind": kind,
        })

    def ensure_stub(cn):
        if cn in seen_node_ids:
            return
        seen_node_ids.add(cn)
        if CN_PART_RE.match(cn):
            t = "Часть ЗУ"
            shape = "triangle"
        else:
            t = "Неизвестно"
            shape = "dot"
        colors = TYPE_COLORS.get(t, TYPE_COLORS["Неизвестно"])
        nodes.append({
            "id": cn, "label": cn,
            "kind": "stub", "type": t,
            "color": colors, "size": 16, "shape": shape,
            "tooltip": f"{t}\n{cn}\n(нет атрибутов в JSON)",
            "attrs": {"_примечание": "Объект упомянут в связях, но отсутствует как карточка в JSON"},
            "deregistered": False,
        })

    DIRECTED_KIND_PRIORITY_LABEL = {
        "land_to_building": "На участке расположен",
        "building_to_premises": "Помещение в здании",
        "part": "Часть",
        "ezp": "Состав ЕЗП",
    }
    land_types = {"Земельный участок", "Единое землепользование"}
    building_types = {"Здание", "Сооружение", "Объект незавершенного строительства"}
    premises_types = {"Помещение"}

    pending_pair_edges: dict = {}

    def queue_pair_edge(a, b, label, kind):
        if a == b:
            return
        key = (tuple(sorted([a, b])), kind)
        existing = pending_pair_edges.get(key)
        preferred_label = DIRECTED_KIND_PRIORITY_LABEL.get(kind, label)
        if existing is None:
            pending_pair_edges[key] = (a, b, preferred_label, kind)
        else:
            pass

    for cn, obj in objects.items():
        add_edge(f"cat::{obj['category']}", cn, "содержит", "category")
        related = obj["attrs"].get("Связанные объекты") or {}
        if isinstance(related, dict):
            for group, value in related.items():
                if not isinstance(value, list):
                    continue
                kind, label = classify_edge_group(group)
                for target in value:
                    target = str(target).strip()
                    if not CN_RE.match(target):
                        continue
                    ensure_stub(target)
                    if kind in ("land_to_building", "building_to_premises"):
                        src_obj = objects.get(cn)
                        tgt_obj = objects.get(target)
                        src_type = (src_obj or {}).get("type", "")
                        tgt_type = (tgt_obj or {}).get("type", "")
                        if kind == "land_to_building":
                            if src_type in building_types and tgt_type in land_types:
                                queue_pair_edge(target, cn, label, kind)
                                continue
                            if src_type in land_types and tgt_type in building_types:
                                queue_pair_edge(cn, target, label, kind)
                                continue
                            queue_pair_edge(cn, target, label, kind)
                            continue
                        if kind == "building_to_premises":
                            if src_type in premises_types and tgt_type in building_types:
                                queue_pair_edge(target, cn, label, kind)
                                continue
                            if src_type in building_types and tgt_type in premises_types:
                                queue_pair_edge(cn, target, label, kind)
                                continue
                            queue_pair_edge(cn, target, label, kind)
                            continue
                    add_edge(cn, target, label, kind)

    for (_, kind), (a, b, label, _) in pending_pair_edges.items():
        add_edge(a, b, label, kind)

    for b_key, b_data in (beneficiaries or {}).items():
        if b_key in seen_node_ids:
            continue
        seen_node_ids.add(b_key)
        is_person = b_data.get("_kind") == "person"
        node_type = "Бенефициар (физ.лицо)" if is_person else "Бенефициар (юр.лицо)"
        colors = TYPE_COLORS[node_type]
        label = beneficiary_label(b_data)
        nodes.append({
            "id": b_key, "label": label,
            "kind": "beneficiary", "type": node_type,
            "color": colors, "size": 20, "shape": "dot",
            "tooltip": f"{node_type}\n{b_data.get('Наименование (отображаемое)') or ''}",
            "attrs": b_data, "deregistered": False,
        })
        add_edge("cat::Бенефициары", b_key, "содержит", "category")

    def add_right_or_enc(obj_cn, record, prefix, type_label, edge_kind, beneficiary_edge_label):
        node_id = right_node_id(obj_cn, prefix, record)
        if node_id not in seen_node_ids:
            seen_node_ids.add(node_id)
            colors = TYPE_COLORS[type_label]
            shape = "dot" if prefix == "right" else "triangle"
            nodes.append({
                "id": node_id, "label": right_node_label(record),
                "kind": prefix, "type": type_label,
                "color": colors, "size": 18, "shape": shape,
                "tooltip": f"{type_label}\n{record.get('Вид права') or record.get('Вид обременения') or ''}\n№ {record.get('Номер регистрации', '')}",
                "attrs": record, "deregistered": False,
            })
        cat_name = "Права" if prefix == "right" else "Обременения"
        add_edge(f"cat::{cat_name}", node_id, "содержит", "category")
        if obj_cn and obj_cn in objects:
            add_edge(obj_cn, node_id, "имеет " + ("право" if prefix == "right" else "обременение"), edge_kind)
        for bdata in record.get("Бенефициары", []) or []:
            bkey = bdata.get("ключ")
            if bkey:
                add_edge(node_id, bkey, beneficiary_edge_label, "beneficiary")

    for obj_cn, record in rights_records:
        add_right_or_enc(obj_cn, record, "right", "Право", "right", "правообладатель")
    for obj_cn, record in encumbrances_records:
        add_right_or_enc(obj_cn, record, "enc", "Обременение", "encumbrance", "в пользу")

    for bu in business_units:
        bu_key = bu.get("Ключ")
        if not bu_key or bu_key in seen_node_ids:
            continue
        seen_node_ids.add(bu_key)
        colors = TYPE_COLORS["Бизнес-единица"]
        label_parts = [bu.get("Наименование") or "Бизнес-единица"]
        if bu.get("КПП"):
            label_parts.append(f"КПП {bu['КПП']}")
        nodes.append({
            "id": bu_key, "label": "\n".join(label_parts),
            "kind": "business_unit", "type": "Бизнес-единица",
            "color": colors, "size": 22, "shape": "square",
            "tooltip": f"Бизнес-единица\n{bu.get('Наименование') or ''}",
            "attrs": bu, "deregistered": False,
        })
        add_edge("cat::Бизнес-единицы", bu_key, "содержит", "category")
        obj_cn = bu.get("Объект (КН)")
        b_key = bu.get("Бенефициар (ключ)")
        if obj_cn and obj_cn in objects:
            add_edge(obj_cn, bu_key, "хозяйственная деятельность", "business_unit")
        if b_key and b_key in beneficiaries:
            add_edge(bu_key, b_key, "ведёт", "business_unit")

    for c in founder_chains or []:
        founder = c.get("founder_key")
        child = c.get("child_key")
        if not founder or not child:
            continue
        if founder in seen_node_ids and child in seen_node_ids:
            share = c.get("share_percent")
            label = "учредитель"
            if share is not None and share != "":
                label = f"учредитель {share}%"
            add_edge(founder, child, label, "founder")

    # ─── Уровни зданий (из structure_*.json) ───────────────────────────
    level_node_id_by_id: dict[str, str] = {}
    for lvl in levels:
        lvl_id = lvl.get("id")
        if not lvl_id:
            continue
        node_id = f"lvl::{lvl_id}"
        level_node_id_by_id[lvl_id] = node_id
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        colors = TYPE_COLORS["Уровень"]
        label = lvl.get("label") or f"Уровень {lvl.get('number','?')}"
        z_str = ""
        if lvl.get("z_meters") is not None:
            z_str = f"\nz = {lvl['z_meters']} м (верх {lvl.get('top_z_meters','?')} м)"
        nodes.append({
            "id": node_id, "label": label,
            "kind": "level", "type": "Уровень",
            "color": colors, "size": 14,
            "shape": "square" if not lvl.get("underground") else "triangleDown",
            "tooltip": f"Уровень\n{label}{z_str}\nКН-источник: {lvl.get('cadastral_source','—')}",
            "attrs": lvl, "deregistered": False,
        })
        add_edge("cat::Уровни", node_id, "содержит", "category")
        parent_cn = lvl.get("cadastral_source")
        if parent_cn and parent_cn in objects:
            add_edge(parent_cn, node_id, "уровень в строении", "level_in_building")

    # ─── Оборудование (из structure_*.json) ────────────────────────────
    bu_node_by_id: dict[str, str] = {bu.get("Ключ"): bu.get("Ключ") for bu in business_units if bu.get("Ключ")}
    for eq in equipment:
        eq_id = eq.get("id")
        if not eq_id:
            continue
        node_id = f"eq::{eq_id}"
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        colors = TYPE_COLORS["Оборудование"]
        name = eq.get("name") or "ОС"
        account = eq.get("account") or ""
        nodes.append({
            "id": node_id, "label": name[:60] + (" …" if len(name) > 60 else ""),
            "kind": "equipment", "type": "Оборудование",
            "color": colors, "size": 8, "shape": "dot",
            "tooltip": f"Оборудование\n{name}\nСчёт {account}",
            "attrs": eq, "deregistered": False,
        })
        add_edge("cat::Оборудование", node_id, "содержит", "category")
        links = eq.get("links", {}) if isinstance(eq.get("links"), dict) else {}
        # Множественные привязки (массивы) — поддержка плоских/старых ссылок
        lvl_ids   = list(links.get("level_ids")        or ([links["level_id"]] if links.get("level_id") else []))
        prem_ids  = list(links.get("premises_ids")     or ([links["premises_id"]] if links.get("premises_id") else []))
        bu_ids    = list(links.get("business_unit_ids")or ([links["business_unit_id"]] if links.get("business_unit_id") else []))

        drawn = False
        for lid in lvl_ids:
            if lid in level_node_id_by_id:
                add_edge(level_node_id_by_id[lid], node_id, "на уровне", "equipment_on_level")
                drawn = True
        # premises_ids в 052 — это cad_id (для type='Помещение'); граф их
        # покрывает через `equipment_at_object` ниже (по cadastral_hints).
        if not drawn:
            for hint in (eq.get("cadastral_hints") or []):
                if CN_RE.match(str(hint)) and hint in objects:
                    add_edge(hint, node_id, "на объекте", "equipment_at_object")
                    drawn = True
                    break

        for bid in bu_ids:
            if bid in bu_node_by_id:
                add_edge(bu_node_by_id[bid], node_id, "ОС бизнес-единицы", "equipment_in_bu")

    return nodes, edges


def build_graph_node_index(nodes: list) -> dict:
    """Sidecar mapping для 08_build_kmz_v2: локально-известные ключи → graph node id.

    Контракт KMZ 2.11.0 §5: маркер в KMZ несёт `graph_node_id` = `id` соответствующего
    узла графа. 08 видит structure.json (где `bu.name`, `eq.id`, `owner.inn/ogrn/name`),
    но не знает формул `legal::inn::<inn>` / `bu::<sha1>` / `eq::<id>`. 04 знает все
    финальные `id` (это `node["id"]` собранных узлов) и эмитит обратный индекс по
    локально-известным ключам, чтобы 08 мог lookup'нуть без дублирования формул.
    """
    idx: dict = {
        "schema": 1,
        "by_cad_number": {},
        "by_bu_name":    {},
        "by_eq_id":      {},
        "by_ben_inn":    {},
        "by_ben_ogrn":   {},
        "by_ben_name":   {},
    }
    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue
        kind = n.get("kind")
        attrs = n.get("attrs") or {}
        if kind == "object":
            idx["by_cad_number"][nid] = nid
        elif kind == "business_unit":
            nm = attrs.get("Наименование") or ""
            if nm:
                idx["by_bu_name"][nm] = nid
        elif kind == "equipment":
            eq_id = attrs.get("id")
            if eq_id is not None:
                idx["by_eq_id"][str(eq_id)] = nid
        elif kind == "beneficiary":
            inner = attrs.get("attrs") or {}
            inn  = inner.get("ИНН")  or attrs.get("ИНН")
            ogrn = inner.get("ОГРН") or attrs.get("ОГРН")
            nm   = attrs.get("Наименование (отображаемое)") or attrs.get("Наименование") or ""
            if inn:  idx["by_ben_inn"][str(inn)] = nid
            if ogrn: idx["by_ben_ogrn"][str(ogrn)] = nid
            if nm:   idx["by_ben_name"][nm] = nid
    return idx


def render_html(nodes, edges, source_name: str, html_name: str = "") -> str:
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)
    filter_groups_json = json.dumps(FILTER_GROUPS, ensure_ascii=False)
    source_name_json = json.dumps(source_name, ensure_ascii=False)
    html_name_json = json.dumps(html_name or source_name, ensure_ascii=False)
    title = f"Граф объектов недвижимости — {html.escape(source_name)}"
    obj_count = sum(1 for n in nodes if n["kind"] == "object")
    right_count = sum(1 for n in nodes if n["kind"] == "right")
    enc_count = sum(1 for n in nodes if n["kind"] == "enc")
    benef_count = sum(1 for n in nodes if n["kind"] == "beneficiary")
    bu_count = sum(1 for n in nodes if n["kind"] == "business_unit")
    stub_count = sum(1 for n in nodes if n["kind"] == "stub")
    stats = (f"{obj_count} объектов · {right_count} прав · {enc_count} обременений · "
             f"{benef_count} бенефициаров · {bu_count} бизнес-единиц · "
             f"{stub_count} ссылок без данных · {len(edges)} связей")

    vis_network_inline = (Path(__file__).parent.parent / "vendor" / "vis-network-9.1.9.min.js").read_text(encoding="utf-8")

    return (rf"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="ekcelo-graph-protocol" content="1">
<title>{title}</title>
<script>__VIS_NETWORK_INLINE__</script>
<style>
  :root {{
    --bg: #1a1a1d;
    --panel-bg: #232327;
    --graph-bg: #1a1a1d;
    --text: #e8e8e8;
    --text-muted: #909098;
    --border: #3a3a40;
    --btn-bg: #2d2d33;
    --btn-bg-hover: #3a3a40;
    --btn-border: #3a3a40;
    --btn-active: #4a4a55;
    --legend-bg: rgba(26, 26, 29, 0.92);
    --header-bg: rgba(26, 26, 29, 0.85);
    --resizer-bg: #2a2a30;
    --sidebar-section-bg: #2a2a30;
    --inline-bg: #1f1f22;
    --inline-border: #2f2f35;
    --chip-src-bg: #1f2a35;
    --chip-src-color: #9ecae1;
    --chip-src-border: #3a4f5f;
    --chip-benef-bg: #3a1f1f;
    --chip-benef-color: #f8c8c8;
    --chip-benef-border: #6a3535;
    --chip-bu-bg: #4a1a1a;
    --chip-bu-color: #ffcccc;
    --chip-bu-border: #8a2020;
    --cn-color: #9ecae1;
    --print-tip-bg: rgba(26,26,29,0.92);
  }}
  body.theme-light {{
    --bg: #f5f5f7;
    --panel-bg: #ffffff;
    --graph-bg: #ffffff;
    --text: #1a1a1d;
    --text-muted: #5a5a60;
    --border: #d0d0d6;
    --btn-bg: #ffffff;
    --btn-bg-hover: #e8e8ec;
    --btn-border: #c8c8ce;
    --btn-active: #d0d0d6;
    --legend-bg: rgba(255, 255, 255, 0.95);
    --header-bg: rgba(255, 255, 255, 0.92);
    --resizer-bg: #e0e0e5;
    --sidebar-section-bg: #f0f0f3;
    --inline-bg: #f8f8fa;
    --inline-border: #e0e0e5;
    --chip-src-bg: #e8f0f7;
    --chip-src-color: #08306b;
    --chip-src-border: #b8d0e5;
    --chip-benef-bg: #fbe5e5;
    --chip-benef-color: #6a1a1a;
    --chip-benef-border: #e0a8a8;
    --chip-bu-bg: #fbd5d5;
    --chip-bu-color: #5a0e0e;
    --chip-bu-border: #d08585;
    --cn-color: #08519c;
    --print-tip-bg: rgba(255,255,255,0.92);
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }}
  #app {{ display: flex; height: 100vh; }}
  #graph-wrap {{ flex: 1; position: relative; background: var(--graph-bg); overflow: hidden; min-width: 200px; }}
  #graph {{ position: absolute; inset: 0; background: var(--graph-bg); }}
  #resizer {{ width: 6px; cursor: ew-resize; background: var(--resizer-bg); border-left: 1px solid var(--border); border-right: 1px solid var(--border); position: relative; z-index: 5; flex-shrink: 0; }}
  #resizer:hover, #resizer.active {{ background: var(--btn-active); }}
  #resizer::after {{ content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 2px; height: 30px; background: var(--text-muted); border-radius: 1px; }}
  #sidebar {{ width: 440px; min-width: 280px; background: var(--panel-bg); overflow-y: auto; padding: 18px 20px; flex-shrink: 0; }}
  #header {{ position: absolute; top: 12px; left: 16px; right: 16px; z-index: 10; display: flex; justify-content: space-between; align-items: center; pointer-events: none; gap: 12px; flex-wrap: wrap; }}
  #header .title {{ background: var(--header-bg); padding: 8px 14px; border-radius: 6px; font-size: 13px; pointer-events: auto; border: 1px solid var(--border); }}
  #header .stats {{ background: var(--header-bg); padding: 6px 12px; border-radius: 6px; font-size: 11px; color: var(--text-muted); pointer-events: auto; border: 1px solid var(--border); }}
  #controls {{ position: absolute; bottom: 16px; left: 16px; z-index: 10; display: flex; gap: 8px; flex-wrap: wrap; max-width: calc(100% - 32px); }}
  .btn {{ background: var(--btn-bg); color: var(--text); border: 1px solid var(--btn-border); padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; font-family: inherit; }}
  .btn:hover {{ background: var(--btn-bg-hover); border-color: var(--text-muted); }}
  .btn.active {{ background: var(--btn-active); border-color: var(--text-muted); color: var(--text); }}
  #search {{ background: var(--btn-bg); color: var(--text); border: 1px solid var(--btn-border); padding: 6px 12px; border-radius: 4px; font-size: 12px; font-family: inherit; width: 220px; }}
  #search:focus {{ outline: none; border-color: #6a8aa8; }}
  #sidebar h2 {{ margin: 0 0 4px 0; font-size: 16px; font-weight: 600; word-break: break-word; }}
  #sidebar .subtitle {{ color: var(--text-muted); font-size: 13px; margin-bottom: 14px; }}
  #sidebar .type-badge {{ display: inline-block; padding: 3px 9px; border-radius: 4px; font-size: 11px; font-weight: 500; margin-bottom: 14px; }}
  #sidebar table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  #sidebar th {{ text-align: left; font-weight: 500; color: var(--text-muted); padding: 7px 8px 7px 0; font-size: 12px; vertical-align: top; width: 38%; border-bottom: 1px solid var(--border); }}
  #sidebar td {{ padding: 7px 0 7px 8px; font-size: 12.5px; word-break: break-word; border-bottom: 1px solid var(--border); vertical-align: top; }}
  #sidebar td.cn {{ color: var(--cn-color); }}
  #sidebar .cn {{ color: var(--cn-color); }}
  #sidebar .group {{ margin-top: 18px; border-top: 1px solid var(--border); padding-top: 14px; }}
  #sidebar .group h3 {{ font-size: 13px; font-weight: 500; color: var(--text); margin: 0 0 8px 0; }}
  #sidebar .related-item {{ display: block; background: var(--sidebar-section-bg); border: 1px solid var(--border); padding: 5px 9px; margin: 3px 0; border-radius: 4px; color: var(--cn-color); font-size: 12px; cursor: pointer; word-break: break-all; }}
  #sidebar .related-item:hover {{ background: var(--btn-bg-hover); }}
  #sidebar .inline-block {{ background: var(--inline-bg); border: 1px solid var(--inline-border); border-radius: 4px; padding: 6px 9px; margin: 2px 0; font-size: 12px; }}
  #sidebar .inline-row {{ margin: 3px 0; word-break: break-word; line-height: 1.4; }}
  #sidebar .inline-row .ikey {{ color: var(--text-muted); }}
  #sidebar .inline-row .ival {{ color: var(--text); }}
  #sidebar .right-card, #sidebar .enc-card, #sidebar .benef-card, #sidebar .bu-card {{ background: var(--sidebar-section-bg); border-left: 3px solid #3182bd; padding: 8px 11px; margin: 6px 0; border-radius: 4px; font-size: 12px; cursor: pointer; }}
  #sidebar .enc-card {{ border-left-color: #08519c; }}
  #sidebar .benef-card {{ border-left-color: #a83a3a; }}
  #sidebar .bu-card {{ border-left-color: #d94545; }}
  #sidebar .right-card:hover, #sidebar .enc-card:hover, #sidebar .benef-card:hover, #sidebar .bu-card:hover {{ background: var(--btn-bg-hover); }}
  #sidebar .right-card .head, #sidebar .enc-card .head, #sidebar .benef-card .head, #sidebar .bu-card .head {{ font-weight: 600; color: var(--text); margin-bottom: 3px; }}
  #sidebar .right-card .meta, #sidebar .enc-card .meta, #sidebar .benef-card .meta, #sidebar .bu-card .meta {{ color: var(--text-muted); font-size: 11px; }}
  #sidebar .src-chip {{ display: inline-block; background: var(--chip-src-bg); color: var(--chip-src-color); border: 1px solid var(--chip-src-border); padding: 1px 6px; border-radius: 3px; font-size: 10px; margin: 2px 3px 0 0; }}
  #sidebar .benef-chip {{ display: inline-block; background: var(--chip-benef-bg); color: var(--chip-benef-color); border: 1px solid var(--chip-benef-border); padding: 1px 6px; border-radius: 3px; font-size: 10.5px; margin: 2px 3px 0 0; cursor: pointer; }}
  #sidebar .bu-chip {{ display: inline-block; background: var(--chip-bu-bg); color: var(--chip-bu-color); border: 1px solid var(--chip-bu-border); padding: 1px 6px; border-radius: 3px; font-size: 10.5px; margin: 2px 3px 0 0; cursor: pointer; }}
  #sidebar .empty {{ color: var(--text-muted); font-style: italic; font-size: 13px; text-align: center; padding: 30px 0; }}
  #sidebar ul.simple-list {{ margin: 4px 0 4px 18px; padding: 0; font-size: 12px; }}
  #sidebar ul.simple-list li {{ margin: 2px 0; }}
  .legend {{ position: absolute; top: 60px; left: 16px; z-index: 10; background: var(--legend-bg); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; font-size: 11px; max-width: 280px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 5px 0; cursor: pointer; user-select: none; padding: 2px 4px; border-radius: 3px; }}
  .legend-item:hover {{ background: rgba(127, 127, 127, 0.12); }}
  .legend-item input[type=checkbox] {{ margin: 0; cursor: pointer; accent-color: #6a8aa8; }}
  .legend-item.dimmed {{ opacity: 0.4; }}
  .legend-item.disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .legend-sq {{ width: 10px; height: 10px; flex-shrink: 0; }}
  .legend-hex {{ width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 8px solid; flex-shrink: 0; }}
  .legend h4 {{ margin: 0 0 6px 0; font-size: 11px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
  .legend-row-buttons {{ display: flex; gap: 6px; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border); }}
  .legend-row-buttons button {{ flex: 1; font-size: 10.5px; padding: 3px 6px; background: var(--btn-bg); color: var(--text); border: 1px solid var(--btn-border); border-radius: 3px; cursor: pointer; }}
  .legend-row-buttons button:hover {{ background: var(--btn-bg-hover); }}
  .legend-skeleton-row {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); padding: 6px 4px 2px; user-select: none; }}
  .legend-skeleton-row label {{ font-size: 11px; color: var(--text); display: flex; align-items: center; gap: 6px; cursor: pointer; }}
  #empty-hint {{ position: absolute; top: 70px; left: 240px; z-index: 20; background: var(--print-tip-bg); border: 2px dashed #6a8aa8; border-radius: 10px; padding: 12px 16px; font-size: 13px; color: var(--text); pointer-events: none; display: none; max-width: 280px; text-align: center; box-shadow: 0 6px 30px rgba(0,0,0,0.4); }}
  #empty-hint .hint-arrow {{ position: absolute; left: -56px; top: 10px; width: 60px; height: 40px; }}
  #empty-hint.shown {{ display: block; }}
</style>
</head>
<body>
<div id="app">
  <div id="graph-wrap">
    <div id="graph"></div>
    <div id="header">
      <div class="title">📊 {title}</div>
      <div class="stats">{stats}</div>
    </div>
    <div class="legend">
      <h4>Типы узлов</h4>
      <div id="filter-list"></div>
      <div class="legend-row-buttons">
        <button id="filter-all">Все</button>
        <button id="filter-none">Никто</button>
        <button id="filter-invert">Инверт.</button>
      </div>
      <div class="legend-skeleton-row">
        <label><input type="checkbox" id="filter-skeleton"> 🦴 Скелет (только связанные)</label>
      </div>
    </div>
    <div id="empty-hint">
      <svg class="hint-arrow" viewBox="0 0 70 50" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrowHead" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L9,3 z" fill="#6a8aa8"/>
          </marker>
        </defs>
        <path d="M65,25 Q40,5 5,25" stroke="#6a8aa8" stroke-width="2.5" fill="none" marker-end="url(#arrowHead)"/>
      </svg>
      Выберите тип отражаемых связей (узлов)
    </div>
    <div id="controls">
      <input type="text" id="search" placeholder="Поиск по номеру или наименованию...">
      <button class="btn" id="btn-fit">Вписать</button>
      <button class="btn" id="btn-physics">Физика: ВКЛ</button>
      <button class="btn" id="btn-hierarchical">Иерархия</button>
      <button class="btn" id="btn-theme" title="Переключить тему">🌙 Тема</button>
      <button class="btn" id="btn-print" title="Распечатать">🖨 Распечатать</button>
      <button class="btn" id="btn-export-jpg" title="Сохранить JPG (8000×5657, A4)">💾 JPG</button>
    </div>
  </div>
  <div id="resizer" title="Перетащите, чтобы изменить ширину панели"></div>
  <div id="sidebar">
    <div class="empty">Кликните на узел графа, чтобы увидеть атрибуты объекта</div>
  </div>
</div>

<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const FILTER_GROUPS = {filter_groups_json};

function buildGeometryShape(geom, baseSize) {{
  if (!geom || !geom.points_normalized) return null;
  const pts = geom.points_normalized;
  const maxAbs = pts.reduce((m, p) => Math.max(m, Math.abs(p[0]), Math.abs(p[1])), 0) || 1;
  const r = baseSize;
  const ptsScaled = pts.map(p => [
    Math.round((p[0] / maxAbs) * r),
    Math.round((-p[1] / maxAbs) * r)
  ]);
  const points = ptsScaled.map(p => p.join(',')).join(' ');
  return points;
}}

function svgIconForNode(n) {{
  const geom = n.geometry;
  if (!geom) return null;
  const colors = n.color;
  const size = Math.max(20, n.size || 22);
  const stroke = colors.border;
  const fill = colors.bg;
  const r = size;
  const w = r * 2.4;
  const h = r * 2.4;
  const cx = w / 2;
  const cy = h / 2;
  const pts = geom.points_normalized;
  const maxAbs = pts.reduce((m, p) => Math.max(m, Math.abs(p[0]), Math.abs(p[1])), 0) || 1;
  const polyPoints = pts.map(p => {{
    const x = cx + (p[0] / maxAbs) * r;
    const y = cy - (p[1] / maxAbs) * r;
    return x.toFixed(1) + ',' + y.toFixed(1);
  }}).join(' ');
  let bricks = '';
  if (n.deregistered) {{
    const bw = r * 0.85;
    const bh = r * 0.55;
    bricks = `<circle cx="${{cx}}" cy="${{cy}}" r="${{r*0.65}}" fill="#cc1f1f" stroke="#ffffff" stroke-width="2"/>` +
             `<rect x="${{cx - bw/2}}" y="${{cy - bh/2}}" width="${{bw}}" height="${{bh}}" fill="#ffffff" rx="2"/>`;
  }}
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${{w}}' height='${{h}}' viewBox='0 0 ${{w}} ${{h}}'>` +
              `<polygon points='${{polyPoints}}' fill='${{fill}}' stroke='${{stroke}}' stroke-width='2' stroke-linejoin='round'/>` +
              bricks +
              `</svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}}

function svgBrickIcon(n) {{
  if (!n.deregistered) return null;
  const size = Math.max(20, n.size || 22);
  const colors = n.color;
  const r = size;
  const w = r * 2.4;
  const h = r * 2.4;
  const cx = w / 2;
  const cy = h / 2;
  let shapeSvg = '';
  const shape = n.shape || 'dot';
  if (shape === 'square') {{
    shapeSvg = `<rect x="${{cx - r}}" y="${{cy - r}}" width="${{2*r}}" height="${{2*r}}" fill="${{colors.bg}}" stroke="${{colors.border}}" stroke-width="2"/>`;
  }} else if (shape === 'diamond') {{
    shapeSvg = `<polygon points="${{cx}},${{cy-r}} ${{cx+r}},${{cy}} ${{cx}},${{cy+r}} ${{cx-r}},${{cy}}" fill="${{colors.bg}}" stroke="${{colors.border}}" stroke-width="2"/>`;
  }} else if (shape === 'triangle') {{
    shapeSvg = `<polygon points="${{cx}},${{cy-r}} ${{cx+r*0.9}},${{cy+r*0.7}} ${{cx-r*0.9}},${{cy+r*0.7}}" fill="${{colors.bg}}" stroke="${{colors.border}}" stroke-width="2"/>`;
  }} else {{
    shapeSvg = `<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="${{colors.bg}}" stroke="${{colors.border}}" stroke-width="2"/>`;
  }}
  const bw = r * 0.85;
  const bh = r * 0.55;
  const bricks = `<circle cx="${{cx}}" cy="${{cy}}" r="${{r*0.65}}" fill="#cc1f1f" stroke="#ffffff" stroke-width="2"/>` +
                 `<rect x="${{cx - bw/2}}" y="${{cy - bh/2}}" width="${{bw}}" height="${{bh}}" fill="#ffffff" rx="2"/>`;
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${{w}}' height='${{h}}' viewBox='0 0 ${{w}} ${{h}}'>${{shapeSvg}}${{bricks}}</svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}}

const NODE_FONT_SIZE = 13;
const EDGE_FONT_SIZE = 11;
const NODE_FONT_FACE = 'Segoe UI, Arial, sans-serif';

const visNodes = RAW_NODES.map(n => {{
  const base = {{
    id: n.id,
    label: n.label,
    shape: n.shape,
    size: n.size,
    color: {{
      background: n.color.bg,
      border: n.color.border,
      highlight: {{ background: n.color.bg, border: '#ffffff' }},
      hover: {{ background: n.color.bg, border: '#ffffff' }}
    }},
    font: {{
      color: n.color.font || '#1a1a1d',
      size: NODE_FONT_SIZE,
      face: NODE_FONT_FACE,
      bold: false,
      strokeWidth: 3,
      strokeColor: '#ffffff',
      multi: false
    }},
    borderWidth: n.kind === 'category' ? 2 : 1.8,
    borderWidthSelected: 3.5,
    title: n.tooltip,
    _kind: n.kind,
    _type: n.type,
    _attrs: n.attrs,
    _deregistered: !!n.deregistered,
    _geometry: n.geometry || null
  }};
  if (n.geometry) {{
    const url = svgIconForNode(n);
    if (url) {{
      base.shape = 'image';
      base.image = url;
      base.size = Math.max(20, (n.size || 22) * 1.4);
    }}
  }} else if (n.deregistered) {{
    const url = svgBrickIcon(n);
    if (url) {{
      base.shape = 'image';
      base.image = url;
      base.size = Math.max(20, (n.size || 22) * 1.4);
    }}
  }}
  return base;
}});

const visEdges = RAW_EDGES.map((e, idx) => ({{
  id: 'e' + idx,
  from: e.from,
  to: e.to,
  label: e.label,
  color: {{ color: e.color, highlight: '#ffffff', hover: '#ffffff' }},
  dashes: e.dashes,
  arrows: e.kind === 'category' ? '' : 'to',
  width: e.kind === 'category' ? 0.8 : 1.4,
  font: {{ color: '#a0a0a8', size: EDGE_FONT_SIZE, strokeWidth: 3, strokeColor: '#1a1a1d', face: NODE_FONT_FACE, background: 'rgba(0,0,0,0)', align: 'middle' }},
  smooth: {{ type: 'continuous', roundness: 0.2 }},
  _kind: e.kind
}}));

const nodesDS = new vis.DataSet(visNodes);
const edgesDS = new vis.DataSet(visEdges);

const container = document.getElementById('graph');
const data = {{ nodes: nodesDS, edges: edgesDS }};

const PHYSICS_DEFAULT = {{
  enabled: true,
  barnesHut: {{ gravitationalConstant: -9000, centralGravity: 0.12, springLength: 140, springConstant: 0.03, damping: 0.3, avoidOverlap: 0.5 }},
  stabilization: {{ iterations: 300, fit: true }}
}};

const options = {{
  physics: PHYSICS_DEFAULT,
  interaction: {{ hover: true, tooltipDelay: 200, navigationButtons: false, keyboard: true, multiselect: false }},
  edges: {{ selectionWidth: 2, hoverWidth: 0.5 }},
  layout: {{ improvedLayout: true }}
}};
const network = new vis.Network(container, data, options);

const sidebar = document.getElementById('sidebar');

function escapeHtml(s) {{
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

function isCadastralNumber(s) {{
  return /^\d{{1,2}}:\d{{1,2}}:\d{{1,7}}:\d+(?:\/\d+)?$/.test(String(s));
}}

function isBeneficiaryKey(s) {{
  return typeof s === 'string' && (s.startsWith('legal::') || s.startsWith('person::') || s.startsWith('bu::'));
}}

function humanizeBeneficiaryKey(s) {{
  if (!s) return '';
  if (s.startsWith('legal::ogrn::')) return 'Юрлицо; ОГРН: ' + s.slice('legal::ogrn::'.length);
  if (s.startsWith('legal::inn::')) return 'Юрлицо; ИНН: ' + s.slice('legal::inn::'.length);
  if (s.startsWith('legal::name::')) return 'Юрлицо (по наименованию)';
  if (s.startsWith('person::founder::')) return 'Физлицо (учредитель)';
  if (s.startsWith('person::')) return 'Физлицо';
  if (s.startsWith('bu::')) return 'Бизнес-единица';
  return s;
}}

function renderInlineBlock(obj) {{
  if (!obj || typeof obj !== 'object') return escapeHtml(obj);
  let html_ = '<div class="inline-block">';
  for (const [k, v] of Object.entries(obj)) {{
    if (v === null || v === undefined || v === '') continue;
    html_ += '<div class="inline-row"><span class="ikey">' + escapeHtml(k) + ':</span> <span class="ival">' + renderInlineValue(v) + '</span></div>';
  }}
  html_ += '</div>';
  return html_;
}}

function renderInlineValue(v) {{
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) {{
    if (v.length === 0) return '—';
    if (v.every(x => typeof x !== 'object' || x === null)) {{
      return v.map(x => isCadastralNumber(x) ? '<span class="cn">' + escapeHtml(x) + '</span>' : escapeHtml(x)).join(', ');
    }}
    return v.map(x => renderInlineBlock(x)).join('');
  }}
  if (typeof v === 'object') return renderInlineBlock(v);
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  if (isCadastralNumber(v)) return '<span class="cn">' + escapeHtml(v) + '</span>';
  return escapeHtml(v);
}}

function renderValue(v, contextKey) {{
  if (v === null || v === undefined) return '';
  if (contextKey === 'Бенефициар (ключ)' && typeof v === 'string') {{
    return escapeHtml(humanizeBeneficiaryKey(v));
  }}
  if (Array.isArray(v)) {{
    if (v.length === 0) return '<span style="color:#707078">—</span>';
    if (v.every(x => typeof x !== 'object' || x === null)) {{
      return '<ul class="simple-list">' + v.map(x => '<li>' + (isCadastralNumber(x) ? '<span class="cn">' + escapeHtml(x) + '</span>' : escapeHtml(x)) + '</li>').join('') + '</ul>';
    }}
    return v.map(x => renderInlineBlock(x)).join('');
  }}
  if (typeof v === 'object') return renderInlineBlock(v);
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  if (isCadastralNumber(v)) return '<span class="cn">' + escapeHtml(v) + '</span>';
  return escapeHtml(v);
}}

function renderSources(srcs) {{
  if (!Array.isArray(srcs) || srcs.length === 0) return '';
  return srcs.map(s => {{
    const label = (s && (s['файл'] || s.id)) || JSON.stringify(s);
    const kind = s && s['тип'] ? s['тип'] : '';
    return '<span class="src-chip" title="' + escapeHtml(kind) + '">' + escapeHtml(label) + '</span>';
  }}).join('');
}}

function renderBeneficiaryChips(benefs) {{
  if (!Array.isArray(benefs) || benefs.length === 0) return '';
  return benefs.map(b => {{
    const name = b['наименование'] || '?';
    const inn = b['ИНН'] ? ' · ИНН ' + b['ИНН'] : '';
    const k = b['ключ'] || '';
    return '<span class="benef-chip" data-bkey="' + escapeHtml(k) + '" title="' + escapeHtml(b['тип'] || '') + '">' + escapeHtml(name + inn) + '</span>';
  }}).join('');
}}

function renderBusinessUnitChips(units) {{
  if (!Array.isArray(units) || units.length === 0) return '';
  return units.map(b => {{
    const name = b['наименование'] || '?';
    const kpp = b['КПП'] ? ' · КПП ' + b['КПП'] : '';
    const k = b['ключ'] || '';
    return '<span class="bu-chip" data-bukey="' + escapeHtml(k) + '">' + escapeHtml(name + kpp) + '</span>';
  }}).join('');
}}

const BU_HIDDEN_KEYS = new Set(['Ключ', 'Совпадение адреса, %']);

function renderNode(node) {{
  const attrs = node._attrs || {{}};
  const isCategory = node._kind === 'category';
  const isBU = node._kind === 'business_unit';

  let html_ = '';
  html_ += '<h2>' + escapeHtml(String(node.label).replace(/\n/g, ' · ')) + '</h2>';
  html_ += '<div class="subtitle">' + escapeHtml(node._type) + (node._kind === 'stub' ? ' · нет атрибутов' : '') + (node._deregistered ? ' · СНЯТ С УЧЁТА' : '') + '</div>';

  const badgeBg = node.color.background;
  const lightBg = ['#7fc97f','#fdae6b','#9ecae1','#bcbddc','#d9d9d9','#e8e8e8','#6baed6','#f8a5a5'].includes(badgeBg);
  html_ += '<span class="type-badge" style="background:' + badgeBg + '; color:' + (lightBg ? '#1a1a1d' : '#ffffff') + '">' + escapeHtml(isCategory ? 'категория' : node._type) + '</span>';

  const flatRows = [];
  const relatedGroups = {{}};
  const rightsList = [];
  const encumbrancesList = [];
  const beneficiariesEmbedded = [];
  const businessUnitsEmbedded = [];
  const foundersIn = [];
  const foundersOut = [];
  let sources = [];
  let licences = null;

  for (const [k, v] of Object.entries(attrs)) {{
    if (isBU && BU_HIDDEN_KEYS.has(k)) continue;
    if (k === 'Связанные объекты' && v && typeof v === 'object' && !Array.isArray(v)) {{
      for (const [group, list] of Object.entries(v)) {{
        if (Array.isArray(list)) relatedGroups[group] = list;
        else flatRows.push([group, list]);
      }}
    }} else if (k === 'Права' && Array.isArray(v)) {{
      rightsList.push(...v);
    }} else if (k === 'Обременения' && Array.isArray(v)) {{
      encumbrancesList.push(...v);
    }} else if (k === 'Источники данных' && Array.isArray(v)) {{
      sources = v;
    }} else if (k === 'Источники' && Array.isArray(v)) {{
      sources = v;
    }} else if (k === 'Бенефициары' && Array.isArray(v)) {{
      beneficiariesEmbedded.push(...v);
    }} else if (k === 'Бизнес-единицы' && Array.isArray(v)) {{
      businessUnitsEmbedded.push(...v);
    }} else if (k === 'Учредители (связи)' && Array.isArray(v)) {{
      foundersIn.push(...v);
    }} else if (k === 'Является учредителем' && Array.isArray(v)) {{
      foundersOut.push(...v);
    }} else if (k === 'Лицензии' && Array.isArray(v)) {{
      licences = v;
    }} else if (k.startsWith('_')) {{
      continue;
    }} else {{
      flatRows.push([k, v]);
    }}
  }}

  if (flatRows.length > 0) {{
    html_ += '<table>';
    for (const [k, v] of flatRows) {{
      html_ += '<tr><th>' + escapeHtml(k) + '</th><td>' + renderValue(v, k) + '</td></tr>';
    }}
    html_ += '</table>';
  }}

  if (beneficiariesEmbedded.length > 0) {{
    html_ += '<div class="group"><h3>Бенефициары (' + beneficiariesEmbedded.length + ')</h3>' + renderBeneficiaryChips(beneficiariesEmbedded) + '</div>';
  }}

  if (businessUnitsEmbedded.length > 0) {{
    html_ += '<div class="group"><h3>Бизнес-единицы (' + businessUnitsEmbedded.length + ')</h3>' + renderBusinessUnitChips(businessUnitsEmbedded) + '</div>';
  }}

  if (foundersIn.length > 0) {{
    html_ += '<div class="group"><h3>Учредители (' + foundersIn.length + ')</h3>';
    for (const f of foundersIn) {{
      const name = f['наименование'] || '?';
      const share = f['доля_процент'] ? ' · доля ' + f['доля_процент'] + '%' : '';
      html_ += '<span class="benef-chip" data-bkey="' + escapeHtml(f['ключ'] || '') + '">' + escapeHtml(name + share) + '</span>';
    }}
    html_ += '</div>';
  }}

  if (foundersOut.length > 0) {{
    html_ += '<div class="group"><h3>Является учредителем (' + foundersOut.length + ')</h3>';
    for (const f of foundersOut) {{
      const name = f['наименование'] || '?';
      const share = f['доля_процент'] ? ' · доля ' + f['доля_процент'] + '%' : '';
      html_ += '<span class="benef-chip" data-bkey="' + escapeHtml(f['ключ'] || '') + '">' + escapeHtml(name + share) + '</span>';
    }}
    html_ += '</div>';
  }}

  for (const [group, list] of Object.entries(relatedGroups)) {{
    html_ += '<div class="group"><h3>' + escapeHtml(group) + ' (' + list.length + ')</h3>';
    for (const cn of list) {{
      html_ += '<div class="related-item" data-cn="' + escapeHtml(cn) + '">' + escapeHtml(cn) + '</div>';
    }}
    html_ += '</div>';
  }}

  if (rightsList.length > 0) {{
    html_ += '<div class="group"><h3>Права (' + rightsList.length + ')</h3>';
    for (const r of rightsList) {{
      const head = escapeHtml((r['Вид права'] || 'Право') + (r['Номер регистрации'] ? ' № ' + r['Номер регистрации'] : ''));
      const date = r['Дата регистрации'] || '';
      html_ += '<div class="right-card">';
      html_ += '<div class="head">' + head + '</div>';
      if (date) html_ += '<div class="meta">' + escapeHtml(date) + '</div>';
      if (r['Реквизиты выписки']) {{
        html_ += '<div class="meta" style="margin-top:5px"><strong>Реквизиты выписки</strong></div>' + renderInlineBlock(r['Реквизиты выписки']);
      }}
      if (r['Реквизиты свидетельства']) {{
        html_ += '<div class="meta" style="margin-top:5px"><strong>Реквизиты свидетельства</strong></div>' + renderInlineBlock(r['Реквизиты свидетельства']);
      }}
      if (r['Документ-основание']) {{
        html_ += '<div class="meta" style="margin-top:4px"><em>Основание:</em> ' + escapeHtml(String(r['Документ-основание']).slice(0,300)) + '</div>';
      }}
      if (r['Бенефициары']) html_ += '<div style="margin-top:5px">' + renderBeneficiaryChips(r['Бенефициары']) + '</div>';
      if (r['Источники']) html_ += '<div style="margin-top:4px">' + renderSources(r['Источники']) + '</div>';
      html_ += '</div>';
    }}
    html_ += '</div>';
  }}

  if (encumbrancesList.length > 0) {{
    html_ += '<div class="group"><h3>Обременения (' + encumbrancesList.length + ')</h3>';
    for (const e of encumbrancesList) {{
      const head = escapeHtml((e['Вид обременения'] || 'Обременение') + (e['Номер регистрации'] ? ' № ' + e['Номер регистрации'] : ''));
      const basis = e['Документ-основание'] || e['Описание'] || '';
      html_ += '<div class="enc-card">';
      html_ += '<div class="head">' + head + '</div>';
      if (e['Дата регистрации']) html_ += '<div class="meta">' + escapeHtml(e['Дата регистрации']) + '</div>';
      if (basis) html_ += '<div class="meta" style="margin-top:3px"><em>Основание:</em> ' + escapeHtml(String(basis).slice(0,300)) + '</div>';
      if (e['Реквизиты выписки']) {{
        html_ += '<div class="meta" style="margin-top:5px"><strong>Реквизиты выписки</strong></div>' + renderInlineBlock(e['Реквизиты выписки']);
      }}
      if (e['Бенефициары']) html_ += '<div style="margin-top:5px">' + renderBeneficiaryChips(e['Бенефициары']) + '</div>';
      if (e['Источники']) html_ += '<div style="margin-top:4px">' + renderSources(e['Источники']) + '</div>';
      html_ += '</div>';
    }}
    html_ += '</div>';
  }}

  if (licences !== null) {{
    html_ += '<div class="group"><h3>Лицензии (' + licences.length + ')</h3>';
    for (const lic of licences) html_ += renderInlineBlock(lic);
    html_ += '</div>';
  }}

  if (sources.length > 0) {{
    html_ += '<div class="group"><h3>Источники данных</h3>' + renderSources(sources) + '</div>';
  }}

  sidebar.innerHTML = html_;

  sidebar.querySelectorAll('.related-item').forEach(el => {{
    el.addEventListener('click', () => {{
      const cn = el.getAttribute('data-cn');
      if (nodesDS.get(cn)) {{
        network.selectNodes([cn]);
        network.focus(cn, {{ scale: 1.2, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
        showNodeById(cn);
      }}
    }});
  }});
  sidebar.querySelectorAll('.benef-chip').forEach(el => {{
    el.addEventListener('click', () => {{
      const bk = el.getAttribute('data-bkey');
      if (nodesDS.get(bk)) {{
        network.selectNodes([bk]);
        network.focus(bk, {{ scale: 1.2, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
        showNodeById(bk);
      }}
    }});
  }});
  sidebar.querySelectorAll('.bu-chip').forEach(el => {{
    el.addEventListener('click', () => {{
      const bk = el.getAttribute('data-bukey');
      if (nodesDS.get(bk)) {{
        network.selectNodes([bk]);
        network.focus(bk, {{ scale: 1.2, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
        showNodeById(bk);
      }}
    }});
  }});
}}

function showNodeById(id) {{
  const node = nodesDS.get(id);
  if (node) renderNode(node);
}}

network.on('selectNode', (params) => {{
  if (params.nodes.length > 0) showNodeById(params.nodes[0]);
  if (typeof window.__isSkeletonOn === 'function' && window.__isSkeletonOn()) {{
    window.__applyFilters();
  }}
}});
network.on('deselectNode', () => {{
  sidebar.innerHTML = '<div class="empty">Кликните на узел графа, чтобы увидеть атрибуты объекта</div>';
  if (typeof window.__isSkeletonOn === 'function' && window.__isSkeletonOn()) {{
    window.__applyFilters();
  }}
}});

document.getElementById('btn-fit').addEventListener('click', () => {{
  network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
}});

let physicsEnabled = true;
document.getElementById('btn-physics').addEventListener('click', (e) => {{
  physicsEnabled = !physicsEnabled;
  network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
  e.target.textContent = 'Физика: ' + (physicsEnabled ? 'ВКЛ' : 'ВЫКЛ');
}});

let hierarchicalOn = false;
let preHierarchyPositions = null;

const HIERARCHY_GROUPS = [
  {{ key: 'beneficiaries',  types: [], kinds: ['beneficiary'] }},
  {{ key: 'encumbrances',   types: [], kinds: ['enc'] }},
  {{ key: 'rights',         types: [], kinds: ['right'] }},
  {{ key: 'business_units', types: [], kinds: ['business_unit'] }},
  {{ key: 'equipment',      types: [], kinds: ['equipment'] }},
  {{ key: 'levels',         types: [], kinds: ['level'] }},
  {{ key: 'premises',       types: ['Помещение'], kinds: [], includeStub: true }},
  {{ key: 'construction',   types: ['Сооружение'], kinds: [] }},
  {{ key: 'building',       types: ['Здание'], kinds: [] }},
  {{ key: 'uncompleted',    types: ['Объект незавершенного строительства'], kinds: [] }},
  {{ key: 'land_parts',     types: [], kinds: [], typePrefix: 'Часть' }},
  {{ key: 'land',           types: ['Земельный участок', 'Единое землепользование'], kinds: [] }},
];

function classifyForHierarchy(n) {{
  if (n._kind === 'category') return null;
  for (let i = 0; i < HIERARCHY_GROUPS.length; i++) {{
    const g = HIERARCHY_GROUPS[i];
    if (g.kinds.includes(n._kind)) return i;
    if (g.types.includes(n._type)) return i;
    if (g.typePrefix && n._type && n._type.indexOf(g.typePrefix) === 0) return i;
    if (g.includeStub && n._kind === 'stub') return i;
  }}
  return null;
}}

function extractDateForSort(n) {{
  const a = n._attrs || {{}};
  const dateFields = [
    'Дата постановки на учёт', 'Дата постановки на учет', 'Дата регистрации',
    'Дата присвоения', 'На учете с', 'Дата выдачи',
    'Дата начала', 'Дата кадастровой стоимости', 'Дата обновления'
  ];
  let best = null;
  for (const f of dateFields) {{
    const v = a[f];
    if (!v) continue;
    const m = String(v).match(/(\d{{4}})[-.](\d{{1,2}})[-.](\d{{1,2}})|(\d{{1,2}})[.\/-](\d{{1,2}})[.\/-](\d{{4}})/);
    if (m) {{
      let y, mo, d;
      if (m[1]) {{ y = +m[1]; mo = +m[2]; d = +m[3]; }}
      else {{ y = +m[6]; mo = +m[5]; d = +m[4]; }}
      const t = new Date(y, mo - 1, d).getTime();
      if (!isNaN(t) && (best === null || t < best)) best = t;
    }}
  }}
  return best === null ? Number.MAX_SAFE_INTEGER : best;
}}

function computeHierarchyLayout() {{
  const visibleNodes = nodesDS.get().filter(n => !n.hidden);
  const visibleSet = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = edgesDS.get().filter(e => !e.hidden && visibleSet.has(e.from) && visibleSet.has(e.to));

  const byGroup = HIERARCHY_GROUPS.map(() => []);
  const categories = [];
  visibleNodes.forEach(n => {{
    if (n._kind === 'category') {{ categories.push(n); return; }}
    const g = classifyForHierarchy(n);
    if (g !== null) byGroup[g].push(n);
  }});

  byGroup.forEach(group => {{
    group.sort((a, b) => extractDateForSort(a) - extractDateForSort(b));
  }});

  const NODE_W = 150;
  const NODE_H = 70;
  const ROW_GAP = 50;
  const GROUP_GAP = 120;
  const MAX_COLS = 12;

  const adj = {{}};
  visibleEdges.forEach(e => {{
    (adj[e.from] = adj[e.from] || []).push(e.to);
    (adj[e.to] = adj[e.to] || []).push(e.from);
  }});

  const nodeToGroup = new Map();
  byGroup.forEach((group, gi) => group.forEach(n => nodeToGroup.set(n.id, gi)));

  const finalPositions = [];
  const groupYBase = [];
  let yCursor = 0;

  for (let gi = 0; gi < byGroup.length; gi++) {{
    const group = byGroup[gi];
    if (group.length === 0) {{
      groupYBase.push(yCursor);
      continue;
    }}
    const cols = Math.min(MAX_COLS, group.length);
    const rows = Math.ceil(group.length / cols);
    const layoutH = rows * (NODE_H + ROW_GAP);
    groupYBase.push(yCursor);

    if (gi > 0) {{
      const widths = [];
      for (let r = 0; r < rows; r++) widths.push(0);
      const placed = group.map((n, i) => {{
        const row = Math.floor(i / cols);
        const col = i % cols;
        const x = (col - (cols - 1) / 2) * NODE_W;
        const y = yCursor + row * (NODE_H + ROW_GAP);
        return {{ id: n.id, x, y, row, col }};
      }});

      placed.sort((a, b) => {{
        const neighA = (adj[a.id] || []).filter(id => nodeToGroup.get(id) !== undefined && nodeToGroup.get(id) > gi);
        const neighB = (adj[b.id] || []).filter(id => nodeToGroup.get(id) !== undefined && nodeToGroup.get(id) > gi);
        let avgXA = 0, avgXB = 0;
        neighA.forEach(id => {{ const pp = finalPositions.find(fp => fp.id === id); if (pp) avgXA += pp.x; }});
        neighB.forEach(id => {{ const pp = finalPositions.find(fp => fp.id === id); if (pp) avgXB += pp.x; }});
        if (neighA.length) avgXA /= neighA.length;
        if (neighB.length) avgXB /= neighB.length;
        return avgXA - avgXB;
      }});

      placed.forEach((p, i) => {{
        const row = Math.floor(i / cols);
        const col = i % cols;
        p.x = (col - (cols - 1) / 2) * NODE_W;
        p.y = yCursor + row * (NODE_H + ROW_GAP);
        p.row = row; p.col = col;
      }});

      placed.forEach(p => finalPositions.push({{ id: p.id, x: p.x, y: p.y, _group: gi, _row: p.row, _col: p.col }}));
    }} else {{
      group.forEach((n, i) => {{
        const row = Math.floor(i / cols);
        const col = i % cols;
        finalPositions.push({{
          id: n.id,
          x: (col - (cols - 1) / 2) * NODE_W,
          y: yCursor + row * (NODE_H + ROW_GAP),
          _group: gi, _row: row, _col: col
        }});
      }});
    }}
    yCursor += layoutH + GROUP_GAP;
  }}

  const SUBROW_OFFSET = 22;
  finalPositions.forEach(p => {{
    const node = visibleNodes.find(n => n.id === p.id);
    if (!node) return;
    const sameGroupNeighbors = (adj[p.id] || []).filter(id => {{
      const g = nodeToGroup.get(id);
      return g === p._group;
    }});
    if (sameGroupNeighbors.length > 0) {{
      p.y += SUBROW_OFFSET;
    }}
  }});

  const totalSpan = yCursor;
  finalPositions.forEach(p => {{ p.y = p.y - totalSpan / 2; }});

  let minXused = Infinity, maxXused = -Infinity;
  finalPositions.forEach(p => {{
    if (p.x < minXused) minXused = p.x;
    if (p.x > maxXused) maxXused = p.x;
  }});
  if (!isFinite(minXused)) {{ minXused = -200; maxXused = 200; }}

  categories.forEach((c, idx) => {{
    finalPositions.push({{
      id: c.id,
      x: maxXused + 250 + (idx % 3) * 130,
      y: Math.floor(idx / 3) * 90 - 200
    }});
  }});

  return finalPositions;
}}

document.getElementById('btn-hierarchical').addEventListener('click', (e) => {{
  hierarchicalOn = !hierarchicalOn;
  e.target.classList.toggle('active', hierarchicalOn);
  if (hierarchicalOn) {{
    preHierarchyPositions = network.getPositions();
    network.setOptions({{
      layout: {{ hierarchical: {{ enabled: false }} }},
      physics: {{ enabled: false }}
    }});
    document.getElementById('btn-physics').textContent = 'Физика: ВЫКЛ';
    physicsEnabled = false;

    const positions = computeHierarchyLayout();
    const upd = positions.map(p => ({{ id: p.id, x: p.x, y: p.y, fixed: {{ x: false, y: false }} }}));
    nodesDS.update(upd);
    setTimeout(() => {{
      network.fit({{ animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
    }}, 300);
  }} else {{
    if (preHierarchyPositions) {{
      const upd = visNodes.map(n => {{
        const p = preHierarchyPositions[n.id];
        return {{ id: n.id, x: p ? p.x : (Math.random() - 0.5) * 800, y: p ? p.y : (Math.random() - 0.5) * 800, fixed: {{ x: false, y: false }} }};
      }});
      nodesDS.update(upd);
    }} else {{
      const updates = visNodes.map(n => ({{
        id: n.id,
        x: (Math.random() - 0.5) * 800,
        y: (Math.random() - 0.5) * 800,
        fixed: {{ x: false, y: false }}
      }}));
      nodesDS.update(updates);
    }}
    network.setOptions({{
      layout: {{ hierarchical: {{ enabled: false }} }},
      physics: PHYSICS_DEFAULT
    }});
    document.getElementById('btn-physics').textContent = 'Физика: ВКЛ';
    physicsEnabled = true;
    setTimeout(() => network.fit({{ animation: {{ duration: 500 }} }}), 800);
  }}
}});

document.getElementById('search').addEventListener('input', (e) => {{
  const q = e.target.value.trim().toLowerCase();
  if (!q) return;
  const matches = visNodes.filter(n =>
    String(n.id).toLowerCase().includes(q) ||
    String(n.label).toLowerCase().includes(q)
  );
  if (matches.length === 1) {{
    network.selectNodes([matches[0].id]);
    network.focus(matches[0].id, {{ scale: 1.5, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
    showNodeById(matches[0].id);
  }}
}});

network.once('stabilizationIterationsDone', () => {{ network.fit(); }});

// ── ekcelo-graph-protocol v1: pre-selection через postMessage + location.hash ──
(function(){{
  var pending = null, ready = false;
  function apply(id){{
    if (!id) return;
    if (!ready) {{ pending = id; return; }}
    try {{
      network.selectNodes([id]);
      network.focus(id, {{ scale: 1.2, animation: true }});
    }} catch (e) {{}}
  }}
  // (ii) location.hash на старте — fallback при прямом открытии файла
  try {{
    var m = (location.hash || '').match(/(?:^#|&)node=([^&]+)/);
    if (m) pending = decodeURIComponent(m[1]);
  }} catch (e) {{}}
  // (i) postMessage — основной канал от viewer'а
  window.addEventListener('message', function(ev){{
    var d = ev && ev.data;
    if (!d || d.type !== 'ekcelo.graph.select') return;
    apply(String(d.nodeId || ''));
  }});
  // применить отложенный nodeId после стабилизации vis-network
  network.once('stabilizationIterationsDone', function(){{
    ready = true;
    if (pending) {{ var p = pending; pending = null; apply(p); }}
  }});
}})();

function brightness(hex) {{
  const m = /^#?([a-f\d]{{2}})([a-f\d]{{2}})([a-f\d]{{2}})$/i.exec(hex || '');
  if (!m) return 128;
  return 0.299*parseInt(m[1],16) + 0.587*parseInt(m[2],16) + 0.114*parseInt(m[3],16);
}}

function pickFontColor(bgHex, isLight) {{
  const b = brightness(bgHex);
  if (isLight) {{
    return b > 160 ? '#0a0a0d' : '#ffffff';
  }} else {{
    return b > 160 ? '#0a0a0d' : '#ffffff';
  }}
}}

function pickStrokeColor(fontColor) {{
  return brightness(fontColor) > 128 ? '#000000' : '#ffffff';
}}

(function themeToggle() {{
  const btn = document.getElementById('btn-theme');
  let isLight = false;
  function applyTheme() {{
    if (isLight) document.body.classList.add('theme-light');
    else document.body.classList.remove('theme-light');
    btn.textContent = isLight ? '☀ Тема' : '🌙 Тема';

    const edgeFontColor = isLight ? '#1a1a1d' : '#ffffff';
    const edgeFontStroke = isLight ? '#ffffff' : '#0a0a0d';
    const highlightBorder = isLight ? '#000000' : '#ffff66';

    const nUpd = visNodes.map(n => {{
      const bg = (n.color && n.color.background) || '#cccccc';
      const fontColor = pickFontColor(bg, isLight);
      const strokeColor = pickStrokeColor(fontColor);
      return {{
        id: n.id,
        color: {{
          background: bg,
          border: n.color.border,
          highlight: {{ background: bg, border: highlightBorder }},
          hover: {{ background: bg, border: highlightBorder }}
        }},
        font: {{
          color: fontColor,
          size: NODE_FONT_SIZE, face: NODE_FONT_FACE, bold: false, multi: false,
          strokeWidth: 3,
          strokeColor: strokeColor
        }}
      }};
    }});
    const eUpd = visEdges.map(e => ({{
      id: e.id,
      color: {{ color: e._origColor || (e.color && e.color.color), highlight: highlightBorder, hover: highlightBorder }},
      font: {{ color: edgeFontColor, size: EDGE_FONT_SIZE, strokeWidth: 3, strokeColor: edgeFontStroke, face: NODE_FONT_FACE, background: 'rgba(0,0,0,0)', align: 'middle' }}
    }}));
    nodesDS.update(nUpd);
    edgesDS.update(eUpd);
  }}
  visNodes.forEach(n => {{ if (!n._origFontColor) n._origFontColor = (n.font && n.font.color); }});
  visEdges.forEach(e => {{ if (!e._origColor) e._origColor = (e.color && e.color.color); }});
  applyTheme();
  btn.addEventListener('click', () => {{
    isLight = !isLight;
    applyTheme();
  }});
}})();


(function() {{
  const resizer = document.getElementById('resizer');
  const sidebarEl = document.getElementById('sidebar');
  let dragging = false, startX = 0, startWidth = 0;
  resizer.addEventListener('mousedown', (e) => {{
    dragging = true;
    resizer.classList.add('active');
    startX = e.clientX;
    startWidth = sidebarEl.getBoundingClientRect().width;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }});
  document.addEventListener('mousemove', (e) => {{
    if (!dragging) return;
    const dx = startX - e.clientX;
    const newWidth = Math.max(280, Math.min(window.innerWidth - 250, startWidth + dx));
    sidebarEl.style.width = newWidth + 'px';
    if (typeof network !== 'undefined' && network.redraw) network.redraw();
  }});
  document.addEventListener('mouseup', () => {{
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }});
}})();

(function buildFilterUI() {{
  const list = document.getElementById('filter-list');
  const filterState = {{}};
  let skeletonOn = false;
  let savedFilterState = null;

  const CAT_NAME_TO_KEY = {{
    "Земельные участки": "land",
    "Части ЗУ": "land_parts",
    "Здания": "building",
    "Сооружения": "construction",
    "Помещения": "premises",
    "Объекты незавершенного строительства": "uncompleted",
    "Права": "rights",
    "Обременения": "encumbrances",
    "Бенефициары": "beneficiaries",
    "Бизнес-единицы": "business_units",
    "Уровни": "levels",
    "Оборудование": "equipment"
  }};

  function nodeFilterKey(node) {{
    const k = node._kind;
    const t = node._type;
    if (k === 'category') {{
      if (filterState['categories'] === false) return 'categories';
      const catName = (node.id || '').replace('cat::', '');
      const linkedKey = CAT_NAME_TO_KEY[catName];
      if (linkedKey && filterState[linkedKey] === false) return linkedKey;
      return 'categories';
    }}
    if (k === 'object' || k === 'stub') {{
      if (t && t.indexOf('Часть') === 0) return 'land_parts';
      if (t === 'Земельный участок' || t === 'Единое землепользование') return 'land';
      if (t === 'Здание') return 'building';
      if (t === 'Сооружение') return 'construction';
      if (t === 'Помещение') return 'premises';
      if (t === 'Объект незавершенного строительства') return 'uncompleted';
      if (k === 'stub') return 'premises';
      return null;
    }}
    if (k === 'right') return 'rights';
    if (k === 'enc') return 'encumbrances';
    if (k === 'beneficiary') return 'beneficiaries';
    if (k === 'business_unit') return 'business_units';
    if (k === 'level') return 'levels';
    if (k === 'equipment') return 'equipment';
    return null;
  }}

  function nodeIdToObj() {{
    const m = {{}};
    visNodes.forEach(n => {{ m[n.id] = n; }});
    return m;
  }}

  function isConnectorNode(node) {{
    const k = node._kind;
    return k === 'right' || k === 'enc' || k === 'business_unit' || k === 'category';
  }}

  function applyFilters() {{
    let effectiveHidden = new Set();
    if (skeletonOn) {{
      const visibleByFilter = new Set();
      visNodes.forEach(n => {{
        const fk = nodeFilterKey(n);
        if (n._kind === 'category') return;
        if (!fk || filterState[fk] !== false) visibleByFilter.add(n.id);
      }});

      const adj = {{}};
      const adjDirected = {{ out: {{}}, inc: {{}} }};
      visEdges.forEach(e => {{
        (adj[e.from] = adj[e.from] || new Set()).add(e.to);
        (adj[e.to] = adj[e.to] || new Set()).add(e.from);
        (adjDirected.out[e.from] = adjDirected.out[e.from] || new Set()).add(e.to);
        (adjDirected.inc[e.to] = adjDirected.inc[e.to] || new Set()).add(e.from);
      }});
      const idMap = nodeIdToObj();

      let skeletonVisible = new Set();

      const selected = (typeof network !== 'undefined' && network.getSelectedNodes) ? network.getSelectedNodes() : [];
      const focusNode = selected && selected.length > 0 ? selected[0] : null;

      if (focusNode && visibleByFilter.has(focusNode)) {{
        skeletonVisible.add(focusNode);
        const queue = [focusNode];
        while (queue.length > 0) {{
          const cur = queue.shift();
          const ups = adjDirected.inc[cur] || new Set();
          ups.forEach(p => {{
            if (visibleByFilter.has(p) && !skeletonVisible.has(p)) {{
              skeletonVisible.add(p);
              queue.push(p);
            }}
          }});
        }}
        const q2 = [focusNode];
        while (q2.length > 0) {{
          const cur = q2.shift();
          const dws = adjDirected.out[cur] || new Set();
          dws.forEach(p => {{
            if (visibleByFilter.has(p) && !skeletonVisible.has(p)) {{
              skeletonVisible.add(p);
              q2.push(p);
            }}
          }});
        }}
      }} else {{
        const allowedConnectors = new Set();
        visNodes.forEach(n => {{
          if (n._kind === 'category') return;
          if (!isConnectorNode(n)) return;
          const fk = nodeFilterKey(n);
          if (fk && filterState[fk] === false) return;
          const neigh = adj[n.id] || new Set();
          let nonConnectorCount = 0;
          neigh.forEach(nid => {{
            const nn = idMap[nid];
            if (!nn) return;
            if (nn._kind === 'category') return;
            if (!visibleByFilter.has(nid)) return;
            nonConnectorCount += 1;
          }});
          if (nonConnectorCount >= 2) allowedConnectors.add(n.id);
        }});

        visNodes.forEach(n => {{
          if (n._kind === 'category') return;
          if (n._kind === 'stub') return;
          if (!visibleByFilter.has(n.id)) return;
          if (isConnectorNode(n)) {{
            if (allowedConnectors.has(n.id)) skeletonVisible.add(n.id);
            return;
          }}
          const neigh = adj[n.id] || new Set();
          let connected = false;
          neigh.forEach(nid => {{
            const nn = idMap[nid];
            if (!nn) return;
            if (nn._kind === 'category') return;
            if (nn._kind === 'stub') return;
            if (!visibleByFilter.has(nid)) return;
            if (isConnectorNode(nn) && !allowedConnectors.has(nid)) return;
            connected = true;
          }});
          if (connected) skeletonVisible.add(n.id);
        }});
      }}

      visNodes.forEach(n => {{
        if (!skeletonVisible.has(n.id)) effectiveHidden.add(n.id);
      }});
    }} else {{
      visNodes.forEach(n => {{
        const fk = nodeFilterKey(n);
        if (fk && filterState[fk] === false) effectiveHidden.add(n.id);
      }});
    }}

    const nodesUpdate = visNodes.map(n => {{
      const hidden = effectiveHidden.has(n.id);
      return {{ id: n.id, hidden: hidden, physics: !hidden }};
    }});
    const edgesUpdate = visEdges.map(e => {{
      const hidden = effectiveHidden.has(e.from) || effectiveHidden.has(e.to);
      return {{ id: e.id, hidden: hidden, physics: !hidden }};
    }});
    nodesDS.update(nodesUpdate);
    edgesDS.update(edgesUpdate);

    FILTER_GROUPS.forEach(g => {{
      const el = document.querySelector('.legend-item[data-key="' + g.key + '"]');
      if (el) {{
        el.classList.toggle('dimmed', filterState[g.key] === false);
        el.classList.toggle('disabled', skeletonOn);
        const cb = el.querySelector('input[type=checkbox]');
        if (cb) cb.disabled = skeletonOn;
      }}
    }});

    const visibleCount = visNodes.length - effectiveHidden.size;
    const hint = document.getElementById('empty-hint');
    if (visibleCount === 0) hint.classList.add('shown');
    else hint.classList.remove('shown');
  }}

  window.__applyFilters = applyFilters;
  window.__isSkeletonOn = () => skeletonOn;

  function legendDot(g) {{
    const dot = document.createElement('div');
    if (g.key === 'categories') {{
      dot.className = 'legend-hex';
      dot.style.borderBottomColor = g.color;
    }} else {{
      dot.className = 'legend-dot';
      dot.style.background = g.color;
    }}
    return dot;
  }}

  FILTER_GROUPS.forEach(g => {{
    filterState[g.key] = true;
    const row = document.createElement('label');
    row.className = 'legend-item';
    row.setAttribute('data-key', g.key);
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.addEventListener('change', () => {{
      filterState[g.key] = cb.checked;
      applyFilters();
    }});
    const label = document.createElement('span');
    label.textContent = g.label;
    row.appendChild(cb);
    row.appendChild(legendDot(g));
    row.appendChild(label);
    list.appendChild(row);
  }});

  document.getElementById('filter-all').addEventListener('click', () => {{
    if (skeletonOn) return;
    FILTER_GROUPS.forEach(g => {{ filterState[g.key] = true; }});
    document.querySelectorAll('.legend-item input[type=checkbox]').forEach(cb => {{ cb.checked = true; }});
    applyFilters();
  }});
  document.getElementById('filter-none').addEventListener('click', () => {{
    if (skeletonOn) return;
    FILTER_GROUPS.forEach(g => {{ filterState[g.key] = false; }});
    document.querySelectorAll('.legend-item input[type=checkbox]').forEach(cb => {{ cb.checked = false; }});
    applyFilters();
  }});
  document.getElementById('filter-invert').addEventListener('click', () => {{
    if (skeletonOn) return;
    FILTER_GROUPS.forEach(g => {{ filterState[g.key] = !filterState[g.key]; }});
    document.querySelectorAll('.legend-item input[type=checkbox]').forEach(cb => {{
      const key = cb.parentElement.getAttribute('data-key');
      cb.checked = filterState[key];
    }});
    applyFilters();
  }});

  document.getElementById('filter-skeleton').addEventListener('change', (e) => {{
    skeletonOn = e.target.checked;
    if (skeletonOn) {{
      savedFilterState = Object.assign({{}}, filterState);
      filterState['categories'] = false;
      const cbCat = document.querySelector('.legend-item[data-key="categories"] input[type=checkbox]');
      if (cbCat) cbCat.checked = false;
    }} else if (savedFilterState) {{
      Object.assign(filterState, savedFilterState);
      FILTER_GROUPS.forEach(g => {{
        const cb = document.querySelector('.legend-item[data-key="' + g.key + '"] input[type=checkbox]');
        if (cb) cb.checked = filterState[g.key] !== false;
      }});
    }}
    applyFilters();
  }});

  applyFilters();
}})();

const SOURCE_FILE_NAME = {source_name_json};
const HTML_FILE_NAME = {html_name_json};

const FOOTER_TEXT = "Сюрвей и визуализация структуры бизнес-недвижимости: ИП Бабенко Р.В. +79034389915 babenko@yandex.ru";

function drawFooter(ctx, targetWidth, targetHeight, dark) {{
  ctx.save();
  ctx.font = Math.max(11, Math.round(targetWidth / 230)) + 'px ' + NODE_FONT_FACE;
  ctx.fillStyle = dark ? '#cccccc' : '#3a3a40';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  const pad = Math.round(targetWidth / 200);
  ctx.fillText(FOOTER_TEXT, targetWidth - pad, targetHeight - pad);
  ctx.restore();
}}

function renderOffscreenNetwork(targetWidth, targetHeight, background, callback) {{
  const visibleNodeIds = nodesDS.get().filter(n => !n.hidden).map(n => n.id);
  if (visibleNodeIds.length === 0) {{
    const tmp = document.createElement('canvas');
    tmp.width = targetWidth;
    tmp.height = targetHeight;
    const ctx = tmp.getContext('2d');
    if (background) {{ ctx.fillStyle = background; ctx.fillRect(0, 0, targetWidth, targetHeight); }}
    drawFooter(ctx, targetWidth, targetHeight, false);
    callback(tmp);
    return;
  }}
  const positions = network.getPositions(visibleNodeIds);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const id of visibleNodeIds) {{
    const p = positions[id];
    if (!p) continue;
    if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
  }}
  if (!isFinite(minX)) {{ minX = -100; maxX = 100; minY = -100; maxY = 100; }}
  const PADDING_FRAC = 0.08;
  const footerReserve = Math.round(targetHeight * 0.05);
  const usableH = targetHeight - footerReserve;
  const usableW = targetWidth;
  const padX = (maxX - minX) * PADDING_FRAC + 80;
  const padY = (maxY - minY) * PADDING_FRAC + 80;
  const graphW = (maxX - minX) + 2 * padX;
  const graphH = (maxY - minY) + 2 * padY;
  const scale = Math.min(usableW / graphW, usableH / graphH);
  const offsetX = (usableW - graphW * scale) / 2 + (padX - minX) * scale;
  const offsetY = (usableH - graphH * scale) / 2 + (padY - minY) * scale;

  const tmp = document.createElement('canvas');
  tmp.width = targetWidth;
  tmp.height = targetHeight;
  const ctx = tmp.getContext('2d');
  if (background) {{ ctx.fillStyle = background; ctx.fillRect(0, 0, targetWidth, targetHeight); }}

  const project = (p) => [p.x * scale + offsetX, p.y * scale + offsetY];

  const visibleSet = new Set(visibleNodeIds);
  const idMap = {{}};
  visNodes.forEach(n => {{ idMap[n.id] = n; }});

  const isLight = document.body.classList.contains('theme-light');
  const edgeFontColor = isLight ? '#1a1a1d' : '#ffffff';
  const edgeFontStroke = isLight ? '#ffffff' : '#0a0a0d';

  edgesDS.get().forEach(e => {{
    if (e.hidden) return;
    if (!visibleSet.has(e.from) || !visibleSet.has(e.to)) return;
    const pa = positions[e.from];
    const pb = positions[e.to];
    if (!pa || !pb) return;
    const [x1, y1] = project(pa);
    const [x2, y2] = project(pb);
    ctx.save();
    ctx.strokeStyle = (e.color && e.color.color) || e._origColor || '#888';
    ctx.lineWidth = Math.max(1.2, (e.width || 1.4) * scale * 0.6 + 1);
    if (e.dashes) ctx.setLineDash([8 * scale, 6 * scale]);
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.stroke();
    if (e.arrows && (e.arrows.indexOf('to') !== -1 || e.arrows === 'to')) {{
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const ah = 10 * Math.max(1, scale * 0.8);
      ctx.setLineDash([]);
      ctx.fillStyle = (e.color && e.color.color) || e._origColor || '#888';
      ctx.beginPath();
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - ah * Math.cos(ang - 0.4), y2 - ah * Math.sin(ang - 0.4));
      ctx.lineTo(x2 - ah * Math.cos(ang + 0.4), y2 - ah * Math.sin(ang + 0.4));
      ctx.closePath();
      ctx.fill();
    }}
    if (e.label) {{
      const lx = (x1 + x2) / 2, ly = (y1 + y2) / 2;
      ctx.setLineDash([]);
      const edgeFontPx = EDGE_FONT_SIZE * scale * 0.9;
      ctx.font = edgeFontPx + 'px ' + NODE_FONT_FACE;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = Math.max(1.5, edgeFontPx * 0.28);
      ctx.strokeStyle = edgeFontStroke;
      ctx.strokeText(e.label, lx, ly);
      ctx.fillStyle = edgeFontColor;
      ctx.fillText(e.label, lx, ly);
    }}
    ctx.restore();
  }});

  nodesDS.get().forEach(n => {{
    if (n.hidden) return;
    const p = positions[n.id];
    if (!p) return;
    const [cx, cy] = project(p);
    const baseSize = n.size || 22;
    const r = Math.max(8, baseSize * scale * 0.9);
    const origN = idMap[n.id] || {{}};
    const bg = (n.color && n.color.background) || '#cccccc';
    const border = (n.color && n.color.border) || '#444';
    ctx.save();
    ctx.fillStyle = bg;
    ctx.strokeStyle = border;
    ctx.lineWidth = Math.max(1, 1.8 * scale * 0.4 + 0.6);

    const shape = n.shape || 'dot';
    if (shape === 'image' && origN.geometry && origN.geometry.points_normalized) {{
      const pts = origN.geometry.points_normalized;
      const maxAbs = pts.reduce((m, pp) => Math.max(m, Math.abs(pp[0]), Math.abs(pp[1])), 0) || 1;
      ctx.beginPath();
      pts.forEach((pp, i) => {{
        const x = cx + (pp[0] / maxAbs) * r;
        const y = cy - (pp[1] / maxAbs) * r;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }});
      ctx.closePath();
      ctx.fill(); ctx.stroke();
    }} else if (shape === 'square' || (shape === 'image' && origN._kind === 'object')) {{
      ctx.fillRect(cx - r, cy - r, 2 * r, 2 * r);
      ctx.strokeRect(cx - r, cy - r, 2 * r, 2 * r);
    }} else if (shape === 'diamond') {{
      ctx.beginPath();
      ctx.moveTo(cx, cy - r); ctx.lineTo(cx + r, cy); ctx.lineTo(cx, cy + r); ctx.lineTo(cx - r, cy);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }} else if (shape === 'triangle') {{
      ctx.beginPath();
      ctx.moveTo(cx, cy - r); ctx.lineTo(cx + r * 0.9, cy + r * 0.7); ctx.lineTo(cx - r * 0.9, cy + r * 0.7);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }} else if (shape === 'hexagon') {{
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {{
        const a = Math.PI / 3 * i - Math.PI / 6;
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }}
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }} else {{
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
    }}

    if (origN._deregistered) {{
      ctx.fillStyle = '#cc1f1f';
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = Math.max(1.5, 2 * scale * 0.5 + 0.5);
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.65, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
      const bw = r * 0.85, bh = r * 0.55;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(cx - bw / 2, cy - bh / 2, bw, bh);
    }}

    if (n.label) {{
      const labelStr = String(n.label);
      const fontPx = NODE_FONT_SIZE * scale * 0.9;
      ctx.font = fontPx + 'px ' + NODE_FONT_FACE;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const fontColor = pickFontColor(bg, isLight);
      const strokeColor = pickStrokeColor(fontColor);
      ctx.lineWidth = Math.max(2, fontPx * 0.25);
      ctx.strokeStyle = strokeColor;
      ctx.fillStyle = fontColor;
      const lines = labelStr.split('\n');
      const startY = cy + r + 4 * scale;
      lines.forEach((ln, idx) => {{
        const yy = startY + idx * fontPx * 1.05;
        ctx.strokeText(ln, cx, yy);
        ctx.fillText(ln, cx, yy);
      }});
    }}
    ctx.restore();
  }});

  drawFooter(ctx, targetWidth, targetHeight, false);
  callback(tmp);
}}

function makeSnapshotFileBase(baseName) {{
  const now = new Date();
  const pad = (x) => String(x).padStart(2, '0');
  const stamp = now.getFullYear() + pad(now.getMonth() + 1) + pad(now.getDate()) + '_' +
                pad(now.getHours()) + pad(now.getMinutes()) + pad(now.getSeconds());
  return 'to_print_' + baseName + '_' + stamp;
}}

async function copyBlobToClipboard(blob) {{
  if (!navigator.clipboard || !window.ClipboardItem) {{
    console.warn('Clipboard API недоступен в этом браузере');
    return false;
  }}
  try {{
    await navigator.clipboard.write([new ClipboardItem({{ 'image/png': blob }})]);
    return true;
  }} catch (e) {{
    console.warn('Не удалось скопировать изображение в буфер:', e);
    return false;
  }}
}}

function flashCopyToast(msg) {{
  const t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText = 'position:fixed;left:50%;bottom:80px;transform:translateX(-50%);background:rgba(40,120,80,0.94);color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 14px rgba(0,0,0,0.3);';
  document.body.appendChild(t);
  setTimeout(() => {{ if (t.parentNode) t.parentNode.removeChild(t); }}, 2200);
}}

const JPG_WIDTH = 8000;
const JPG_HEIGHT = Math.round(8000 * 210 / 297);

function copyHiresToClipboard() {{
  renderOffscreenNetwork(JPG_WIDTH, JPG_HEIGHT, '#ffffff', (hiresCanvas) => {{
    hiresCanvas.toBlob(async (blob) => {{
      if (!blob) return;
      const ok = await copyBlobToClipboard(blob);
      if (ok) flashCopyToast('📋 Граф ' + JPG_WIDTH + '×' + JPG_HEIGHT + ' скопирован в буфер обмена');
    }}, 'image/png');
  }});
}}

document.getElementById('btn-print').addEventListener('click', () => {{
  network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
  const baseName = SOURCE_FILE_NAME.replace(/\.[^.]+$/, '');
  setTimeout(() => {{
    renderOffscreenNetwork(2400, 1700, '#ffffff', (tmp) => {{
      const url = tmp.toDataURL('image/png');
      const prevTitle = document.title;
      document.title = baseName;
      const printFrame = document.createElement('iframe');
      printFrame.style.cssText = 'position:fixed;left:-99999px;width:0;height:0;border:0;';
      document.body.appendChild(printFrame);
      const doc = printFrame.contentDocument || printFrame.contentWindow.document;
      doc.open();
      doc.write('<!doctype html><html><head><title>' + baseName.replace(/[<>&"]/g, '') + '</title>' +
        '<style>@page {{ size: A4 landscape; margin: 0; }} ' +
        '@media print {{ html,body{{margin:0;padding:0;background:transparent;-webkit-print-color-adjust:exact;print-color-adjust:exact}} ' +
        'img{{display:block;width:100vw;height:100vh;object-fit:contain}} }}' +
        'html,body{{margin:0;padding:0;background:transparent}} ' +
        'img{{display:block;width:100vw;height:100vh;object-fit:contain}}</style>' +
        '</head><body><img src="' + url + '"/></body></html>');
      doc.close();
      setTimeout(() => {{
        try {{
          printFrame.contentWindow.focus();
          printFrame.contentWindow.print();
        }} catch (e) {{
          const win = window.open('', '_blank');
          if (win) {{
            win.document.open();
            win.document.write(doc.documentElement.outerHTML);
            win.document.close();
            setTimeout(() => win.print(), 300);
          }}
        }}
        setTimeout(() => {{
          document.title = prevTitle;
          if (printFrame.parentNode) printFrame.parentNode.removeChild(printFrame);
        }}, 1500);
        copyHiresToClipboard();
      }}, 600);
    }});
  }}, 1100);
}});

document.getElementById('btn-export-jpg').addEventListener('click', () => {{
  network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
  const baseName = HTML_FILE_NAME.replace(/\.[^.]+$/, '');
  setTimeout(() => {{
    renderOffscreenNetwork(JPG_WIDTH, JPG_HEIGHT, '#ffffff', (tmp) => {{
      tmp.toBlob(async (blob) => {{
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = makeSnapshotFileBase(baseName) + '.jpg';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }}, 'image/jpeg', 0.92);
      tmp.toBlob(async (pngBlob) => {{
        if (!pngBlob) return;
        const ok = await copyBlobToClipboard(pngBlob);
        if (ok) flashCopyToast('📋 Граф ' + JPG_WIDTH + '×' + JPG_HEIGHT + ' скопирован в буфер обмена');
      }}, 'image/png');
    }});
  }}, 1100);
}});
</script>
</body>
</html>
""").replace("__VIS_NETWORK_INLINE__", vis_network_inline)



def main():
    print("=== Построение графа объектов недвижимости ===\n")
    if len(sys.argv) > 1:
        path = sys.argv[1].strip().strip('"').strip("'")
    else:
        path = input("Путь к enriched_*.json: ").strip().strip('"').strip("'")
    src = Path(path)
    if not src.exists():
        print(f"[!] Файл не найден: {src}")
        sys.exit(1)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[!] Ошибка чтения JSON: {e}")
        sys.exit(1)

    # Опционально — structure_*.json от 052_make_structure_v1.py
    structure_path = ""
    if len(sys.argv) > 2:
        structure_path = sys.argv[2].strip().strip('"').strip("'")
    else:
        structure_path = input("Путь к structure_*.json (Enter — пропустить): ").strip().strip('"').strip("'")

    levels: list[dict] = []
    equipment: list[dict] = []
    bu_extra: list[dict] = []
    if structure_path:
        sp = Path(structure_path)
        if not sp.exists():
            print(f"[!] structure-файл не найден, продолжаю без него: {sp}")
        else:
            try:
                sdata = json.loads(sp.read_text(encoding="utf-8"))
                levels, equipment, bu_extra, _ = parse_structure(sdata)
                print(f"[+] structure: уровней={len(levels)} · оборудования={len(equipment)} · BU(доп.)={len(bu_extra)}")
            except Exception as e:
                print(f"[!] Ошибка чтения structure: {e}")

    objects, rights_records, encumbrances_records, beneficiaries, business_units, founder_chains = parse_input(data)
    if not objects and not rights_records and not encumbrances_records and not beneficiaries:
        print("[!] В JSON не найдено данных для построения графа")
        sys.exit(1)

    if bu_extra:
        existing_keys = {b.get("Ключ") for b in business_units}
        for bu in bu_extra:
            if bu.get("Ключ") not in existing_keys:
                business_units.append(bu)

    nodes, edges = build_graph(objects, rights_records, encumbrances_records,
                               beneficiaries, business_units, founder_chains,
                               levels=levels, equipment=equipment)

    by_type = {}
    for n in nodes:
        if n["kind"] == "object":
            by_type[n["type"]] = by_type.get(n["type"], 0) + 1

    print(f"Объектов в JSON: {sum(by_type.values())}")
    for t, c in sorted(by_type.items()):
        print(f"  · {t}: {c}")
    print(f"Прав: {len(rights_records)}")
    print(f"Обременений: {len(encumbrances_records)}")
    print(f"Бенефициаров: {len(beneficiaries)}")
    print(f"Бизнес-единиц: {len(business_units)}")
    print(f"Цепочек учредителей: {len(founder_chains)}")
    if levels:
        print(f"Уровней зданий: {len(levels)}")
    if equipment:
        print(f"Оборудования (ОС): {len(equipment)}")
    stubs = sum(1 for n in nodes if n["kind"] == "stub")
    if stubs:
        print(f"Связанных, не загруженных в JSON: {stubs}")
    print(f"Связей: {len(edges)}")

    out_path = src.with_name(f"graph_{src.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    output_html = render_html(nodes, edges, src.name, out_path.name)
    out_path.write_text(output_html, encoding="utf-8")

    # Sidecar для 08_build_kmz_v2 — контракт KMZ 2.11.0 §5/§6 (graph_node_id).
    # Имя фиксированное: 08 ищет его рядом с graph.html в _data/.
    idx_path = out_path.with_name("graph_node_index.json")
    idx_path.write_text(json.dumps(build_graph_node_index(nodes),
                                   ensure_ascii=False, indent=2,
                                   sort_keys=True),
                        encoding="utf-8")
    print(f"\n[+] Граф сохранён: {out_path}")
    print(f"[+] Sidecar-индекс для KMZ: {idx_path}")
    print(f"    Откройте файл двойным кликом в любом современном браузере (Chrome, Edge, Firefox).")
    print(f"    Для отображения графа требуется интернет (загрузка vis-network с CDN).")


if __name__ == "__main__":
    main()
