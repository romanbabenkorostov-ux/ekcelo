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
import math
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


# ── Геометрия: площадь/центроид контура (локальная равноугольная проекция) ────
def _lonlat_to_local_meters(lon, lat, lon0, lat0):
    """Локальная плоская проекция от центроида (точность ±0.1% до ~10 км)."""
    dx = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
    dy = (lat - lat0) * 110540.0
    return dx, dy


def _ring_centroid_wgs84(ring) -> tuple[float, float]:
    """Центроид кольца (lon, lat) по формуле планарного полигона."""
    if len(ring) < 3:
        return (ring[0][0], ring[0][1]) if ring else (0.0, 0.0)
    A = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        cross = x1 * y2 - x2 * y1
        A += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    A *= 0.5
    if abs(A) < 1e-12:
        return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)
    return (cx / (6.0 * A), cy / (6.0 * A))


def _ring_area_sqm_local(ring_local_m) -> float:
    """Площадь кольца в м² (shoelace по локальным метрам)."""
    n = len(ring_local_m)
    if n < 3:
        return 0.0
    s = sum(ring_local_m[i][0] * ring_local_m[(i + 1) % n][1]
            - ring_local_m[(i + 1) % n][0] * ring_local_m[i][1] for i in range(n))
    return abs(s) * 0.5


def polygon_area_centroid(polygon_coords) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Polygon coords ([outer, hole1, …] в WGS84) → (area_sqm, lon, lat).

    Площадь = внешнее кольцо − дыры; центроид — внешнее кольцо. None при пустом."""
    if not polygon_coords or not polygon_coords[0]:
        return (None, None, None)
    outer = polygon_coords[0]
    lon0, lat0 = _ring_centroid_wgs84(outer)
    def proj(ring):
        return [_lonlat_to_local_meters(p[0], p[1], lon0, lat0) for p in ring]
    area = _ring_area_sqm_local(proj(outer))
    for hole in polygon_coords[1:]:
        area -= _ring_area_sqm_local(proj(hole))
    return (round(area, 2), round(lon0, 7), round(lat0, 7))


# ── МКУ: контуры из геометрии (MultiPolygon → отдельные полигоны) ────────────
def split_geometry_contours(geom: Optional[dict]) -> list[dict]:
    """GeoJSON геометрии → список контуров {geom_geojson(Polygon), area_sqm,
    centroid_lon, centroid_lat}.

    Polygon → 1 контур; MultiPolygon → по контуру на полигон (для МКУ/ЕЗП).
    contour_cad НЕ заполняется (у контура МКУ нет своего КН). Площадь/центроид
    считаются из геометрии (локальная проекция)."""
    if not isinstance(geom, dict):
        return []
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    if t == "Polygon":
        polys = [coords]
    elif t == "MultiPolygon":
        polys = coords
    else:
        return []
    out = []
    for poly in polys:
        area, lon, lat = polygon_area_centroid(poly)
        out.append({"geom_geojson": json.dumps(
                        {"type": "Polygon", "coordinates": poly}, ensure_ascii=False),
                    "area_sqm": area, "centroid_lon": lon, "centroid_lat": lat,
                    "geom_source": "geometry"})
    return out
