"""
egrn_parser/geo_kmz.py — экспорт объектов в пределах земельных участков в KMZ.

Правило (задача заказчика):
  • у объекта есть контур/геометрия → наносим контур (Polygon) или точку (Point);
  • у объекта НЕТ геометрии → ставим точку, разложенную ПО СПИРАЛИ внутри
    соответствующего ЗУ (равномерно от центра наружу, не выходя за границу участка).

Без внешних зависимостей: KML пишется как XML, KMZ — zip с `doc.kml`. Ядро
(`build_kmz`, `spiral_points`) работает на чистых структурах; источник данных
(БД/файлы) подключается отдельно — см. `collect_from_db`.

Структура входа `parcels`:
  [{"cad": "23:15:...", "polygon": [[lon,lat], ...] | None,
    "objects": [{"name": str, "geometry": {"type":"Polygon|Point","coords":[...]} | None}]}]
"""
from __future__ import annotations

import math
import xml.sax.saxutils as _xml
import zipfile
from pathlib import Path
from typing import Any, Optional

Coord = tuple[float, float]


# ── геометрия ────────────────────────────────────────────────────────────────
def _ring(polygon: Any) -> list[Coord]:
    """Внешнее кольцо: [[lon,lat],…] из Polygon-coords (рингов) или плоского кольца."""
    if not polygon:
        return []
    ring = polygon[0] if (isinstance(polygon[0], (list, tuple))
                          and polygon[0] and isinstance(polygon[0][0], (list, tuple))) else polygon
    return [(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]


def centroid(ring: list[Coord]) -> Coord:
    n = len(ring)
    if n == 0:
        return (0.0, 0.0)
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)


def bbox(ring: list[Coord]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_ring(pt: Coord, ring: list[Coord]) -> bool:
    """Ray-casting: точка внутри кольца."""
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1):
            inside = not inside
    return inside


def spiral_points(ring: list[Coord], count: int, *, turns: float = 3.0,
                  margin: float = 0.85) -> list[Coord]:
    """`count` точек по архимедовой спирали внутри полигона `ring`.

    Центр — центроид; радиус растёт ∝ sqrt(i) (равномерно по площади). Точки вне
    полигона подтягиваются к центру до попадания внутрь (margin — доля габарита)."""
    if count <= 0 or len(ring) < 3:
        return []
    cx, cy = centroid(ring)
    minx, miny, maxx, maxy = bbox(ring)
    rx = (maxx - minx) / 2.0 * margin
    ry = (maxy - miny) / 2.0 * margin
    out: list[Coord] = []
    for i in range(count):
        t = (i + 0.5) / count                       # 0..1
        theta = turns * 2.0 * math.pi * t
        rad = math.sqrt(t)                          # равномерно по площади
        dx, dy = rad * math.cos(theta), rad * math.sin(theta)
        # подтягиваем внутрь полигона (до 6 шагов уменьшения радиуса)
        s = 1.0
        for _ in range(6):
            pt = (cx + dx * rx * s, cy + dy * ry * s)
            if point_in_ring(pt, ring):
                break
            s *= 0.7
        out.append((cx + dx * rx * s, cy + dy * ry * s))
    return out


# ── KML/KMZ ──────────────────────────────────────────────────────────────────
def _coords_str(ring: list[Coord]) -> str:
    pts = list(ring)
    if pts and pts[0] != pts[-1]:
        pts = pts + [pts[0]]                         # замкнуть кольцо
    return " ".join(f"{lon},{lat},0" for lon, lat in pts)


def _placemark_polygon(name: str, ring: list[Coord], style: str) -> str:
    return (f"<Placemark><name>{_xml.escape(name)}</name><styleUrl>#{style}</styleUrl>"
            f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_coords_str(ring)}"
            f"</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")


def _placemark_point(name: str, pt: Coord, style: str) -> str:
    return (f"<Placemark><name>{_xml.escape(name)}</name><styleUrl>#{style}</styleUrl>"
            f"<Point><coordinates>{pt[0]},{pt[1]},0</coordinates></Point></Placemark>")


_STYLES = """
<Style id="parcel"><LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
<PolyStyle><fill>0</fill></PolyStyle></Style>
<Style id="objpoly"><LineStyle><color>ff00aa00</color><width>2</width></LineStyle>
<PolyStyle><color>5500aa00</color></PolyStyle></Style>
<Style id="objpoint"><IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>
<Style id="spiral"><IconStyle><color>ff00ffff</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>
""".strip()


def build_kml(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Собрать KML по списку участков. Возвращает {kml, stats}."""
    folders = []
    n_contour = n_spiral = n_parcels_geo = 0
    for p in parcels:
        cad = str(p.get("cad", "?"))
        ring = _ring(p.get("polygon"))
        body = []
        if ring:
            body.append(_placemark_polygon(f"ЗУ {cad}", ring, "parcel"))
            n_parcels_geo += 1
        objs = p.get("objects") or []
        no_geom = []
        for o in objs:
            g = o.get("geometry")
            nm = str(o.get("name", "объект"))
            if g and g.get("coords"):
                if g.get("type") == "Point":
                    c = g["coords"][0]
                    body.append(_placemark_point(nm, (float(c[0]), float(c[1])), "objpoint"))
                else:
                    body.append(_placemark_polygon(nm, _ring(g["coords"]), "objpoly"))
                n_contour += 1
            else:
                no_geom.append(nm)
        # объекты без геометрии → точки по спирали внутри ЗУ
        if no_geom and ring:
            for nm, pt in zip(no_geom, spiral_points(ring, len(no_geom))):
                body.append(_placemark_point(nm, pt, "spiral"))
                n_spiral += 1
        elif no_geom:
            # нет границы ЗУ → спираль ставить негде (нужна геометрия участка)
            for nm in no_geom:
                body.append(f"<!-- объект без геометрии и без границы ЗУ: {_xml.escape(nm)} -->")
        folders.append(f"<Folder><name>ЗУ {_xml.escape(cad)}</name>{''.join(body)}</Folder>")

    kml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f'{_STYLES}{"".join(folders)}</Document></kml>')
    return {"kml": kml, "stats": {"parcels": len(parcels), "parcels_with_geom": n_parcels_geo,
                                  "objects_with_contour": n_contour, "objects_spiral": n_spiral}}


def build_kmz(out_path: str | Path, parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Собрать KMZ-файл. Возвращает {path, stats}."""
    res = build_kml(parcels)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", res["kml"])
    return {"path": str(out), "stats": res["stats"]}


# Режимы «что считать объектом внутри ЗУ» (выбор пользователя; умолч. — все три):
#   linked (а) — linked_objects(located_on) + building_objects.parent_cad
#   agro   (в) — §6-объекты: agro_parcel с land_cad = ЗУ (насаждения/точки оценки)
#   geo    (г) — любой объект с геометрией, чей центроид внутри полигона ЗУ
DEFAULT_MODES = ("linked", "agro", "geo")
_MODE_ALIAS = {"а": "linked", "a": "linked", "в": "agro", "v": "agro", "г": "geo", "g": "geo"}


def _norm_modes(modes) -> set[str]:
    return {_MODE_ALIAS.get(m.strip().lower(), m.strip().lower()) for m in modes}


# Источники СТРОЕНИЙ (выбор пользователя; умолч. порядок 2→1→3):
#   nspd (2) — обнаружение ОКС в границах ЗУ через NSPD-WFS (geo_nspd.discover_buildings)
#   db   (1) — из БД по режимам modes (linked/agro/geo)
#   cads (3) — переданный список КН строений (геометрия по КН из NSPD/БД)
DEFAULT_BUILDING_SOURCES = ("nspd", "db", "cads")


def collect_from_db(conn, cad_numbers: list[str], *, modes=DEFAULT_MODES,
                    geometry_fetcher: Optional[Any] = None,
                    building_sources=DEFAULT_BUILDING_SOURCES,
                    building_discovery: Optional[Any] = None,
                    extra_building_cads: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Собрать структуру `parcels` из БД.

    Граница ЗУ — из `land_contours`; при отсутствии и наличии `geometry_fetcher`
    (NSPD) — тянется и кэшируется. Объекты внутри — по `modes` (linked/agro/geo).
    Геометрия объекта — из его контуров; при отсутствии и наличии fetcher — из NSPD;
    иначе → точка по спирали.
    """
    import json as _json
    modes = _norm_modes(modes)

    def _has(t):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (t,)).fetchone() is not None

    def _poly(cad: str) -> Optional[list]:
        if _has("land_contours"):
            for (gj,) in conn.execute(
                "SELECT geom_geojson FROM land_contours WHERE parent_cad=? "
                "AND geom_geojson IS NOT NULL ORDER BY contour_no", (cad,)):
                try:
                    g = _json.loads(gj)
                    if g.get("type") == "Polygon":
                        return g["coordinates"]
                except (ValueError, TypeError):
                    continue
        return None

    def _fetch(cad: str) -> Optional[list]:
        """NSPD-фетч геометрии (2в) + кэш в land_contours."""
        if not geometry_fetcher:
            return None
        try:
            g = geometry_fetcher(cad)
        except Exception:
            return None
        if not g:
            return None
        coords = g["coordinates"] if isinstance(g, dict) and "coordinates" in g else g
        if _has("land_contours"):
            conn.execute("INSERT OR IGNORE INTO land_contours(parent_cad, contour_no, "
                         "geom_geojson, geom_source) VALUES(?,?,?,?)",
                         (cad, 1, _json.dumps({"type": "Polygon", "coordinates": coords},
                                              ensure_ascii=False), "nspd"))
            conn.commit()
        return coords

    def _from_db(cad: str, poly) -> list[dict[str, Any]]:
        """Строения/объекты из БД по режимам modes (источник 1: linked/agro/geo)."""
        names: list[str] = []
        geo_objs: list[dict[str, Any]] = []
        if "linked" in modes:
            if _has("linked_objects"):
                names += [r[0] for r in conn.execute(
                    "SELECT linked_cad_number FROM linked_objects WHERE primary_cad_number=?", (cad,))]
            if _has("building_objects"):
                names += [r[0] for r in conn.execute(
                    "SELECT cad_number FROM building_objects WHERE parent_cad_number=?", (cad,))]
        agro_pts = []
        if "agro" in modes and _has("agro_parcel"):
            for code, gj in conn.execute(
                "SELECT parcel_code, geom_geojson FROM agro_parcel WHERE land_cad=?", (cad,)):
                g = None
                if gj:
                    try:
                        gg = _json.loads(gj); g = {"type": gg.get("type", "Polygon"),
                                                   "coords": gg.get("coordinates")}
                    except (ValueError, TypeError):
                        g = None
                agro_pts.append({"name": f"агро:{code}", "geometry": g})
        if "geo" in modes and poly and _has("land_contours"):
            ring0 = _ring(poly)
            for ocad, gj in conn.execute(
                "SELECT DISTINCT parent_cad, geom_geojson FROM land_contours "
                "WHERE parent_cad<>? AND geom_geojson IS NOT NULL", (cad,)):
                try:
                    gg = _json.loads(gj)
                    r = _ring(gg.get("coordinates"))
                    if r and point_in_ring(centroid(r), ring0):
                        geo_objs.append({"name": ocad,
                                         "geometry": {"type": "Polygon", "coords": gg["coordinates"]}})
                        names.append(ocad)
                except (ValueError, TypeError):
                    continue
        objs = []
        for ch in dict.fromkeys(names):
            pre = next((o for o in geo_objs if o["name"] == ch), None)
            if pre:
                objs.append(pre); continue
            g = _poly(ch) or _fetch(ch)
            objs.append({"name": ch, "geometry": {"type": "Polygon", "coords": g} if g else None})
        return objs + agro_pts

    parcels = []
    for cad in cad_numbers:
        poly = _poly(cad) or _fetch(cad)
        objects, seen = [], set()

        def _add(o):
            if o["name"] in seen:
                return
            seen.add(o["name"]); objects.append(o)

        for src in building_sources:                  # порядок выбора (умолч. 2→1→3)
            if src == "nspd" and building_discovery and poly:
                for o in building_discovery(poly):    # обнаружение ОКС в границах ЗУ
                    _add(o)
            elif src == "db":
                for o in _from_db(cad, poly):
                    _add(o)
            elif src == "cads" and extra_building_cads:
                for ch in extra_building_cads:
                    g = _poly(ch) or _fetch(ch)
                    _add({"name": ch, "geometry": {"type": "Polygon", "coords": g} if g else None})
        parcels.append({"cad": cad, "polygon": poly, "objects": objects})
    return parcels
