"""
egrn_parser/exporters/html_report.py — отчёт по объекту: граф, хронология, эссе.

ЧТО ЭТО. Один самодостаточный HTML с тремя вкладками, собранный из SQLite:

  1. «Права и ограничения» — граф связей объект ↔ права ↔ правообладатели ↔
     обременения ↔ зоны, на vis-network. Форма и палитра взяты из
     `04_nspd_graph_v14.py`, чтобы два графа системы читались одинаково.
  2. «Хронология» — те же сведения, но по датам: когда объект поставлен на
     учёт, когда зарегистрированы права, когда возникли обременения, когда
     появился контур. Граф отвечает «кто с кем связан», хронология — «что за
     чем шло»; это разные вопросы, и один ответ на оба не работает.
  3. «Эссе» — текст из `essay_md`, отрисованный в HTML, с кнопкой выгрузки
     исходного `.md`.

ПОЧЕМУ ИЗ БАЗЫ, А НЕ ИЗ `enriched_*.json`. Существующий `04_nspd_graph_v14.py`
строит граф проекта из выгрузки НСПД — ему нужен пройденный конвейер 01–03.
Здесь вход другой: только что разобранные выписки, никакого проекта ещё нет.
Источник — SQLite, единственное, что к этому моменту есть.

ЧТО ГРАФ ОБЯЗАН ПОКАЗЫВАТЬ ЧЕСТНО. Право и обременение — не однородные записи,
хотя в таблице `rights` лежат рядом: одно говорит, чей объект, другое — что с
ним нельзя сделать. Поэтому у них разные категории, разные цвета и разные типы
рёбер. Слить их в «связи объекта» значит потерять ровно то, ради чего граф и
строят.

ПЕРСОНАЛЬНЫЕ ДАННЫЕ. Правообладатель-физлицо попадает в граф как «Физическое
лицо» без имени: узел нужен, чтобы видеть долевую собственность, а ФИО, СНИЛС и
паспорт в отчёте не нужны никогда. Юридические лица называются — они публичны
по ЕГРЮЛ.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Optional

from egrn_parser.exporters import essay_md

__all__ = ["build_report_data", "build_html", "export_html_report",
           "report_filename", "TEMPLATE_PATH", "VIS_VENDOR_PATH"]

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "object_report.html.j2"
VIS_VENDOR_PATH = (Path(__file__).resolve().parents[2]
                   / "vendor" / "vis-network-9.1.9.min.js")
VIS_CDN = "https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"

# Палитра — из 04_nspd_graph_v14.py. Один и тот же тип объекта обязан выглядеть
# одинаково в обоих графах системы; свои цвета здесь заводить нельзя.
TYPE_COLORS: dict[str, dict[str, str]] = {
    "Земельный участок": {"bg": "#7fc97f", "border": "#2d5a2d", "font": "#0a1f0a"},
    "Единое землепользование": {"bg": "#5fa55f", "border": "#1f4a1f", "font": "#000000"},
    "Здание": {"bg": "#fdae6b", "border": "#7a4515", "font": "#2a1505"},
    "Сооружение": {"bg": "#bcbddc", "border": "#3d3d70", "font": "#0a0a30"},
    "Помещение": {"bg": "#9ecae1", "border": "#1f4d6f", "font": "#04253b"},
    "Объект незавершенного строительства": {"bg": "#fcbba1", "border": "#7a3818", "font": "#2a0f05"},
    "Часть ЗУ": {"bg": "#d9d9d9", "border": "#5a5a5a", "font": "#202020"},
    "Право": {"bg": "#6baed6", "border": "#3182bd", "font": "#ffffff"},
    "Обременение": {"bg": "#3182bd", "border": "#08519c", "font": "#ffffff"},
    "Ограничение (ЗОУИТ)": {"bg": "#9e9ac8", "border": "#54278f", "font": "#ffffff"},
    "Бенефициар (юр.лицо)": {"bg": "#e85b5b", "border": "#a83a3a", "font": "#ffffff"},
    "Бенефициар (физ.лицо)": {"bg": "#f8a5a5", "border": "#c87575", "font": "#5a1a1a"},
    "Неизвестно": {"bg": "#e8e8e8", "border": "#a0a0a0", "font": "#606060"},
}

CATEGORY_COLORS: dict[str, dict[str, str]] = {
    "Объекты": {"bg": "#2d6a2d", "border": "#1a4a1a", "font": "#ffffff"},
    "Права": {"bg": "#08519c", "border": "#08306b", "font": "#ffffff"},
    "Обременения": {"bg": "#08306b", "border": "#041632", "font": "#ffffff"},
    "Ограничения (ЗОУИТ)": {"bg": "#54278f", "border": "#3f007d", "font": "#ffffff"},
    "Правообладатели": {"bg": "#a83a3a", "border": "#6a1a1a", "font": "#ffffff"},
    "Части объекта": {"bg": "#606060", "border": "#303030", "font": "#ffffff"},
}

EDGE_COLORS = {
    "category": {"color": "#888888", "dashes": True},
    "right": {"color": "#3182bd", "dashes": False},
    "encumbrance": {"color": "#08519c", "dashes": False},
    "restriction": {"color": "#54278f", "dashes": True},
    "holder": {"color": "#a83a3a", "dashes": False},
    "part": {"color": "#969696", "dashes": True},
    # Улучшение ↔ земля: не «часть», а две природы одного объекта недвижимости.
    "on_land": {"color": "#4a8a4a", "dashes": False},
}

OBJECT_TYPE_RU = {
    "land": "Земельный участок",
    "building": "Здание",
    "room": "Помещение",
    "construction": "Сооружение",
    "ons": "Объект незавершенного строительства",
    "parking": "Помещение",
}

_INN_RE = re.compile(r"\b\d{10}(?:\d{2})?\b")


def _rows(conn: sqlite3.Connection, sql: str, *args) -> list[tuple]:
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in _rows(conn, f'PRAGMA table_info("{table}")')}


def _num(value: Optional[float], digits: int = 1) -> Optional[str]:
    if value is None:
        return None
    text = f"{float(value):.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


# --- объекты --------------------------------------------------------------

def _objects(conn: sqlite3.Connection, cad_number: Optional[str]) -> list[dict]:
    """Карточки объектов из обеих таблиц; у каждой свой набор колонок."""
    found: dict[str, dict] = {}
    queries = (
        ("land", "SELECT cad_number, address, area, cadastral_value, "
                 "       lifecycle_status_text, registration_date, NULL, NULL, "
                 "       land_category, permitted_uses "
                 "  FROM land_objects"),
        (None, "SELECT cad_number, address, area, cadastral_value, "
               "       lifecycle_status_text, registration_date, name, purpose, "
               "       NULL, NULL "
               "  FROM building_objects"),
    )
    keys = ("cad_number", "address", "area", "cadastral_value", "status",
            "registration_date", "name", "purpose", "land_category",
            "permitted_uses")
    for default_kind, sql in queries:
        for row in _rows(conn, sql):
            item = dict(zip(keys, row))
            if cad_number and item["cad_number"] != cad_number:
                continue
            item["object_type"] = default_kind or _guess_kind(conn, item["cad_number"])
            found.setdefault(item["cad_number"], item)

    # Объект может быть известен только по геометрии — карточки ещё нет.
    for (cad,) in _rows(conn, "SELECT DISTINCT cad_number FROM egrn_contour"
                              + (" WHERE cad_number = ?" if cad_number else ""),
                        *( (cad_number,) if cad_number else () )):
        found.setdefault(cad, {"cad_number": cad, "object_type": "land"})

    for cad, item in found.items():
        row = _rows(conn, "SELECT land_layout, SUM(area_computed_sqm), MAX(accuracy_m) "
                          "  FROM egrn_contour WHERE cad_number = ? AND kind='parcel'",
                    cad)
        if row and row[0][1] is not None:
            item["land_layout"], item["contour_area"], item["accuracy_m"] = row[0]
    return sorted(found.values(), key=lambda x: x["cad_number"])


def _guess_kind(conn: sqlite3.Connection, cad: str) -> str:
    row = _rows(conn, "SELECT object_type FROM building_objects WHERE cad_number = ?", cad)
    return (row[0][0] if row and row[0][0] else "building")


# --- граф -----------------------------------------------------------------

def _holder_label(conn: sqlite3.Connection, right_id: Any,
                  beneficiary: Optional[str], inn: Optional[str]) -> tuple[str, str, str]:
    """(id узла, подпись, тип). Физлица не называются — см. преамбулу."""
    if "right_holders" in {r[0] for r in _rows(
            conn, "SELECT name FROM sqlite_master WHERE type='table'")}:
        rows = _rows(conn, "SELECT name, inn, holder_type FROM right_holders "
                           " WHERE right_id = ?", right_id)
        if rows:
            name, holder_inn, holder_type = rows[0]
            if holder_type == "individual" or not name:
                return (f"holder::fl::{right_id}", "Физическое лицо",
                        "Бенефициар (физ.лицо)")
            key = holder_inn or name
            return (f"holder::{key}", name, "Бенефициар (юр.лицо)")
    if beneficiary or inn:
        # Поле часто хранит слипшуюся строку с ИНН, ОГРН, почтой и адресом —
        # в граф идёт только имя (или ИНН, если имени нет).
        head = (beneficiary or "").split(",")[0].strip()
        found_inn = inn or (_INN_RE.search(beneficiary or "") or [None])[0]
        if head and _INN_RE.fullmatch(head):
            head = ""
        label = head or (f"ИНН {found_inn}" if found_inn else "Правообладатель")
        return (f"holder::{found_inn or label}", label, "Бенефициар (юр.лицо)")
    return ("", "", "")


def _build_graph(conn: sqlite3.Connection, objects: list[dict]) -> dict:
    """Узлы и рёбра для vis-network."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    categories: dict[str, list[str]] = {}
    zones: dict[str, dict] = {}

    def add_node(node_id: str, label: str, kind: str, type_name: str,
                 tooltip: str, attrs: dict, shape: str = "box",
                 size: int = 16) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append({
            "id": node_id, "label": label, "kind": kind, "type": type_name,
            "color": TYPE_COLORS.get(type_name, TYPE_COLORS["Неизвестно"]),
            "shape": shape, "size": size, "tooltip": tooltip, "attrs": attrs,
        })

    def add_edge(source: str, target: str, kind: str, label: str = "") -> None:
        style = EDGE_COLORS.get(kind, EDGE_COLORS["category"])
        edges.append({"from": source, "to": target, "kind": kind, "label": label,
                      "color": style["color"], "dashes": style["dashes"]})

    def in_category(category: str, node_id: str) -> None:
        categories.setdefault(category, []).append(node_id)

    right_columns = _columns(conn, "rights")

    for item in objects:
        cad = item["cad_number"]
        type_name = OBJECT_TYPE_RU.get(item.get("object_type") or "land", "Неизвестно")
        if item.get("land_layout") == "ЕЗП":
            type_name = "Единое землепользование"
        attrs = {
            "Адрес": item.get("address"),
            "Площадь, кв.м": _num(item.get("area"), 0),
            "Кадастровая стоимость, ₽": _num(item.get("cadastral_value"), 2),
            "Категория земель": item.get("land_category"),
            "Разрешённое использование": item.get("permitted_uses"),
            "Назначение": item.get("purpose"),
            "Раскладка": item.get("land_layout"),
            "Площадь по контуру, кв.м": _num(item.get("contour_area")),
            "Точность контура, м": _num(item.get("accuracy_m"), 2),
            "Статус": item.get("status"),
        }
        attrs = {k: v for k, v in attrs.items() if v}
        add_node(f"obj::{cad}", cad, "object", type_name,
                 f"{type_name}\n{cad}\n{item.get('address') or ''}".strip(),
                 attrs, shape="box", size=24)
        in_category("Объекты", f"obj::{cad}")

        # права и обременения
        columns = [c for c in ("right_id", "right_type", "right_number", "right_date",
                               "right_category", "beneficiary_name", "beneficiary_inn",
                               "basis", "share_numerator", "share_denominator")
                   if c in right_columns]
        if columns:
            for raw in _rows(conn, f"SELECT {', '.join(columns)} FROM rights "
                                   f" WHERE object_key_value = ? AND is_active = 1",
                             cad):
                right = dict(zip(columns, raw))
                category = right.get("right_category") or "right"
                is_right = category == "right"
                node_type = "Право" if is_right else "Обременение"
                node_id = f"right::{right.get('right_number') or right.get('right_id')}"
                share = None
                if right.get("share_numerator") and right.get("share_denominator"):
                    share = f"{right['share_numerator']}/{right['share_denominator']}"
                right_attrs = {
                    "Вид": right.get("right_type"),
                    "Номер регистрации": right.get("right_number"),
                    "Дата": (right.get("right_date") or "")[:10] or None,
                    "Доля": share,
                    "Основание": right.get("basis"),
                }
                add_node(node_id, right.get("right_type") or node_type, "right",
                         node_type, f"{node_type}\n{right.get('right_type') or ''}",
                         {k: v for k, v in right_attrs.items() if v},
                         shape="ellipse", size=18)
                in_category("Права" if is_right else "Обременения", node_id)
                add_edge(f"obj::{cad}", node_id,
                         "right" if is_right else "encumbrance",
                         share or "")

                holder_id, holder_label, holder_type = _holder_label(
                    conn, right.get("right_id"), right.get("beneficiary_name"),
                    right.get("beneficiary_inn"))
                if holder_id:
                    add_node(holder_id, holder_label, "holder", holder_type,
                             holder_label, {}, shape="box", size=18)
                    in_category("Правообладатели", holder_id)
                    add_edge(node_id, holder_id, "holder")

        # ЗОУИТ и прочие ограничения объекта. Узел — ОДИН НА ЗОНУ, а не на пару
        # (объект, зона): охранная зона ЛЭП 26:29-6.395 накрывает десяток
        # участков, и продублированная по объектам она превращает граф в веер
        # одинаковых ромбов, из которого не видно главного — какие участки
        # попали под одно и то же ограничение. Ключ узла — реестровый номер
        # зоны; он и есть её идентификатор в ЕГРН.
        for registry, description in _restriction_items(conn, cad):
            key = registry or _zone_fallback_key(description)
            node_id = f"zone::{key}"
            zones.setdefault(key, {
                "registry": registry, "description": description, "objects": []})
            zones[key]["objects"].append(cad)
            # Описание одной и той же зоны в разных выписках бывает разной
            # длины; оставляем самое полное — оно и есть содержание ограничения.
            if len(description) > len(zones[key]["description"]):
                zones[key]["description"] = description
            add_edge(f"obj::{cad}", node_id, "restriction")

        # части участка (ЧЗУ)
        for part_number, mnemonic, area in _rows(
                conn, "SELECT part_number, part_mnemonic, area_computed_sqm "
                      "  FROM egrn_contour WHERE cad_number = ? AND kind = 'part' "
                      " ORDER BY CAST(part_number AS INTEGER)", cad):
            node_id = f"part::{cad}::{part_number}"
            label = mnemonic or f"часть {part_number}"
            add_node(node_id, label, "part", "Часть ЗУ",
                     f"Часть участка {part_number}", {
                         "Зона": mnemonic,
                         "Площадь, кв.м": _num(area),
                     }, shape="dot", size=12)
            in_category("Части объекта", node_id)
            add_edge(f"obj::{cad}", node_id, "part")

    # Узлы зон создаются после обхода объектов: только теперь известно, сколько
    # объектов накрывает каждая и какое описание полнее.
    for key, zone in zones.items():
        node_id = f"zone::{key}"
        label = zone["registry"] or "Ограничение"
        count = len(zone["objects"])
        add_node(node_id, label, "restriction", "Ограничение (ЗОУИТ)",
                 f"{label}\nОбъектов под ограничением: {count}\n"
                 + zone["description"][:300],
                 {"Реестровый номер": zone["registry"],
                  "Объектов под ограничением": count,
                  "Объекты": ", ".join(sorted(set(zone["objects"]))),
                  "Содержание": zone["description"]},
                 # Зона, накрывающая несколько объектов, крупнее: размер здесь
                 # несёт смысл «насколько широко ограничение», а не украшение.
                 shape="diamond", size=14 + min(count, 8) * 2)
        in_category("Ограничения (ЗОУИТ)", node_id)

    # Улучшение стоит на земле — это не «часть», а вторая природа одного
    # объекта недвижимости (см. obsidian/Decisions/ADR-009). Ребро рисуется
    # только если участок тоже есть в отчёте: связь на отсутствующий узел
    # обещает данные, которых нет.
    known = {item["cad_number"] for item in objects}
    for item in objects:
        for land_cad in _land_links(conn, item["cad_number"]):
            if land_cad in known and land_cad != item["cad_number"]:
                add_edge(f"obj::{item['cad_number']}", f"obj::{land_cad}",
                         "on_land", "на участке")

    # категории — шапки групп, как в 04_nspd_graph
    for category, members in categories.items():
        node_id = f"cat::{category}"
        colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["Объекты"])
        nodes.insert(0, {
            "id": node_id, "label": category, "kind": "category", "type": category,
            "color": colors, "shape": "hexagon", "size": 20,
            "tooltip": f"Категория: {category}\nЭлементов: {len(members)}",
            "attrs": {"Элементов": len(members)},
        })
        for member in members:
            add_edge(node_id, member, "category")

    return {"nodes": nodes, "edges": edges}


def _zone_fallback_key(description: str) -> str:
    """Ключ зоны без реестрового номера.

    Такие записи в выписках есть — например, «Особые отметки» с текстом
    ограничения. Ключом становится начало текста: одинаковые формулировки из
    разных выписок схлопнутся, разные останутся раздельными. Это хуже, чем
    реестровый номер, но лучше, чем узел на каждую выписку.
    """
    return " ".join(description.split())[:60] or "без номера"


def _land_links(conn: sqlite3.Connection, cad: str) -> list[str]:
    """КН участков, на которых стоит улучшение."""
    rows = _rows(conn, "SELECT land_cad_numbers FROM building_objects "
                       " WHERE cad_number = ?", cad)
    if not rows or not rows[0][0]:
        return []
    return [c.strip() for c in re.split(r"[;,]", rows[0][0]) if c.strip()]


def _restriction_items(conn: sqlite3.Connection, cad: str) -> list[tuple[str, str]]:
    """Ограничения объекта из таблицы либо из JSON-колонки (обе схемы живы)."""
    rows = _rows(conn, "SELECT registry_number, description FROM object_restrictions "
                       " WHERE cad_number = ?", cad)
    if rows:
        return [(r[0] or "", r[1] or "") for r in rows]
    row = _rows(conn, "SELECT object_restrictions FROM land_objects "
                      " WHERE cad_number = ?", cad)
    if not row or not row[0][0]:
        return []
    try:
        payload = json.loads(row[0][0])
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [(str(x.get("registry_number") or ""), str(x.get("description") or ""))
            for x in payload if isinstance(x, dict)]


# --- хронология -----------------------------------------------------------

# Тип события → как его рисовать. Цвета те же, что у категорий графа: одно и то
# же явление не должно менять цвет при переходе между вкладками.
EVENT_STYLES = {
    "object": {"label": "Объект", "color": "#2d6a2d"},
    "right": {"label": "Право", "color": "#08519c"},
    "encumbrance": {"label": "Обременение", "color": "#08306b"},
    "restriction": {"label": "Ограничение", "color": "#54278f"},
    "extract": {"label": "Выписка", "color": "#6b5b3e"},
    "contour": {"label": "Контур", "color": "#2e8b57"},
    "conflict": {"label": "Решение о контуре", "color": "#c9a227"},
}


def _build_timeline(conn: sqlite3.Connection, objects: list[dict]) -> list[dict]:
    """События по датам: что за чем шло с объектом.

    Порядок — по дате возрастанию; события без даты выбрасываются, а не
    сваливаются в начало: «неизвестно когда» на шкале времени изображается
    только враньём.
    """
    events: list[dict] = []
    right_columns = _columns(conn, "rights")

    def add(day: Optional[str], kind: str, cad: str, title: str,
            detail: str = "") -> None:
        if not day:
            return
        events.append({"date": str(day)[:10], "kind": kind, "cad_number": cad,
                       "title": title, "detail": detail,
                       "label": EVENT_STYLES[kind]["label"],
                       "color": EVENT_STYLES[kind]["color"]})

    for item in objects:
        cad = item["cad_number"]
        add(item.get("registration_date"), "object", cad,
            "Поставлен на кадастровый учёт",
            f"{OBJECT_TYPE_RU.get(item.get('object_type') or 'land', '')}, "
            f"{_num(item.get('area'), 0) or '?'} кв.м")

        columns = [c for c in ("right_type", "right_number", "right_date",
                               "right_category", "beneficiary_name", "basis")
                   if c in right_columns]
        if columns:
            for raw in _rows(conn, f"SELECT {', '.join(columns)} FROM rights "
                                   f" WHERE object_key_value = ?", cad):
                right = dict(zip(columns, raw))
                category = right.get("right_category") or "right"
                kind = "right" if category == "right" else "encumbrance"
                detail = "; ".join(x for x in (
                    right.get("right_number"),
                    (right.get("beneficiary_name") or "").split(",")[0].strip() or None,
                    right.get("basis")) if x)
                add(right.get("right_date"), kind, cad,
                    right.get("right_type") or EVENT_STYLES[kind]["label"], detail)

        for number, day, template in _rows(
                conn, "SELECT extract_number, extract_date, extract_template "
                      "  FROM extracts WHERE cad_number = ?", cad):
            add(day, "extract", cad, f"Выписка ЕГРН {number or ''}".strip(),
                f"шаблон: {template}" if template else "")

        for day, count, area in _rows(
                conn, "SELECT extract_date, COUNT(*), SUM(area_computed_sqm) "
                      "  FROM egrn_contour WHERE cad_number = ? AND kind='parcel' "
                      " GROUP BY extract_date", cad):
            add(day, "contour", cad, "Контур из выписки",
                f"контуров {count}, {_num(area)} кв.м")

        for day in _rows(conn, "SELECT created_at FROM manual_contour "
                               " WHERE cad_number = ?", cad):
            add(day[0], "contour", cad, "Ручная обводка",
                "примерный контур, внесён человеком")

        for detected, resolved, resolution in _rows(
                conn, "SELECT detected_at, resolved_at, resolution "
                      "  FROM contour_conflict WHERE cad_number = ?", cad):
            add(detected, "conflict", cad, "В выписке появился уточнённый контур",
                "ждёт решения" if resolution == "pending" else "")
            if resolved:
                add(resolved, "conflict", cad,
                    "Принят уточнённый контур" if resolution == "use_egrn"
                    else "Оставлен исходный контур", "")

    events.sort(key=lambda e: (e["date"], e["cad_number"], e["title"]))
    return events


# --- сборка ---------------------------------------------------------------

def build_report_data(conn: sqlite3.Connection, *,
                      cad_number: Optional[str] = None,
                      generated_on: Optional[str] = None) -> dict:
    """Всё, что нужно шаблону. Ни одной строки HTML здесь нет намеренно:
    данные тестируются словарём, а вёрстка — глазами."""
    objects = _objects(conn, cad_number)
    essays = []
    for item in objects:
        text = essay_md.build_essay(conn, item["cad_number"])
        essays.append({"cad_number": item["cad_number"], "markdown": text,
                       "html": _markdown_to_html(text)})
    return {
        "generated_on": generated_on or date.today().isoformat(),
        "objects": objects,
        "graph": _build_graph(conn, objects),
        "timeline": _build_timeline(conn, objects),
        "essays": essays,
        "title": (f"Объект {cad_number}" if cad_number
                  else f"Объекты недвижимости ({len(objects)})"),
    }


_MD_INLINE = ((re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
              (re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)"), r"<em>\1</em>"),
              (re.compile(r"`(.+?)`"), r"<code>\1</code>"))


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _markdown_to_html(text: str) -> str:
    """Подмножество Markdown, которое реально порождает `essay_md`.

    Тянуть библиотеку ради заголовков, таблиц, списков и цитат незачем: эссе
    пишет этот же проект, набор конструкций в нём закрытый и известен. Если
    `essay_md` начнёт выдавать что-то ещё — сюда придётся добавить, и это
    честнее, чем молча рендерить неизвестный синтаксис как попало.
    """
    html: list[str] = []
    table: list[str] = []
    bullets: list[str] = []

    def flush_table() -> None:
        if not table:
            return
        rows = [r for r in table if not set(r.replace("|", "").strip()) <= set("-: ")]
        html.append("<table>")
        for index, row in enumerate(rows):
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            tag = "th" if index == 0 else "td"
            html.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        html.append("</table>")
        table.clear()

    def flush_bullets() -> None:
        if not bullets:
            return
        html.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
        bullets.clear()

    for raw in text.split("\n"):
        line = _escape(raw.rstrip())
        for pattern, replacement in _MD_INLINE:
            line = pattern.sub(replacement, line)
        if line.startswith("|"):
            flush_bullets()
            table.append(line)
            continue
        flush_table()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush_bullets()
        if not line.strip():
            continue
        if line.startswith("### "):
            html.append(f"<h4>{line[4:]}</h4>")
        elif line.startswith("## "):
            html.append(f"<h3>{line[3:]}</h3>")
        elif line.startswith("# "):
            html.append(f"<h2>{line[2:]}</h2>")
        elif line.startswith("&gt; "):
            html.append(f"<blockquote>{line[5:]}</blockquote>")
        else:
            html.append(f"<p>{line}</p>")
    flush_table()
    flush_bullets()
    return "\n".join(html)


def build_html(conn: sqlite3.Connection, *, cad_number: Optional[str] = None,
               generated_on: Optional[str] = None, inline_vis: bool = True) -> str:
    """Отчёт одной строкой.

    `inline_vis=True` вшивает vis-network в файл: отчёт открывают на объекте,
    где интернета может не быть, и страница, которая без сети показывает
    пустой прямоугольник вместо графа, бесполезна ровно тогда, когда нужна.
    Ценой служит вес файла — около 0,7 МБ.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_PATH.parent)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True)
    template = environment.get_template(TEMPLATE_PATH.name)

    vis_inline = ""
    vis_src = VIS_CDN
    if inline_vis and VIS_VENDOR_PATH.exists():
        vis_inline = VIS_VENDOR_PATH.read_text(encoding="utf-8")
        vis_src = ""

    data = build_report_data(conn, cad_number=cad_number, generated_on=generated_on)
    # Легенда строится по тем типам, что реально попали в граф: перечислять в
    # ней «Единое землепользование», когда в отчёте одни помещения, — значит
    # заставлять читателя искать то, чего нет.
    used_types = {node["type"] for node in data["graph"]["nodes"]
                  if node["kind"] != "category"}
    legend_types = [(name, colors) for name, colors in TYPE_COLORS.items()
                    if name in used_types]
    return template.render(vis_inline=vis_inline, vis_src=vis_src,
                           legend_types=legend_types,
                           data_json=json.dumps(data, ensure_ascii=False,
                                                sort_keys=True),
                           **data)


def report_filename(cad_number: Optional[str], day: Optional[str] = None) -> str:
    day = day or date.today().isoformat()
    if cad_number:
        return f"Отчёт_{cad_number.replace(':', '-')}_{day}.html"
    return f"Отчёт_ЕГРН_{day}.html"


def export_html_report(conn: sqlite3.Connection, out_path: Path | str,
                       **kwargs) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(conn, **kwargs), encoding="utf-8")
    return path
