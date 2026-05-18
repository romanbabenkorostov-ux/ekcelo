#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pirushin_sosn_rocha_08_build_kmz_v1.py

Идемпотентно собирает KMZ из GOLDEN_PATH-структуры проекта.

  <root>/_data/structure.json   ← из 052_make_structure
  <root>/_data/nspd_cache/*.json ← геометрия КН (Point/Polygon)
  <root>/_data/graph.html       ← из 04_nspd_graph
  <root>/08_Фотографии/**.jpg   ← фото (EXIF GPS)
  <root>/09_Документы_JPG/**.jpg ← документы (EXIF UserComment JSON)
       │
       ▼
  <root>/_exports/project.kmz   ← готовый KMZ

KMZ-формат подобран совместимо с:
  • Google Earth Pro (extrude по высоте, balloon с <description>),
  • https://romanbabenkorostov-ux.github.io/ekcelo/ (фронт-просмотрщик
    `index.html` ищет doc.kml в корне zip, фото детектит как Point +
    `<description><img src="images/<file>">`, документы кладём в docs/
    чтобы они НЕ интерпретировались как фото).

Запуск:  python pirushin_sosn_rocha_08_build_kmz_v1.py

Зависимости:  Pillow (опц.), piexif (опц.)
"""

from __future__ import annotations
import json
import re
import sys
import zipfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

try:
    import piexif
    from piexif.helper import UserComment
except ImportError:
    piexif = None
    UserComment = None


class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; CY = "\033[96m"; B = "\033[1m"; X = "\033[0m"
def cp(t="", c=""): print(f"{c}{t}{C.X}" if c else t)


# ─── Геометрия / индексы ────────────────────────────────────────────────────
def _centroid_lonlat(coords) -> tuple[float, float] | None:
    pts = []
    def walk(v):
        if isinstance(v, list) and v and isinstance(v[0], (int, float)) and len(v) >= 2:
            pts.append((float(v[0]), float(v[1])))
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(coords)
    if not pts: return None
    return sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts)


def _extract_geom(info: dict) -> dict:
    if not isinstance(info, dict): return {}
    for key in ("geometry", "Геометрия", "geom"):
        g = info.get(key)
        if isinstance(g, dict):
            t = g.get("type"); c = g.get("coordinates")
            if t == "Point" and isinstance(c, list) and len(c) >= 2:
                return {"type": "Point", "coords": [[float(c[0]), float(c[1])]]}
            if t == "Polygon" and isinstance(c, list) and c:
                return {"type": "Polygon", "coords": c}
            if t == "MultiPolygon" and isinstance(c, list) and c:
                return {"type": "Polygon", "coords": c[0]}
    for klat, klon in (("Широта", "Долгота"), ("lat", "lon")):
        if klat in info and klon in info:
            try: return {"type": "Point",
                         "coords": [[float(info[klon]), float(info[klat])]]}
            except Exception: pass
    return {}


def _floors(info: dict) -> int | None:
    if not isinstance(info, dict): return None
    for k in ("Количество этажей", "Этажность", "floors", "Этажей"):
        v = info.get(k)
        if v is None: continue
        m = re.search(r"\d+", str(v))
        if m: return int(m.group(0))
    return None


def load_nspd_cache(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    cdir = root / "_data" / "nspd_cache"
    if not cdir.exists(): return out
    for jf in cdir.glob("*.json"):
        try: data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception: continue
        if not isinstance(data, dict): continue
        for _, by_cn in data.items():
            if not isinstance(by_cn, dict): continue
            for cn, rec in by_cn.items():
                info = (rec or {}).get("info") if isinstance(rec, dict) else None
                out[cn] = info if isinstance(info, dict) else {}
    return out


def load_structure(root: Path) -> dict:
    p = root / "_data" / "structure.json"
    if not p.exists():
        cands = sorted((root / "_data").glob("structure_*.json"))
        if cands: p = cands[-1]
    if not p.exists():
        cp(f"  structure.json не найден в {root/'_data'}", C.R)
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        cp(f"  structure.json не прочитан: {e}", C.R); return {}


# ─── EXIF GPS из JPG ────────────────────────────────────────────────────────
def _rat_to_deg(rat) -> float:
    d = rat[0][0] / rat[0][1]
    m = rat[1][0] / rat[1][1]
    s = rat[2][0] / rat[2][1]
    return d + m/60 + s/3600

def read_gps(jpg: Path) -> dict:
    """Возвращает {lat, lon, alt, ucomment_dict?, description?}."""
    if piexif is None: return {}
    try: exif = piexif.load(str(jpg))
    except Exception: return {}
    gps = exif.get("GPS", {}) or {}
    out: dict = {}
    try:
        if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
            lat = _rat_to_deg(gps[piexif.GPSIFD.GPSLatitude])
            lon = _rat_to_deg(gps[piexif.GPSIFD.GPSLongitude])
            if gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N") in (b"S", "S"): lat = -lat
            if gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E") in (b"W", "W"): lon = -lon
            out["lat"] = lat; out["lon"] = lon
        if piexif.GPSIFD.GPSAltitude in gps:
            a = gps[piexif.GPSIFD.GPSAltitude]
            alt = a[0]/a[1]
            if gps.get(piexif.GPSIFD.GPSAltitudeRef, 0) == 1: alt = -alt
            out["alt"] = alt
    except Exception: pass
    try:
        uc = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment)
        if uc:
            s = UserComment.load(uc) if UserComment else ""
            try: out["ucomment"] = json.loads(s)
            except Exception: out["ucomment_raw"] = s
    except Exception: pass
    try:
        d = exif.get("0th", {}).get(piexif.ImageIFD.ImageDescription)
        if d: out["description"] = d.decode("utf-8", "ignore") if isinstance(d, bytes) else str(d)
    except Exception: pass
    return out


# ─── KML builder ────────────────────────────────────────────────────────────
KML_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{name}</name>
  <description><![CDATA[Сгенерировано pirushin_sosn_rocha_08_build_kmz_v1.py
{ts}]]></description>

  <Style id="land">
    <LineStyle><color>ff00aaff</color><width>2</width></LineStyle>
    <PolyStyle><color>3300aaff</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Style id="building">
    <LineStyle><color>ff1f7aff</color><width>2</width></LineStyle>
    <PolyStyle><color>881f7aff</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Style id="structure">
    <LineStyle><color>ff999999</color><width>2</width></LineStyle>
    <PolyStyle><color>66999999</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Style id="ons">
    <LineStyle><color>ff00ffff</color><width>2</width></LineStyle>
    <PolyStyle><color>4400ffff</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Style id="photo">
    <IconStyle><scale>1.0</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/camera.png</href></Icon>
    </IconStyle>
    <BalloonStyle><text><![CDATA[$[description]]]></text></BalloonStyle>
  </Style>
  <Style id="doc">
    <IconStyle><scale>0.9</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/info.png</href></Icon>
    </IconStyle>
    <BalloonStyle><text><![CDATA[$[description]]]></text></BalloonStyle>
  </Style>
  <Style id="graph">
    <IconStyle><scale>1.3</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/open-diamond.png</href></Icon>
    </IconStyle>
    <BalloonStyle><text><![CDATA[$[description]]]></text></BalloonStyle>
  </Style>
"""
KML_FOOT = "</Document></kml>\n"


def _coords_str(ring: list, z: float) -> str:
    """ring = [[lon,lat], ...] → 'lon,lat,z lon,lat,z ...'"""
    out = []
    for p in ring:
        if not isinstance(p, list) or len(p) < 2: continue
        out.append(f"{float(p[0]):.7f},{float(p[1]):.7f},{z:.2f}")
    return " ".join(out)


def polygon_kml(coords: list, z: float, extrude: bool) -> str:
    """coords = Polygon (rings) per GeoJSON: [[outer],[hole], ...]"""
    if not coords: return ""
    rings = coords if isinstance(coords[0][0], list) else [coords]
    outer = rings[0]
    extrude_xml = "<extrude>1</extrude>" if extrude else "<extrude>0</extrude>"
    alt_mode = "relativeToGround" if extrude else "clampToGround"
    inner = ""
    for hole in rings[1:]:
        inner += (f"<innerBoundaryIs><LinearRing><coordinates>"
                  f"{_coords_str(hole, z)}</coordinates></LinearRing></innerBoundaryIs>")
    return (f"<Polygon>{extrude_xml}<altitudeMode>{alt_mode}</altitudeMode>"
            f"<outerBoundaryIs><LinearRing><coordinates>"
            f"{_coords_str(outer, z)}</coordinates></LinearRing></outerBoundaryIs>"
            f"{inner}</Polygon>")


def folder_open(name: str, open_=True) -> str:
    return f"<Folder><name>{xml_escape(name)}</name><open>{1 if open_ else 0}</open>"


def placemark(name: str, descr_html: str, style_id: str, geom_xml: str,
              ts: str | None = None) -> str:
    ts_xml = f"<TimeStamp><when>{ts}</when></TimeStamp>" if ts else ""
    return (f"<Placemark><name>{xml_escape(name)}</name>"
            f"<styleUrl>#{style_id}</styleUrl>"
            f"<description><![CDATA[{descr_html}]]></description>"
            f"{ts_xml}{geom_xml}</Placemark>")


# ─── Сборка балунов ─────────────────────────────────────────────────────────
def cad_balloon(cad: dict, docs_for_cad: list[Path],
                photos_for_cad: list[Path] | None = None,
                xml_meta: dict | None = None) -> str:
    rows = []
    for k in ("cadastral_number", "object_type", "address"):
        v = cad.get(k)
        if k == "address" and xml_meta and xml_meta.get("address"):
            v = xml_meta["address"]  # XML точнее, чем NSPD-кеш
        if v: rows.append(f"<tr><td><b>{xml_escape(k)}</b></td>"
                          f"<td>{xml_escape(str(v))}</td></tr>")
    info = cad.get("_raw_info") or {}
    for k in ("Площадь", "Количество этажей", "Назначение", "Год постройки"):
        v = info.get(k) if isinstance(info, dict) else None
        if v: rows.append(f"<tr><td>{xml_escape(k)}</td>"
                          f"<td>{xml_escape(str(v))}</td></tr>")
    if xml_meta:
        rows.append("<tr><td colspan='2'><b>Из XML-выписки ЕГРН:</b></td></tr>")
        for label, key in (("№ выписки", "kuvi"), ("Дата", "extract_date"),
                           ("Площадь", "area"), ("Кад. стоимость", "cad_value"),
                           ("Правообладатель", "holder_name"),
                           ("ИНН", "holder_inn"), ("ОГРН", "holder_ogrn"),
                           ("Вид права", "right_type")):
            v = xml_meta.get(key)
            if v: rows.append(f"<tr><td>{xml_escape(label)}</td>"
                              f"<td>{xml_escape(str(v))}</td></tr>")
    body = ("<table style='font-family:Arial;font-size:12px;"
            "border-collapse:collapse'>" + "".join(rows) + "</table>")
    if docs_for_cad:
        imgs = "".join(
            f"<div><img src='docs/{xml_escape(p.name)}' "
            f"style='max-width:520px;border:1px solid #888;margin-top:6px'/>"
            f"<div style='font-size:10px;color:#666'>{xml_escape(p.name)}</div></div>"
            for p in docs_for_cad
        )
        body += "<hr/><b>Документы:</b>" + imgs
    if photos_for_cad:
        imgs = "".join(
            f"<a href='images/{xml_escape(p.name)}'>"
            f"<img src='images/{xml_escape(p.name)}' "
            f"style='max-width:240px;margin:4px;border:1px solid #aaa'/></a>"
            for p in photos_for_cad
        )
        body += "<hr/><b>Фото:</b><div>" + imgs + "</div>"
    return body


def photo_balloon(jpg_name: str, meta: dict) -> str:
    descr = meta.get("description") or ""
    parts = [f"<img src='images/{xml_escape(jpg_name)}' style='max-width:640px'/>"]
    if descr: parts.append(f"<div style='margin-top:6px'>{xml_escape(descr)}</div>")
    return "".join(parts)


# ─── Главная сборка ─────────────────────────────────────────────────────────
def build_kmz(root: Path) -> Path:
    st = load_structure(root)
    if not st:
        cp("  пустой structure — KMZ будет минимальным.", C.Y)
    cache = load_nspd_cache(root)

    # Объединённый «вид» по КН
    by_cn: dict[str, dict] = {}
    for cad in st.get("cadastre_objects", []):
        cn = cad.get("cadastral_number")
        if not cn: continue
        info = cache.get(cn) or cad.get("_raw_info") or {}
        geom = _extract_geom(info) or _extract_geom(cad.get("_raw_info") or {})
        floors = _floors(info)
        is_land = (cad.get("object_type") or "").lower().startswith("земельн")
        z = 0.0 if is_land else (floors or 1) * 3.0
        by_cn[cn] = {**cad, "_geom": geom, "_z": z, "_is_land": is_land,
                     "_floors": floors, "_info": info}

    # ── Документы, привязка КН/ИНН → файлы ────────────────────────────────
    #   egrn_ / svid_ / tehpasp_ / tehplan_  → к КН (баллон объекта)
    #   egrul_ / egrip_                       → к ИНН → к BU (без Point)
    docs_dir = root / "Документы_JPG"
    doc_by_cad: dict[str, list[Path]] = {}
    doc_by_inn: dict[str, list[Path]] = {}
    cad_doc_re = re.compile(
        r"^(egrn|svid|tehpasp|tehplan|doc)_(\d{2})_(\d{2})_(\d{1,8})_(\d{1,8})"
    )
    for jpg in sorted(docs_dir.rglob("*.jpg")):
        m = cad_doc_re.search(jpg.name)
        if m:
            cn = f"{m.group(2)}:{m.group(3)}:{m.group(4)}:{m.group(5)}"
            doc_by_cad.setdefault(cn, []).append(jpg); continue
        m = re.search(r"egr(?:ul|ip)_inn(?:fl)?(\d{10,12})", jpg.name)
        if m: doc_by_inn.setdefault(m.group(1), []).append(jpg); continue

    # Точные данные из XML-выписок (создаётся 07-скриптом)
    xml_facts: dict[str, dict] = {}
    xfp = root / "_data" / "egrn_xml.json"
    if xfp.exists():
        try: xml_facts = json.loads(xfp.read_text(encoding="utf-8"))
        except Exception: xml_facts = {}

    # ── Фотографии: привязка либо по EXIF GPS, либо по структуре папок.
    # Распознаваемые пути (после `Фотографии/`):
    #   Недвижимость/<категория>/<КН>/[План/]...   — КН 61_44_0050706_31,
    #       категория ∈ {Земельные_участки,Строения,Сооружения,Помещения,ОНЗ}
    #   Оборудование/<инв>/...                     — инвентарный № как имя папки
    #   Бизнес_единицы/<slug>/...                  — slug BU
    #   Не_распределено/...                        — без привязки
    REALTY_CATS_SET = {"Земельные_участки", "Строения", "Сооружения",
                       "Помещения", "ОНЗ"}
    photos_dir = root / "Фотографии"
    photos: list[tuple[Path, dict, dict]] = []  # (path, gps_meta, tag)
    photos_by_cad: dict[str, list[Path]] = {}
    photos_by_eq: dict[str, list[Path]]  = {}
    photos_by_bu: dict[str, list[Path]]  = {}

    def _tag_from_path(jpg: Path) -> dict:
        try:    rel = jpg.relative_to(photos_dir)
        except Exception: return {}
        parts = rel.parts
        if len(parts) < 2: return {}
        top = parts[0]
        if top == "Недвижимость" and len(parts) >= 3 and parts[1] in REALTY_CATS_SET:
            cn = parts[2].replace("_", ":")  # 61_44_0050706_31 → 61:44:0050706:31
            return {"kind": "cad", "cad": cn, "category": parts[1]}
        if top == "Оборудование":
            return {"kind": "eq", "eq": parts[1]}
        if top == "Бизнес_единицы":
            return {"kind": "bu", "bu": parts[1]}
        return {}

    for jpg in sorted(photos_dir.rglob("*.jpg")):
        tag = _tag_from_path(jpg)
        meta = read_gps(jpg)
        # координаты: EXIF приоритетнее, иначе центроид связанного объекта
        if "lat" not in meta and tag.get("kind") == "cad":
            cad = by_cn.get(tag["cad"]) or {}
            g = cad.get("_geom") or {}
            cen = _centroid_lonlat(g.get("coords")) if g.get("coords") else None
            if cen:
                meta["lon"], meta["lat"] = cen
                meta["alt"] = (cad.get("_z") or 0.0)
        if "lat" not in meta and tag.get("kind") == "eq":
            # ищем оборудование с этим инвентарным → центроид его КН
            for eq in st.get("equipment", []):
                if str(eq.get("inv_number_hint") or "") == tag["eq"]:
                    cid = (eq.get("links") or {}).get("cadastre_id")
                    cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
                    if cad and cad.get("_geom", {}).get("coords"):
                        cen = _centroid_lonlat(cad["_geom"]["coords"])
                        if cen:
                            meta["lon"], meta["lat"] = cen
                            meta["alt"] = (cad.get("_z") or 0.0) / 2.0
                    break
        if "lat" in meta and "lon" in meta:
            photos.append((jpg, meta, tag))
        # индексы для подмешивания в баллоны
        if tag.get("kind") == "cad": photos_by_cad.setdefault(tag["cad"], []).append(jpg)
        elif tag.get("kind") == "eq":  photos_by_eq.setdefault(tag["eq"], []).append(jpg)
        elif tag.get("kind") == "bu":  photos_by_bu.setdefault(tag["bu"], []).append(jpg)

    # ── Сборка KML ────────────────────────────────────────────────────────
    ent = st.get("enterprise", {}) or {}
    kml_name = f"{ent.get('name_short', root.name)} — KMZ"
    ts_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    out = [KML_HEAD.format(name=xml_escape(kml_name), ts=ts_iso)]

    # 1. Кадастровые объекты по категориям
    groups = {"Земельные участки": [], "Здания": [], "Сооружения": [],
              "ОНС": [], "Помещения / прочее": []}
    for cn, cad in by_cn.items():
        ot = (cad.get("object_type") or "").lower()
        if "земельн" in ot: groups["Земельные участки"].append(cad)
        elif "здан" in ot:  groups["Здания"].append(cad)
        elif "сооруж" in ot: groups["Сооружения"].append(cad)
        elif "онс" in ot or "незаверш" in ot: groups["ОНС"].append(cad)
        else: groups["Помещения / прочее"].append(cad)

    style_map = {"Земельные участки": "land", "Здания": "building",
                 "Сооружения": "structure", "ОНС": "ons",
                 "Помещения / прочее": "structure"}

    # КН → список ИНН (для подмешивания ЕГРЮЛ/ЕГРИП в баллон каждого объекта)
    cad_to_inns: dict[str, list[str]] = {}
    for bu in st.get("business_units", []):
        for cid in bu.get("cadastre_ids") or []:
            cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
            if not cad: continue
            cn0 = cad.get("cadastral_number")
            for inn in bu.get("inns") or []:
                cad_to_inns.setdefault(cn0, []).append(str(inn))

    for gname, items in groups.items():
        if not items: continue
        out.append(folder_open(f"{gname} ({len(items)})"))
        for cad in items:
            cn = cad.get("cadastral_number")
            geom = cad.get("_geom") or {}
            if not geom: continue
            # ЕГРН — по КН; ЕГРЮЛ/ЕГРИП — по связанным ИНН
            docs = list(doc_by_cad.get(cn, []))
            for inn in cad_to_inns.get(cn, []):
                docs.extend(doc_by_inn.get(inn, []))
            name = f"{cn}" + (f" · {cad.get('address')}" if cad.get("address") else "")
            balloon = cad_balloon(cad, docs, photos_by_cad.get(cn),
                                  xml_meta=xml_facts.get(cn))
            style = style_map[gname]
            extrude = (gname in ("Здания", "Сооружения", "ОНС"))
            z = cad.get("_z", 0.0)
            if geom["type"] == "Polygon":
                geom_xml = polygon_kml(geom["coords"], z, extrude)
            else:
                lon, lat = geom["coords"][0]
                geom_xml = (f"<Point><altitudeMode>"
                            f"{'relativeToGround' if extrude else 'clampToGround'}"
                            f"</altitudeMode><coordinates>{lon:.7f},{lat:.7f},"
                            f"{z:.2f}</coordinates></Point>")
            out.append(placemark(name, balloon, style, geom_xml))
        out.append("</Folder>")

    # 2. Бизнес-единицы (без Point) + выписки ЕГРЮЛ/ЕГРИП в балунах.
    #    Документы юрлиц/ИП НЕ привязываются к координатам — попадают в
    #    список Places sidebar и (продублированно) в баллоны связанных КН.
    bus = st.get("business_units", []) or []
    if bus:
        out.append(folder_open(f"Бизнес-единицы ({len(bus)})", False))
        for bu in bus:
            inns = [str(x) for x in (bu.get("inns") or [])]
            files: list[Path] = []
            for inn in inns: files.extend(doc_by_inn.get(inn, []))
            rows = []
            rows.append(f"<tr><td><b>Название</b></td><td>{xml_escape(str(bu.get('name','')))}</td></tr>")
            if bu.get("address"):
                rows.append(f"<tr><td>Адрес</td><td>{xml_escape(str(bu['address']))}</td></tr>")
            if inns:
                rows.append(f"<tr><td>ИНН</td><td>{', '.join(inns)}</td></tr>")
            tbl = ("<table style='font-family:Arial;font-size:12px'>"
                   + "".join(rows) + "</table>")
            imgs = "".join(
                f"<div><img src='docs/{xml_escape(p.name)}' style='max-width:520px;"
                f"margin-top:6px;border:1px solid #888'/>"
                f"<div style='font-size:10px;color:#666'>{xml_escape(p.name)}</div></div>"
                for p in files
            )
            balloon = tbl + ("<hr/><b>ЕГРЮЛ/ЕГРИП:</b>" + imgs if imgs else "")
            # без Point: Placemark отображается только в дереве слева
            out.append(f"<Placemark><name>{xml_escape(bu.get('name','BU'))}</name>"
                       f"<styleUrl>#doc</styleUrl>"
                       f"<description><![CDATA[{balloon}]]></description></Placemark>")
        out.append("</Folder>")

    # 2b. Оборудование (Point на центроиде связанного КН)
    eqs = st.get("equipment", []) or []
    if eqs:
        out.append(folder_open(f"Оборудование ({len(eqs)})", False))
        for eq in eqs:
            cid = (eq.get("links") or {}).get("cadastre_id")
            if not cid: continue
            cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
            if not cad or not cad.get("_geom"): continue
            cen = _centroid_lonlat(cad["_geom"]["coords"])
            if not cen: continue
            lon, lat = cen
            z = (cad.get("_z") or 0.0) / 2.0  # «висит» в середине высоты здания
            rows = [f"<tr><td><b>{xml_escape(eq.get('name',''))}</b></td><td></td></tr>"]
            for k in ("account", "inv_number_hint", "right_type"):
                v = eq.get(k)
                if v: rows.append(f"<tr><td>{k}</td><td>{xml_escape(str(v))}</td></tr>")
            rows.append(f"<tr><td>КН</td><td>{xml_escape(cad.get('cadastral_number',''))}</td></tr>")
            balloon = "<table style='font-family:Arial;font-size:12px'>" + "".join(rows) + "</table>"
            geom_xml = (f"<Point><altitudeMode>"
                        f"{'relativeToGround' if z > 0 else 'clampToGround'}"
                        f"</altitudeMode>"
                        f"<coordinates>{lon:.7f},{lat:.7f},{z:.2f}</coordinates></Point>")
            out.append(placemark(eq.get("name", "оборудование")[:80],
                                 balloon, "doc", geom_xml))
        out.append("</Folder>")

    # 3. Фотографии (Point + <img src="images/...">), сгруппированы по привязке.
    if photos:
        groups_p: dict[str, list[tuple[Path, dict, dict]]] = {
            "Недвижимость": [], "Оборудование": [], "Бизнес-единицы": [],
            "Не распределено": []}
        for item in photos:
            t = item[2].get("kind")
            if t == "cad": groups_p["Недвижимость"].append(item)
            elif t == "eq":  groups_p["Оборудование"].append(item)
            elif t == "bu":  groups_p["Бизнес-единицы"].append(item)
            else: groups_p["Не распределено"].append(item)
        out.append(folder_open(f"Фотографии ({len(photos)})"))
        for gname, items in groups_p.items():
            if not items: continue
            out.append(folder_open(f"{gname} ({len(items)})", False))
            for jpg, meta, tag in items:
                lat, lon = meta["lat"], meta["lon"]
                alt = meta.get("alt") or 0.0
                ts = meta.get("ucomment", {}).get("ts") if isinstance(meta.get("ucomment"), dict) else None
                extra = ""
                if tag.get("kind") == "cad": extra = f"<div><b>Объект:</b> {xml_escape(tag['cad'])}</div>"
                elif tag.get("kind") == "eq": extra = f"<div><b>Оборудование:</b> {xml_escape(tag['eq'])}</div>"
                elif tag.get("kind") == "bu": extra = f"<div><b>BU:</b> {xml_escape(tag['bu'])}</div>"
                balloon = photo_balloon(jpg.name, meta) + extra
                geom_xml = (f"<Point><altitudeMode>relativeToGround</altitudeMode>"
                            f"<coordinates>{lon:.7f},{lat:.7f},{alt:.2f}</coordinates></Point>")
                out.append(placemark(jpg.name, balloon, "photo", geom_xml, ts=ts))
            out.append("</Folder>")
        out.append("</Folder>")

    # 4. Граф связей (04_nspd_graph) — отдельный Placemark с balloon-iframe
    graph_html = root / "html" / "graph.html"
    if graph_html.exists():
        # ставим точку в центр всех геометрий
        all_pts = []
        for cad in by_cn.values():
            g = cad.get("_geom") or {}
            cen = _centroid_lonlat(g.get("coords")) if g.get("coords") else None
            if cen: all_pts.append(cen)
        if all_pts:
            lon = sum(p[0] for p in all_pts)/len(all_pts)
            lat = sum(p[1] for p in all_pts)/len(all_pts)
            balloon = ("<h3>Граф связей объектов</h3>"
                       "<iframe src='graph.html' width='820' height='600' "
                       "style='border:0'></iframe>"
                       "<p><a href='graph.html'>Открыть в браузере</a></p>")
            geom_xml = (f"<Point><altitudeMode>clampToGround</altitudeMode>"
                        f"<coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>")
            out.append(folder_open("Граф 04_nspd_graph", False))
            out.append(placemark("Граф связей", balloon, "graph", geom_xml))
            out.append("</Folder>")

    out.append(KML_FOOT)
    kml_text = "".join(out)

    # ── Сборка KMZ ────────────────────────────────────────────────────────
    exp = root / "kmz-kml"; exp.mkdir(parents=True, exist_ok=True)
    kmz = exp / "project.kmz"
    tmp = kmz.with_suffix(".kmz.tmp")
    # Идемпотентность: одинаковая дата у файлов внутри zip → одинаковый hash
    zinfo_date = (2025, 1, 1, 0, 0, 0)

    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zi = zipfile.ZipInfo("doc.kml", date_time=zinfo_date)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, kml_text)

        # images/  ← фото (все, что упомянуты в KML или в баллонах объектов)
        used_photos: set[Path] = {p for p, _, _ in photos}
        for lst in photos_by_cad.values(): used_photos.update(lst)
        for lst in photos_by_eq.values():  used_photos.update(lst)
        for lst in photos_by_bu.values():  used_photos.update(lst)
        for jpg in sorted(used_photos):
            zi = zipfile.ZipInfo(f"images/{jpg.name}", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, jpg.read_bytes())
        # docs/    ← документы JPG (НЕ в images/ — иначе фронт примет за фото)
        all_docs = set()
        for lst in doc_by_cad.values(): all_docs.update(lst)
        for lst in doc_by_inn.values(): all_docs.update(lst)
        for p in sorted(all_docs):
            zi = zipfile.ZipInfo(f"docs/{p.name}", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, p.read_bytes())
        # graph.html
        if graph_html.exists():
            zi = zipfile.ZipInfo("graph.html", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, graph_html.read_bytes())

    # Атомарная замена
    tmp.replace(kmz)
    return kmz


def main() -> None:
    cp("=" * 64, C.B)
    cp(" Build KMZ — pirushin_sosn_rocha_08_build_kmz_v1", C.B)
    cp("=" * 64, C.B)

    raw = input("\nПуть к проекту (D:\\ОБЪЕКТЫ\\<Название>): ").strip()
    if not raw: cp("Путь не указан — выход.", C.R); sys.exit(1)
    root = Path(raw)
    if not root.exists(): cp(f"Папка не найдена: {root}", C.R); sys.exit(1)

    cp(f"\nСбор KMZ из {root}", C.CY)
    kmz = build_kmz(root)
    sz = kmz.stat().st_size / 1024
    cp(f"\nГотово: {kmz}  ({sz:.1f} КБ)", C.G)
    cp("Совместимо с Google Earth Pro и https://romanbabenkorostov-ux.github.io/ekcelo/", C.CY)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: cp("\nПрервано.", C.Y)
