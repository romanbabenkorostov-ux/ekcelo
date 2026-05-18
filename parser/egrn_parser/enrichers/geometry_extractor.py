"""
egrn_parser/enrichers/geometry_extractor.py — извлечение геометрии из PDF/XML.

Уровни точности (ТЗ раздел 20.1):
  'egrn_pdf'     — координаты из раздела 3 PDF (Высокая)
  'egrn_xml'     — координаты из XML (Высокая)
  'manual_kml'   — ручная обводка KML (Средняя)
  'geocoded'     — геокодирование адреса (Очень низкая)

Система координат: WGS-84 (EPSG:4326) для отображения.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Паттерн координат в тексте PDF
COORD_RE = re.compile(
    r"(?:широта|lat)[:\s]+([\d.]+)[^\d]+"
    r"(?:долгота|lon|lng)[:\s]+([\d.]+)",
    re.IGNORECASE,
)

# Паттерн МСК/СК-42 координат (X Y пары через пробел/запятую)
MSK_COORD_RE = re.compile(r"(\d{6,7}[.,]\d+)\s*[,;]\s*(\d{6,7}[.,]\d+)")


def extract_geometry_from_pdf_text(text: str) -> Optional[dict]:
    """
    Попытаться извлечь координаты из текста PDF (раздел 3 — чертёж).
    Возвращает dict с ключами lat, lon или None.
    """
    m = COORD_RE.search(text)
    if m:
        try:
            lat = float(m.group(1))
            lon = float(m.group(2))
            if 35.0 < lat < 82.0 and 19.0 < lon < 190.0:  # грубая проверка — территория РФ
                return {"lat": lat, "lon": lon, "crs": "EPSG:4326", "source": "egrn_pdf"}
        except ValueError:
            pass
    return None


def build_point_geojson(lat: float, lon: float) -> str:
    """Построить GeoJSON-точку."""
    return json.dumps({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {}
    }, ensure_ascii=False)


def build_polygon_geojson(coords: list[list[float]]) -> str:
    """Построить GeoJSON-полигон из списка [lon, lat] пар."""
    if coords and coords[0] != coords[-1]:
        coords = coords + [coords[0]]  # замкнуть
    return json.dumps({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {}
    }, ensure_ascii=False)


def point_to_wkt(lat: float, lon: float) -> str:
    """Точка → WKT."""
    return f"POINT ({lon} {lat})"


def polygon_to_wkt(coords: list[list[float]]) -> str:
    """Полигон → WKT (coords в формате [[lon, lat], ...])."""
    if coords and coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    pts = " ".join(f"{c[0]} {c[1]}" for c in coords)
    return f"POLYGON (({pts}))"
