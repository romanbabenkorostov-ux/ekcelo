"""
egrn_parser/parsers/land_layout.py — классификация представления земельного
участка: ЗУ / ЕЗП / МКУ (ADR-005, шаг 1).

Различение (онтология `obsidian/Architecture/zu-ezp-mku-ontology.md`):
  • ЕЗП — есть маркер «(Единое землепользование)» ИЛИ дочерние КН (двухуровневая
    структура: главный КН + обособленные/условные участки со своими КН).
  • МКУ — ≥2 несвязных контуров при ОДНОМ КН без дочерних (контуры без своих КН,
    нумеруются :КН(1), :КН(2)).
  • ЗУ  — один контур, один КН (базовый тип).

Чистая функция (без БД) — подключается в land-ingest / 01b_ingest_contours.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Sequence

ЗУ, ЕЗП, МКУ = "ЗУ", "ЕЗП", "МКУ"

_EZP_MARKER = "единое землепользование"
_RE_CAD = re.compile(r"\d{2}:\d{2}:\d+:\d+")
# Секция перечня дочерних КН ЕЗП в Росреестр-выписке.
_RE_EZP_CHILDREN = re.compile(
    r"входящих\s+в\s+единое\s+землепользование\s*:?\s*(.+?)(?:\n\s*\n|Получатель|$)",
    re.IGNORECASE | re.DOTALL)


def detect_land_layout(
    *,
    cad_number: Optional[str] = None,
    name: Optional[str] = None,
    contours_count: Optional[int] = None,
    child_cads: Optional[Sequence[str]] = None,
) -> str:
    """Вернуть тип представления участка: 'ЗУ' | 'ЕЗП' | 'МКУ'.

    Приоритет: маркер/дочерние КН → ЕЗП; иначе ≥2 контуров → МКУ; иначе ЗУ.
    """
    text = f"{name or ''} {cad_number or ''}".lower()
    if _EZP_MARKER in text or (child_cads and len(child_cads) > 0):
        return ЕЗП
    if contours_count is not None and contours_count >= 2:
        return МКУ
    return ЗУ


def detect_from_land_object(obj: dict) -> str:
    """Классифицировать по записи land_objects-подобного dict.

    Учитывает поля: cad_number, name, nested_objects (дочерние КН),
    contours_count / полигонов / geom (число контуров).
    """
    child = obj.get("nested_objects") or obj.get("child_cads")
    if isinstance(child, dict):
        child = list(child.values())
    n = (obj.get("contours_count")
         or obj.get("полигонов")
         or _geojson_polygon_count(obj.get("geom") or obj.get("geojson")))
    return detect_land_layout(
        cad_number=obj.get("cad_number"),
        name=obj.get("name"),
        contours_count=n,
        child_cads=child if isinstance(child, (list, tuple)) else None,
    )


def _geojson_polygon_count(geom) -> Optional[int]:
    """Число полигонов в GeoJSON (Polygon → 1, MultiPolygon → len)."""
    if not isinstance(geom, dict):
        return None
    t = geom.get("type")
    if t == "Polygon":
        return 1
    if t == "MultiPolygon":
        coords = geom.get("coordinates") or []
        return len(coords)
    return None


# ── Извлечение ЕЗП из Росреестр-выписки (текст) ──────────────────────────────
def normalize_cad(cad: Optional[str]) -> Optional[str]:
    """Убрать пометку «(Единое землепользование)» и пробелы из КН."""
    if not cad:
        return None
    m = _RE_CAD.search(cad)
    return m.group(0) if m else cad.strip()


def extract_ezp_children(text: str) -> list[str]:
    """Дочерние КН из секции «…обособленных (условных) участков, входящих в
    единое землепользование: КН, КН, … .» Пустой список — если секции нет."""
    m = _RE_EZP_CHILDREN.search(text)
    if not m:
        return []
    return _RE_CAD.findall(m.group(1))


def extract_main_cad(text: str) -> Optional[str]:
    """Главный КН объекта. Предпочитаем КН с пометкой «(Единое землепользование)»."""
    m = re.search(r"(\d{2}:\d{2}:\d+:\d+)\s*\(\s*[Ее]диное землепользование", text)
    if m:
        return m.group(1)
    m2 = _RE_CAD.search(text)
    return m2.group(0) if m2 else None


def parse_land_extract(text: str) -> dict:
    """Классифицировать Росреестр-выписку по земле → {cad_number, layout, children}.

    Для ЕЗП заполняет children (дочерние КН). Для МКУ/ЗУ children пуст
    (контуры — из геометрии, см. detect_from_land_object).
    """
    children = extract_ezp_children(text)
    cad = extract_main_cad(text)
    layout = detect_land_layout(cad_number=cad, name=text[:2000], child_cads=children)
    return {"cad_number": cad, "layout": layout, "children": children}


# ── МКУ: контуры из геометрии (MultiPolygon → отдельные полигоны) ────────────
def split_geometry_contours(geom: Optional[dict]) -> list[dict]:
    """GeoJSON геометрии → список контуров {geom_geojson(Polygon)}.

    Polygon → 1 контур; MultiPolygon → по контуру на полигон (для МКУ/ЕЗП).
    contour_cad НЕ заполняется (у контура МКУ нет своего КН)."""
    if not isinstance(geom, dict):
        return []
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    if t == "Polygon":
        return [{"geom_geojson": json.dumps(geom, ensure_ascii=False)}]
    if t == "MultiPolygon":
        return [{"geom_geojson": json.dumps(
                    {"type": "Polygon", "coordinates": poly}, ensure_ascii=False)}
                for poly in coords]
    return []
