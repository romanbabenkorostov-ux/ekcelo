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


_GOLDEN_ANGLE = 2.39996322972865332                  # ≈137.5° — узор филлотаксиса

def spiral_points(ring: list[Coord], count: int, *, margin: float = 0.45) -> list[Coord]:
    """`count` точек кучным узором (филлотаксис/«подсолнух») внутри полигона.

    Центр — центроид; радиус ∝ sqrt(i) (равномерно по площади), угол = i·золотой
    угол → нет резонанса с числом точек (архимедова спираль с целым числом
    оборотов вырождалась в линию). margin (доля габарита) задаёт кучность:
    0.45 — компактно у центра ЗУ. Точки вне полигона подтягиваются к центру."""
    if count <= 0 or len(ring) < 3:
        return []
    core = ring[:-1] if len(ring) > 2 and ring[0] == ring[-1] else ring
    cx, cy = centroid(core)
    minx, miny, maxx, maxy = bbox(ring)
    rx = (maxx - minx) / 2.0 * margin
    ry = (maxy - miny) / 2.0 * margin
    out: list[Coord] = []
    for i in range(count):
        rad = math.sqrt((i + 0.5) / count)          # равномерно по площади
        theta = i * _GOLDEN_ANGLE
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


def _description(info: Optional[dict], *, no_coords: bool = False) -> str:
    """KML <description> с таблицей «Информация» (всплывает при клике в Google Earth).
    no_coords=True добавляет пометку «Без координат границ по Росреестру» (объект
    поставлен по спирали, реальной границы в ЕГРН нет)."""
    rows = []
    for k, v in (info or {}).items():
        if v in (None, "", []):
            continue
        rows.append(f"<tr><td><b>{_xml.escape(str(k))}</b></td>"
                    f"<td>{_xml.escape(str(v))}</td></tr>")
    if no_coords:
        rows.append("<tr><td colspan=\"2\"><i>Без координат границ по Росреестру</i>"
                    "</td></tr>")
    if not rows:
        return ""
    html = "<table border=\"0\" cellpadding=\"2\">" + "".join(rows) + "</table>"
    return f"<description><![CDATA[{html}]]></description>"


def _placemark_polygon(name: str, ring: list[Coord], style: str, desc: str = "") -> str:
    return (f"<Placemark><name>{_xml.escape(name)}</name>{desc}<styleUrl>#{style}</styleUrl>"
            f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_coords_str(ring)}"
            f"</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")


def _placemark_point(name: str, pt: Coord, style: str, desc: str = "") -> str:
    return (f"<Placemark><name>{_xml.escape(name)}</name>{desc}<styleUrl>#{style}</styleUrl>"
            f"<Point><coordinates>{pt[0]},{pt[1]},0</coordinates></Point></Placemark>")


_STYLES = """
<Style id="parcel"><LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
<PolyStyle><fill>0</fill></PolyStyle></Style>
<Style id="objpoly"><LineStyle><color>ff00aa00</color><width>2</width></LineStyle>
<PolyStyle><color>5500aa00</color></PolyStyle></Style>
<Style id="objpoint"><IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>
<Style id="spiral"><IconStyle><color>ff00ffff</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>
""".strip()


def _render_parcels(parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Единый промежуточный слой для KML/KMZ/JSON: координаты спиральных точек
    вычисляются ОДИН раз → KML и JSON согласованы. Поддерживает ЗУ и одиночные
    ОКС (kind='oks'): у ОКС геометрия — собственный контур (polygon) либо точка
    (point, «без координат границ»)."""
    out = []
    for p in parcels:
        cad = str(p.get("cad", "?"))
        kind = p.get("kind") or "zu"
        ring = _ring(p.get("polygon"))
        ppt = p.get("point")
        if ring:
            pgeom = {"kind": "polygon", "ring": ring}
        elif ppt:
            pgeom = {"kind": "point", "pt": (float(ppt[0]), float(ppt[1]))}
        else:
            pgeom = {"kind": "none"}
        objs_out, no_geom = [], []
        for o in (p.get("objects") or []):
            g = o.get("geometry")
            nm = str(o.get("name", "объект"))
            if g and g.get("coords"):
                if g.get("type") == "Point":
                    c = g["coords"][0]
                    geom = {"kind": "point", "pt": (float(c[0]), float(c[1]))}
                else:
                    geom = {"kind": "polygon", "ring": _ring(g["coords"])}
                objs_out.append({"name": nm, "info": o.get("info"),
                                 "geometry": geom, "no_coords": False})
            else:
                no_geom.append((nm, o.get("info")))
        # объекты без геометрии → точки по спирали внутри ЗУ («без координат границ»)
        if no_geom and ring:
            for (nm, info), pt in zip(no_geom, spiral_points(ring, len(no_geom))):
                objs_out.append({"name": nm, "info": info,
                                 "geometry": {"kind": "point", "pt": pt}, "no_coords": True})
        else:
            for nm, info in no_geom:
                objs_out.append({"name": nm, "info": info,
                                 "geometry": {"kind": "none"}, "no_coords": True})
        out.append({"cad": cad, "kind": kind, "info": p.get("info"),
                    "geometry": pgeom,
                    "no_coords": (pgeom["kind"] == "point" and kind == "oks"),
                    "objects": objs_out})
    return out


def _stats(rendered: list[dict[str, Any]]) -> dict[str, int]:
    n_pg = sum(1 for r in rendered if r["geometry"]["kind"] == "polygon")
    n_c = sum(1 for r in rendered for o in r["objects"]
              if o["geometry"]["kind"] == "polygon")
    n_s = sum(1 for r in rendered for o in r["objects"]
              if o["geometry"]["kind"] == "point" and o["no_coords"])
    return {"parcels": len(rendered), "parcels_with_geom": n_pg,
            "objects_with_contour": n_c, "objects_spiral": n_s}


def _kml_from_rendered(rendered: list[dict[str, Any]]) -> str:
    folders = []
    for r in rendered:
        cad = r["cad"]
        head = "ОКС" if r["kind"] == "oks" else "ЗУ"
        body = []
        gk = r["geometry"]["kind"]
        if gk == "polygon":
            style = "objpoly" if r["kind"] == "oks" else "parcel"
            body.append(_placemark_polygon(f"{head} {cad}", r["geometry"]["ring"], style,
                                           _description(r.get("info"))))
        elif gk == "point":
            body.append(_placemark_point(f"{head} {cad}", r["geometry"]["pt"], "spiral",
                                         _description(r.get("info"), no_coords=r["no_coords"])))
        for o in r["objects"]:
            ok = o["geometry"]["kind"]
            desc = _description(o.get("info"), no_coords=o["no_coords"])
            if ok == "polygon":
                body.append(_placemark_polygon(o["name"], o["geometry"]["ring"], "objpoly", desc))
            elif ok == "point":
                style = "spiral" if o["no_coords"] else "objpoint"
                body.append(_placemark_point(o["name"], o["geometry"]["pt"], style, desc))
        folders.append(f"<Folder><name>{_xml.escape(head)} {_xml.escape(cad)}</name>"
                       f"{''.join(body)}</Folder>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f'{_STYLES}{"".join(folders)}</Document></kml>')


def _yandex_geom(geom: dict) -> Optional[dict]:
    """Внутр. геометрия → Яндекс.Карты (порядок координат [lat, lon])."""
    k = geom.get("kind")
    if k == "polygon":
        ring = geom["ring"]
        coords = [[round(lat, 7), round(lon, 7)] for lon, lat in ring]
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        return {"type": "Polygon", "coordinates": [coords]}
    if k == "point":
        lon, lat = geom["pt"]
        return {"type": "Point", "coordinates": [round(lat, 7), round(lon, 7)]}
    return None


_NO_COORDS_NOTE = "Без координат границ по Росреестру"


def _json_from_rendered(rendered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Полный JSON: все объекты; полигон → полигон; нет координат в Росреестре →
    точка + пометка. Геометрия в формате Яндекс.Карт ([lat, lon])."""
    def obj(name, kind, info, geom, no_coords):
        d = {"cad": name, "kind": kind, "info": info or {},
             "geometry": _yandex_geom(geom)}
        if no_coords:
            d["note"] = _NO_COORDS_NOTE
        return d
    out = []
    for r in rendered:
        entry = obj(r["cad"], r["kind"], r["info"], r["geometry"], r["no_coords"])
        entry["objects"] = [obj(o["name"], "oks", o["info"], o["geometry"], o["no_coords"])
                            for o in r["objects"]]
        out.append(entry)
    return out


def build_kml(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Собрать KML по списку участков/ОКС. Возвращает {kml, stats}."""
    rendered = _render_parcels(parcels)
    return {"kml": _kml_from_rendered(rendered), "stats": _stats(rendered)}


def build_outputs(base_path: str | Path, parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Записать KMZ + KML + JSON (Яндекс-геометрия) с общим телом имени `base_path`
    (без расширения). Возвращает {kmz, kml, json, stats}."""
    import json as _json
    rendered = _render_parcels(parcels)
    kml = _kml_from_rendered(rendered)
    base = Path(base_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    kmz_p = base.with_suffix(".kmz")
    kml_p = base.with_suffix(".kml")
    json_p = base.with_suffix(".json")
    with zipfile.ZipFile(kmz_p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
    kml_p.write_text(kml, encoding="utf-8")
    json_p.write_text(_json.dumps(_json_from_rendered(rendered), ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return {"kmz": str(kmz_p), "kml": str(kml_p), "json": str(json_p),
            "stats": _stats(rendered)}


def build_kmz(out_path: str | Path, parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Совместимость: KMZ + JSON-сайдкар. Возвращает {path, stats, info_json}."""
    import json as _json
    rendered = _render_parcels(parcels)
    res = {"kml": _kml_from_rendered(rendered), "stats": _stats(rendered)}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", res["kml"])
    sidecar = out.with_suffix(".info.json")
    sidecar.write_text(_json.dumps(_json_from_rendered(rendered), ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return {"path": str(out), "stats": res["stats"], "info_json": str(sidecar)}


def merge_previous(parcels: list[dict[str, Any]],
                   prev_json_path: str | Path) -> list[dict[str, Any]]:
    """Идемпотентное обновление: подмешать контуры из ранее записанного JSON.
    Правило — **контур побеждает**: если в прошлом файле у объекта был полигон,
    а сейчас его нет (спираль/точка), берём старый контур; новый контур всегда
    перезаписывает. Привязка по КН (cad/name)."""
    import json as _json
    try:
        prev = _json.loads(Path(prev_json_path).read_text(encoding="utf-8"))
    except Exception:
        return parcels
    # карта КН → полигон-coords (внутренний [lon,lat]) из прошлого JSON (Яндекс [lat,lon])
    prev_poly: dict[str, list] = {}

    def _take(entry):
        g = entry.get("geometry") or {}
        if g.get("type") == "Polygon" and g.get("coordinates"):
            ring = [[lon, lat] for lat, lon in g["coordinates"][0]]
            prev_poly[str(entry.get("cad"))] = [ring]
    for e in (prev or []):
        _take(e)
        for o in e.get("objects") or []:
            _take(o)

    def _has_contour(geom):
        return bool(geom and geom.get("type") in ("Polygon", "MultiPolygon")
                    and geom.get("coords"))
    for p in parcels:
        if not _has_contour(p.get("polygon") and {"type": "Polygon", "coords": p.get("polygon")}):
            if str(p.get("cad")) in prev_poly:
                p["polygon"] = prev_poly[str(p["cad"])]
        for o in (p.get("objects") or []):
            if not _has_contour(o.get("geometry")) and str(o.get("name")) in prev_poly:
                o["geometry"] = {"type": "Polygon", "coords": prev_poly[str(o["name"])]}
    return parcels


def output_basename(cads: list[str], when=None) -> str:
    """Тело имени файлов: <первый КН с ':'→'_'>[_и_далее]_<YYYYMMDD_HHMMSS>."""
    from datetime import datetime
    head = (cads[0] if cads else "objects").replace(":", "_").replace(" ", "")
    if len(cads) > 1:
        head += "_и_далее"
    ts = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"{head}_{ts}"


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
