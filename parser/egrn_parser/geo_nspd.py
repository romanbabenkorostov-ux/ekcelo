"""
egrn_parser/geo_nspd.py — получение геометрии объекта по КН из ПКК/НSPD (для KMZ).

Лёгкий HTTP-путь (без Playwright): ПКК `pkk.rosreestr.ru/api/features/{layer}/{cad}`
возвращает геометрию в EPSG:3857 → репроекция в WGS84. Слои: 1 — ЗУ, 5 — ОКС/здания.

Разделение: `fetch_feature` (сеть) ↔ `parse_pkk_feature`/`_merc_to_wgs` (чистые,
тестируются офлайн). Сеть в закрытом контуре может быть недоступна — тогда фетч
вернёт None, а вызывающий (geo_kmz) разложит объект по спирали.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any, Optional

PKK_URL = "https://pkk.rosreestr.ru/api/features/{layer}/{cad}"
_R = 6378137.0                                       # радиус сферы web-mercator
LAYER_PARCEL = 1
LAYER_BUILDING = 5


def _merc_to_wgs(x: float, y: float) -> tuple[float, float]:
    """EPSG:3857 (метры) → WGS84 (lon, lat, градусы)."""
    lon = x / _R * 180.0 / math.pi
    lat = (2.0 * math.atan(math.exp(y / _R)) - math.pi / 2.0) * 180.0 / math.pi
    return (round(lon, 7), round(lat, 7))


def _ring_to_wgs(ring: list) -> list:
    return [list(_merc_to_wgs(float(p[0]), float(p[1]))) for p in ring if len(p) >= 2]


def parse_pkk_feature(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Ответ ПКК → GeoJSON WGS84 {type:'Polygon', coordinates:[...]} (внешние кольца).

    Поддерживает feature.geometry Polygon/MultiPolygon в EPSG:3857."""
    feat = (payload or {}).get("feature") or {}
    geom = feat.get("geometry") or {}
    t = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    if t == "Polygon":
        return {"type": "Polygon", "coordinates": [_ring_to_wgs(r) for r in coords]}
    if t == "MultiPolygon":
        # для KMZ берём первый полигон (внешние кольца)
        return {"type": "Polygon", "coordinates": [_ring_to_wgs(r) for r in coords[0]]}
    return None


def fetch_feature(cad: str, *, layer: int = LAYER_PARCEL, timeout: int = 20) -> Optional[dict]:
    """GET ПКК по КН → JSON. Требует исходящей сети (в закрытом контуре — None)."""
    url = PKK_URL.format(layer=layer, cad=urllib.parse.quote(cad))
    req = urllib.request.Request(url, headers={
        "Referer": "https://pkk.rosreestr.ru/", "Origin": "https://pkk.rosreestr.ru",
        "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:                                # сеть закрыта/таймаут/404 → None
        return None


def fetch_geometry(cad: str, *, layer: int = LAYER_PARCEL) -> Optional[dict]:
    """КН → GeoJSON WGS84 геометрия (ЗУ layer=1 / ОКС layer=5) или None.

    Готовая функция для geo_kmz.collect_from_db(geometry_fetcher=...)."""
    payload = fetch_feature(cad, layer=layer)
    return parse_pkk_feature(payload) if payload else None


def building_fetcher():
    """Фетчер геометрии ОКС/зданий (layer=5) для geometry_fetcher объектов."""
    return lambda cad: fetch_geometry(cad, layer=LAYER_BUILDING)
