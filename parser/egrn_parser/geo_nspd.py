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


# ── NSPD WFS: геометрия по КН + обнаружение ОКС в границах ЗУ ─────────────────
# WFS отдаёт GeoJSON сразу в EPSG:4326 (репроекция не нужна). Слои — из v8-парсера.
WFS_URL = "https://nspd.gov.ru/api/aeggis/v3/{id}/wfs"
NSPD_ZU_LAYERS = [36048]
NSPD_OKS_LAYERS = [36329, 36328, 36049]
CAD_FIELDS = ["cad_num", "KAD_NUM", "CAD_NUM", "kadnum", "cadnum"]


def _wfs_get(layer_id: int, *, cql: Optional[str] = None,
             bbox: Optional[tuple] = None, count: int = 50,
             timeout: int = 20) -> Optional[dict]:
    """GetFeature по слою (CQL или BBOX). Возвращает GeoJSON body или None (сеть)."""
    params = (f"SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ms:layer_{layer_id}"
              f"&outputFormat=application/json&SRSNAME=EPSG:4326&count={count}")
    if cql:
        params += "&CQL_FILTER=" + urllib.parse.quote(cql, safe="")
    if bbox:
        params += f"&BBOX={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326"
    url = WFS_URL.format(id=layer_id) + "?" + params
    req = urllib.request.Request(url, headers={
        "Referer": "https://nspd.gov.ru/map", "Origin": "https://nspd.gov.ru",
        "Accept": "application/json, */*", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _geojson_to_kmz_geom(g: dict) -> Optional[dict]:
    """GeoJSON (4326) → формат geo_kmz {type, coords}."""
    if not isinstance(g, dict) or not g.get("coordinates"):
        return None
    t = g.get("type")
    if t == "Point":
        return {"type": "Point", "coords": [g["coordinates"]]}
    if t == "Polygon":
        return {"type": "Polygon", "coords": g["coordinates"]}
    if t == "MultiPolygon":
        return {"type": "Polygon", "coords": g["coordinates"][0]}
    return None


def _feat_cad(props: dict) -> Optional[str]:
    for f in CAD_FIELDS:
        v = (props or {}).get(f)
        if v:
            return str(v)
    return None


def parse_wfs_features(body: dict) -> list[dict[str, Any]]:
    """WFS GeoJSON → [{cad, geometry{type,coords}}] (геометрия в 4326)."""
    out = []
    for ft in (body or {}).get("features") or []:
        g = _geojson_to_kmz_geom(ft.get("geometry") or {})
        if g:
            out.append({"cad": _feat_cad(ft.get("properties") or {}), "geometry": g})
    return out


def discover_buildings(parcel_polygon: Any) -> list[dict[str, Any]]:
    """Найти ОКС в границах ЗУ через NSPD-WFS (BBOX по габариту + точный фильтр
    centroid-in-polygon). Возвращает [{name(cad), geometry}]. Требует сети."""
    from egrn_parser.geo_kmz import _ring, bbox as _bbox, centroid, point_in_ring
    ring = _ring(parcel_polygon)
    if len(ring) < 3:
        return []
    minx, miny, maxx, maxy = _bbox(ring)
    seen, result = set(), []
    for lid in NSPD_OKS_LAYERS:
        body = _wfs_get(lid, bbox=(minx, miny, maxx, maxy))
        if not body:
            continue
        for f in parse_wfs_features(body):
            r = _ring(f["geometry"]["coords"])
            if not r or not point_in_ring(centroid(r), ring):
                continue                              # центр ОКС вне ЗУ
            key = f.get("cad") or str(r[0])
            if key in seen:
                continue
            seen.add(key)
            result.append({"name": f.get("cad") or "ОКС", "geometry": f["geometry"]})
    return result
