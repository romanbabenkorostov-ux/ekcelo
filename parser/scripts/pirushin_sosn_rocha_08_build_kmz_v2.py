#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pirushin_sosn_rocha_08_build_kmz_v2.py

Идемпотентный сборщик KMZ из GOLDEN_PATH-структуры проекта,
совместимый с контрактом KML_INGESTION_SPEC v2.10.0
(расширение v2.9.62 фронт-просмотрщика
https://github.com/romanbabenkorostov-ux/ekcelo).

Отличия от v1:
  • 9 префиксов styleUrl (cad_zu_/cad_oks_/cad_room_/cad_str_/cad_ons_/
    cad_bu_/cad_eq_/cad_ben_/cad_exp_) + photoPin_*.
  • 10 Folder верхнего уровня вместо 5.
  • description — пары "Ключ: значение; " без HTML.
  • Фото без EXIF-GPS раскладываются по спирали Фибоначчи вокруг
    центроида привязанного КН (r0=25 м, φ=137.508°).
  • ExtendedData с object_type/cad_number/z_meters_top/… в каждом Placemark.
  • <atom:author> + kml_schema_version=2.0 в <Document>.

Входные данные (как в v1):
  <root>/_data/structure.json
  <root>/_data/nspd_cache/*.json
  <root>/_data/graph.html
  <root>/08_Фотографии/**.jpg
  <root>/09_Документы_JPG/**.jpg
       │
       ▼
  <root>/kmz-kml/project.kmz

Запуск:
  python pirushin_sosn_rocha_08_build_kmz_v2.py --root D:\\ОБЪЕКТЫ\\<Название>
  python pirushin_sosn_rocha_08_build_kmz_v2.py            # с интерактивным вводом

Зависимости: piexif (опц., для чтения EXIF-GPS).
"""

from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

try:
    import piexif
    from piexif.helper import UserComment
except ImportError:
    piexif = None
    UserComment = None


# ─── Константы ──────────────────────────────────────────────────────────────

KML_SCHEMA_VERSION = "2.0"
GENERATOR_NAME = "pirushin_sosn_rocha_08_build_kmz_v2.py"

# Spiral (см. spec v2.10.0 §A.7)
GOLDEN_DEG = 137.508
SPIRAL_R0_M = 25.0
SPIRAL_DR_M = 4.0
LAT_M_PER_DEG = 111320.0

# Кадастровый номер как отдельный токен
CN_RE = re.compile(r"\b(\d{2}:\d{2}:\d{2,8}:\d{1,8}(?:/\d+)?)\b")

# Цвета и иконки по kind. ABGR (не RGBA).
STYLE_TABLE: dict[str, dict] = {
    "zu":    {"line": "ff007f00", "poly": "33007f00", "icon": None,
              "icon_url": None},
    "oks":   {"line": "ff7f007f", "poly": "337f007f", "icon": None,
              "icon_url": None},
    "room":  {"line": "ffaa00aa", "poly": "44aa00aa", "icon": "ffaa00aa",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/donut.png"},
    "str":   {"line": "ff999999", "poly": "66999999", "icon": None,
              "icon_url": None},
    "ons":   {"line": "ff00ffff", "poly": "4400ffff", "icon": None,
              "icon_url": None},
    "bu":    {"line": None, "poly": None, "icon": "ff1ea0ff",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/target.png"},
    "eq":    {"line": None, "poly": None, "icon": "ff00aaff",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/forbidden.png"},
    "ben":   {"line": None, "poly": None, "icon": "ffe5541e",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/man.png"},
    "exp":   {"line": None, "poly": None, "icon": "ffe5541e",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"},
    "photo": {"line": None, "poly": None, "icon": "ffff8800",
              "icon_url": "http://maps.google.com/mapfiles/kml/shapes/camera.png"},
}

# Префиксы Style id / styleUrl. Подстрока — единственный сигнал классификатору.
STYLE_PREFIX = {
    "zu": "cad_zu_", "oks": "cad_oks_", "room": "cad_room_",
    "str": "cad_str_", "ons": "cad_ons_", "bu": "cad_bu_",
    "eq": "cad_eq_", "ben": "cad_ben_", "exp": "cad_exp_",
    "photo": "photoPin_",
}

# Порядок Folder верхнего уровня. Пустые группы пропускаются.
FOLDER_ORDER = [
    "Земельные участки", "ОКС", "Помещения", "Сооружения", "ОНС",
    "Бизнес-единицы", "Оборудование", "Бенефициары",
    "Фотографии", "Пояснения",
]

# Folder → kind, который туда кладётся.
FOLDER_KIND = {
    "Земельные участки": "zu", "ОКС": "oks", "Помещения": "room",
    "Сооружения": "str", "ОНС": "ons", "Бизнес-единицы": "bu",
    "Оборудование": "eq", "Бенефициары": "ben", "Пояснения": "exp",
}


# ─── Вывод ──────────────────────────────────────────────────────────────────
class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
    CY = "\033[96m"; B = "\033[1m"; X = "\033[0m"

def cp(t="", c=""): print(f"{c}{t}{C.X}" if c else t)


# ─── Геометрия / индексы ────────────────────────────────────────────────────
def _geom_centroid(geom: dict | None) -> tuple[float, float] | None:
    """Centroid (lon, lat) для Point / Polygon / MultiPolygon из _extract_geom.

    Polygon → среднее всех вершин внешнего контура без замыкающей.
    Point → сам Point.
    MultiPolygon → центроид первого полигона.
    """
    if not geom or "coords" not in geom:
        return None
    t = geom.get("type")
    coords = geom["coords"]
    if t == "Point":
        if not coords or len(coords[0]) < 2:
            return None
        return float(coords[0][0]), float(coords[0][1])
    if t == "Polygon":
        # coords — список рингов (GeoJSON-like) или плоский ring
        ring = coords[0] if (coords and isinstance(coords[0][0], list)) else coords
        if not ring:
            return None
        # без замыкающей точки
        unique = ring[:-1] if (len(ring) > 1 and ring[0] == ring[-1]) else ring
        if not unique:
            return None
        n = len(unique)
        return (sum(float(p[0]) for p in unique) / n,
                sum(float(p[1]) for p in unique) / n)
    return None


def _extract_geom(info: dict) -> dict:
    if not isinstance(info, dict):
        return {}
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
            try:
                return {"type": "Point",
                        "coords": [[float(info[klon]), float(info[klat])]]}
            except Exception:
                pass
    return {}


def _floors(info: dict) -> int | None:
    if not isinstance(info, dict):
        return None
    for k in ("Количество этажей", "Этажность", "floors", "Этажей"):
        v = info.get(k)
        if v is None:
            continue
        m = re.search(r"\d+", str(v))
        if m:
            return int(m.group(0))
    return None


def load_nspd_cache(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    cdir = root / "_data" / "nspd_cache"
    if not cdir.exists():
        return out
    for jf in cdir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for _, by_cn in data.items():
            if not isinstance(by_cn, dict):
                continue
            for cn, rec in by_cn.items():
                info = (rec or {}).get("info") if isinstance(rec, dict) else None
                out[cn] = info if isinstance(info, dict) else {}
    return out


def load_structure(root: Path) -> dict:
    p = root / "_data" / "structure.json"
    if not p.exists():
        cands = sorted((root / "_data").glob("structure_*.json"))
        if cands:
            p = cands[-1]
    if not p.exists():
        cp(f"  structure.json не найден в {root/'_data'}", C.R)
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        cp(f"  structure.json не прочитан: {e}", C.R)
        return {}


# ─── EXIF GPS из JPG ────────────────────────────────────────────────────────
def _rat_to_deg(rat) -> float:
    d = rat[0][0] / rat[0][1]
    m = rat[1][0] / rat[1][1]
    s = rat[2][0] / rat[2][1]
    return d + m/60 + s/3600


def read_gps(jpg: Path) -> dict:
    """Возвращает {lat, lon, alt, ucomment?, description?}."""
    if piexif is None:
        return {}
    try:
        exif = piexif.load(str(jpg))
    except Exception:
        return {}
    gps = exif.get("GPS", {}) or {}
    out: dict = {}
    try:
        if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
            lat = _rat_to_deg(gps[piexif.GPSIFD.GPSLatitude])
            lon = _rat_to_deg(gps[piexif.GPSIFD.GPSLongitude])
            if gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N") in (b"S", "S"):
                lat = -lat
            if gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E") in (b"W", "W"):
                lon = -lon
            out["lat"] = lat; out["lon"] = lon
        if piexif.GPSIFD.GPSAltitude in gps:
            a = gps[piexif.GPSIFD.GPSAltitude]
            alt = a[0]/a[1]
            if gps.get(piexif.GPSIFD.GPSAltitudeRef, 0) == 1:
                alt = -alt
            out["alt"] = alt
    except Exception:
        pass
    try:
        uc = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment)
        if uc:
            s = UserComment.load(uc) if UserComment else ""
            try:
                out["ucomment"] = json.loads(s)
            except Exception:
                out["ucomment_raw"] = s
    except Exception:
        pass
    try:
        d = exif.get("0th", {}).get(piexif.ImageIFD.ImageDescription)
        if d:
            out["description"] = (d.decode("utf-8", "ignore")
                                  if isinstance(d, bytes) else str(d))
    except Exception:
        pass
    return out


# ─── Спираль Фибоначчи для фото без EXIF-GPS ────────────────────────────────
def spiral_points(lat0: float, lon0: float, count: int,
                  r0: float = SPIRAL_R0_M, dr_factor: float = SPIRAL_DR_M,
                  golden_angle: float = GOLDEN_DEG
                  ) -> list[tuple[float, float, float]]:
    """Спираль Фибоначчи вокруг (lat0, lon0) с пустым центром радиуса r0.

    Возвращает count кортежей (lat, lon, alt=0.0). Детерминирована.

    φ_i = i × golden_angle (рад)
    r_i = r0 + dr_factor · √(i+1) (м)
    Δlon = r · cos(φ) / (111320 · cos(lat0))
    Δlat = r · sin(φ) / 111320
    """
    if count <= 0:
        return []
    lat0_rad = math.radians(lat0)
    m_per_deg_lon = max(LAT_M_PER_DEG * math.cos(lat0_rad), 1.0)
    phi_step_rad = math.radians(golden_angle)
    out: list[tuple[float, float, float]] = []
    for i in range(count):
        phi = i * phi_step_rad
        r = r0 + dr_factor * math.sqrt(i + 1)
        dx = r * math.cos(phi)
        dy = r * math.sin(phi)
        d_lon = dx / m_per_deg_lon
        d_lat = dy / LAT_M_PER_DEG
        out.append((
            round(lat0 + d_lat, 7),
            round(lon0 + d_lon, 7),
            0.0,
        ))
    return out


def _spiral_r_for(i: int) -> float:
    return SPIRAL_R0_M + SPIRAL_DR_M * math.sqrt(i + 1)


def _spiral_phi_for(i: int) -> float:
    return (i * GOLDEN_DEG) % 360.0


# ─── Slug / id-форматы ──────────────────────────────────────────────────────
_SLUG_RE = re.compile(r"[^A-Za-z0-9_]+")

def _slug(s: str, max_len: int = 32) -> str:
    """Транслитерация → ASCII slug, для id BU."""
    if not s:
        return "x"
    table = str.maketrans({
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh",
        "з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o",
        "п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"c",
        "ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu",
        "я":"ya"," ":"_","-":"_",
    })
    s2 = s.lower().translate(table)
    s2 = _SLUG_RE.sub("_", s2).strip("_")
    return (s2 or "x")[:max_len]


def cn_to_id_part(cn: str) -> str:
    """61:44:0050706:31 → 61_44_0050706_31"""
    return cn.replace(":", "_")


def style_id_for(kind: str, key: str) -> str:
    """Сборка Style id по правилам §A.2 spec."""
    prefix = STYLE_PREFIX[kind]
    if kind in ("zu", "oks", "room", "str", "ons"):
        # key — кадастровый номер
        return prefix + cn_to_id_part(key)
    if kind == "bu":
        return prefix + _slug(key, 48)
    if kind == "eq":
        # key — инв.№ или uuid
        if re.fullmatch(r"[A-Za-z0-9_-]+", key or ""):
            return prefix + f"inv_{_slug(key, 32)}"
        h = hashlib.sha1((key or "?").encode("utf-8")).hexdigest()[:8]
        return prefix + f"uid_{h}"
    if kind == "ben":
        return prefix + f"inn_{_slug(key, 32)}"
    if kind == "exp":
        return prefix + _slug(key, 32)
    if kind == "photo":
        return prefix + key  # уже подготовленный суффикс
    return prefix + _slug(key, 32)


# ─── Style XML ──────────────────────────────────────────────────────────────
def build_style(style_id: str, kind: str) -> str:
    """Возвращает XML <Style id="…">…</Style> для одного объекта."""
    cfg = STYLE_TABLE[kind]
    parts: list[str] = []
    if cfg.get("line"):
        parts.append(f'<LineStyle><color>{cfg["line"]}</color>'
                     f'<width>2</width></LineStyle>')
    if cfg.get("poly"):
        parts.append(f'<PolyStyle><color>{cfg["poly"]}</color>'
                     f'<fill>1</fill><outline>1</outline></PolyStyle>')
    if cfg.get("icon") and cfg.get("icon_url"):
        parts.append(f'<IconStyle><color>{cfg["icon"]}</color>'
                     f'<scale>0.9</scale>'
                     f'<Icon><href>{cfg["icon_url"]}</href></Icon>'
                     f'</IconStyle>')
        parts.append('<LabelStyle><scale>0.8</scale></LabelStyle>')
    return f'<Style id="{xml_escape(style_id)}">' + "".join(parts) + '</Style>'


def style_defaults() -> str:
    """Глобальные fallback-стили в начале документа."""
    return (
        build_style("cad_exp_default", "exp") +
        build_style("photoPin_default", "photo")
    )


# ─── KV-пары для description (без HTML) ─────────────────────────────────────
def _kv_pairs(pairs: list[tuple[str, object | None]]) -> str:
    """Пары "Ключ: значение; …" с фильтром пустых значений.

    Значения экранируются от точки-с-запятой (заменой на запятую),
    чтобы парсер пар на стороне просмотрщика не ломался.
    """
    out: list[str] = []
    for k, v in pairs:
        if v is None or v == "":
            continue
        v_safe = str(v).replace(";", ",").replace("\n", " ").strip()
        if not v_safe:
            continue
        out.append(f"{k}: {v_safe}")
    return "; ".join(out) + (";" if out else "")


def _doc_photo_pairs(docs: list[Path] | None,
                     photos: list[Path] | None) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None]] = []
    if docs:
        for i, p in enumerate(sorted(docs), 1):
            pairs.append((f"Ссылка_документ_{i}", f"docs/{p.name}"))
    if photos:
        for i, p in enumerate(sorted(photos), 1):
            pairs.append((f"Ссылка_фото_{i}", f"images/{p.name}"))
    return pairs


def _xml_meta_pairs(xml_meta: dict | None) -> list[tuple[str, str | None]]:
    """Пары из EGRN XML-выписки (07-скрипт). Порядок фиксирован."""
    if not xml_meta:
        return []
    keys = [
        ("Кадастровая стоимость", "cad_value"),
        ("Правообладатель", "holder_name"),
        ("ИНН", "holder_inn"),
        ("ОГРН", "holder_ogrn"),
        ("Вид права", "right_type"),
    ]
    return [(label, xml_meta.get(key)) for label, key in keys]


# ─── Balloon-функции (plain pairs) ──────────────────────────────────────────
def balloon_zu(cad: dict, docs: list[Path] | None,
               photos: list[Path] | None, xml_meta: dict | None = None) -> str:
    info = cad.get("_info") or cad.get("_raw_info") or {}
    pairs: list[tuple[str, object | None]] = [
        ("Кадастровый номер", cad.get("cadastral_number")),
        ("Площадь", info.get("Площадь") or cad.get("area")),
        ("Категория", info.get("Категория земель")),
        ("Разрешённое использование", info.get("Разрешённое использование")),
        ("Адрес", (xml_meta or {}).get("address") or cad.get("address")),
    ]
    pairs += _xml_meta_pairs(xml_meta)
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_oks(cad: dict, docs: list[Path] | None,
                photos: list[Path] | None, xml_meta: dict | None = None) -> str:
    info = cad.get("_info") or cad.get("_raw_info") or {}
    pairs: list[tuple[str, object | None]] = [
        ("Кадастровый номер", cad.get("cadastral_number")),
        ("Назначение", info.get("Назначение") or cad.get("purpose")),
        ("Этажность", cad.get("_floors") or info.get("Количество этажей")),
        ("Подземных этажей", info.get("Количество подземных этажей")),
        ("Год постройки", info.get("Год постройки")),
        ("Материал стен", info.get("Материал стен")),
        ("Площадь", info.get("Площадь") or cad.get("area")),
        ("Адрес", (xml_meta or {}).get("address") or cad.get("address")),
    ]
    pairs += _xml_meta_pairs(xml_meta)
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_room(cad: dict, docs: list[Path] | None,
                 photos: list[Path] | None, xml_meta: dict | None = None) -> str:
    info = cad.get("_info") or cad.get("_raw_info") or {}
    pairs: list[tuple[str, object | None]] = [
        ("Кадастровый номер", cad.get("cadastral_number")),
        ("Тип", cad.get("object_type") or info.get("Назначение")),
        ("Адрес", (xml_meta or {}).get("address") or cad.get("address")),
        ("Площадь", info.get("Площадь") or cad.get("area")),
        ("Этаж", cad.get("_floor_index") or info.get("Этаж")),
        ("Родительское здание", cad.get("parent_cad")),
    ]
    pairs += _xml_meta_pairs(xml_meta)
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_str(cad: dict, docs: list[Path] | None,
                photos: list[Path] | None, xml_meta: dict | None = None) -> str:
    info = cad.get("_info") or cad.get("_raw_info") or {}
    pairs: list[tuple[str, object | None]] = [
        ("Кадастровый номер", cad.get("cadastral_number")),
        ("Назначение", info.get("Назначение") or cad.get("purpose")),
        ("Протяжённость", info.get("Протяжённость") or info.get("Длина")),
        ("Материал", info.get("Материал")),
        ("Адрес", (xml_meta or {}).get("address") or cad.get("address")),
    ]
    pairs += _xml_meta_pairs(xml_meta)
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_ons(cad: dict, docs: list[Path] | None,
                photos: list[Path] | None, xml_meta: dict | None = None) -> str:
    info = cad.get("_info") or cad.get("_raw_info") or {}
    pairs: list[tuple[str, object | None]] = [
        ("Кадастровый номер", cad.get("cadastral_number")),
        ("Назначение", info.get("Назначение") or cad.get("purpose")),
        ("Степень готовности", info.get("Степень готовности")),
        ("Запланированная площадь", info.get("Запланированная площадь")),
        ("Адрес", (xml_meta or {}).get("address") or cad.get("address")),
    ]
    pairs += _xml_meta_pairs(xml_meta)
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_bu(bu: dict, docs: list[Path] | None,
               related_cns: list[str], beneficiary_name: str | None) -> str:
    inns = [str(x) for x in (bu.get("inns") or [])]
    pairs: list[tuple[str, object | None]] = [
        ("Бизнес-единица", bu.get("name")),
        ("Адрес", bu.get("address")),
        ("Кадастровых объектов в составе", len(related_cns) if related_cns else None),
        ("КН", ", ".join(related_cns) if related_cns else None),
        ("ИНН", ", ".join(inns) if inns else None),
        ("Бенефициар", beneficiary_name),
    ]
    pairs += _doc_photo_pairs(docs, None)
    return _kv_pairs(pairs)


def balloon_eq(eq: dict, parent_cn: str | None, parent_bu: str | None,
               docs: list[Path] | None, photos: list[Path] | None) -> str:
    pairs: list[tuple[str, object | None]] = [
        ("Оборудование", eq.get("name")),
        ("Инв.№", eq.get("inv_number_hint")),
        ("Субсчёт", eq.get("account")),
        ("Балансовая стоимость", eq.get("balance_value") or eq.get("cost")),
        ("Связан с КН", parent_cn),
        ("Связан с БУ", parent_bu),
        ("Балансодержатель", eq.get("balance_holder") or eq.get("right_type")),
        ("Этаж", eq.get("_floor_label")),
    ]
    pairs += _doc_photo_pairs(docs, photos)
    return _kv_pairs(pairs)


def balloon_ben(ben: dict, related_bus: list[str],
                docs: list[Path] | None) -> str:
    pairs: list[tuple[str, object | None]] = [
        ("Бенефициар", ben.get("name") or ben.get("full_name")),
        ("ИНН", ben.get("inn")),
        ("ОГРН", ben.get("ogrn") or ben.get("ogrnip")),
        ("КПП", ben.get("kpp")),
        ("Юр.адрес", ben.get("address") or ben.get("legal_address")),
        ("Доля владения", ben.get("share")),
        ("БУ под управлением",
         ", ".join(related_bus) if related_bus else None),
    ]
    pairs += _doc_photo_pairs(docs, None)
    return _kv_pairs(pairs)


def balloon_photo(jpg_name: str, meta: dict, cad_ref: str | None,
                  category: str | None, source: str,
                  r_meters: float | None = None,
                  phi_deg: float | None = None) -> str:
    """source ∈ {'exif','spiral_around_centroid','level_center'}"""
    ts = None
    uc = meta.get("ucomment")
    if isinstance(uc, dict):
        ts = uc.get("ts") or uc.get("DateTimeOriginal")
    pairs: list[tuple[str, object | None]] = [
        ("Файл", jpg_name),
        ("Кадастровый объект", cad_ref or "—"),
        ("Семантическая категория", category),
        ("Угол", meta.get("yaw") or meta.get("heading")),
        ("Снято", ts),
        ("Камера", meta.get("camera")),
        ("GPS высота",
         f"{meta['alt']:.1f} м" if isinstance(meta.get("alt"), (int, float)) else None),
        ("Источник координат", source),
        ("r_meters", f"{r_meters:.1f}" if r_meters is not None else None),
        ("phi_deg", f"{phi_deg:.1f}" if phi_deg is not None else None),
    ]
    return _kv_pairs(pairs)


# ─── ExtendedData ───────────────────────────────────────────────────────────
def extended_data(kvs: dict[str, object | None]) -> str:
    rows: list[str] = []
    for k, v in kvs.items():
        if v is None or v == "":
            continue
        rows.append(
            f'<Data name="{xml_escape(str(k))}">'
            f'<value>{xml_escape(str(v))}</value></Data>'
        )
    if not rows:
        return ""
    return "<ExtendedData>" + "".join(rows) + "</ExtendedData>"


# ─── Name / geometry helpers ────────────────────────────────────────────────
def name_with_cad(cn: str | None, suffix: str | None = None,
                  max_len: int = 100) -> str:
    """Name для Placemark. cn — отдельный токен формата NN:NN:N…:N…."""
    parts: list[str] = []
    if cn and CN_RE.search(cn):
        parts.append(cn)
    if suffix:
        suffix = str(suffix).strip()
        if suffix:
            current = " · ".join(parts)
            budget = max_len - (len(current) + 3)  # ' · '
            if budget > 0:
                parts.append(suffix[:budget])
    return " · ".join(parts) if parts else (cn or suffix or "—")


def _coords_str(ring: list, z: float) -> str:
    out: list[str] = []
    for p in ring:
        if not isinstance(p, list) or len(p) < 2:
            continue
        out.append(f"{float(p[0]):.7f},{float(p[1]):.7f},{z:.2f}")
    return " ".join(out)


def polygon_kml(coords: list, z: float, extrude: bool) -> str:
    """Polygon без innerBoundaryIs (несовместимо с v2.9.62 §4)."""
    if not coords:
        return ""
    rings = coords if isinstance(coords[0][0], list) else [coords]
    outer = rings[0]
    extrude_xml = "<extrude>1</extrude>" if extrude else "<extrude>0</extrude>"
    alt_mode = "relativeToGround" if extrude else "clampToGround"
    return (f"<Polygon>{extrude_xml}<altitudeMode>{alt_mode}</altitudeMode>"
            f"<outerBoundaryIs><LinearRing><coordinates>"
            f"{_coords_str(outer, z)}</coordinates></LinearRing></outerBoundaryIs>"
            f"</Polygon>")


def point_kml(lon: float, lat: float, z: float, extrude: bool) -> str:
    extrude_xml = "<extrude>1</extrude>" if extrude else "<extrude>0</extrude>"
    alt_mode = "relativeToGround" if extrude else "clampToGround"
    return (f"<Point>{extrude_xml}<altitudeMode>{alt_mode}</altitudeMode>"
            f"<coordinates>{lon:.7f},{lat:.7f},{z:.2f}</coordinates></Point>")


def folder_open(name: str, open_: bool = True) -> str:
    return (f"<Folder><name>{xml_escape(name)}</name>"
            f"<open>{1 if open_ else 0}</open>")


def placemark(name: str, descr: str, style_id: str, geom_xml: str,
              ts: str | None = None, ext_data: str | None = None) -> str:
    ts_xml = f"<TimeStamp><when>{xml_escape(ts)}</when></TimeStamp>" if ts else ""
    return (
        f"<Placemark>"
        f"<name><![CDATA[{name}]]></name>"
        f"<styleUrl>#{xml_escape(style_id)}</styleUrl>"
        f"<description><![CDATA[{descr}]]></description>"
        f"{ext_data or ''}{ts_xml}{geom_xml}"
        f"</Placemark>"
    )


# ─── Классификация КН → kind ────────────────────────────────────────────────
def classify_cad(cad: dict) -> str:
    """Возвращает kind ∈ {'zu','oks','room','str','ons'} по object_type."""
    ot = (cad.get("object_type") or "").lower()
    if "земельн" in ot:
        return "zu"
    if "помещ" in ot or "квартир" in ot or "машино-мест" in ot or "комнат" in ot:
        return "room"
    if "сооруж" in ot:
        return "str"
    if "онс" in ot or "незаверш" in ot:
        return "ons"
    if "здан" in ot:
        return "oks"
    return "oks"  # fallback


# Соответствие kind → имя Folder (для группировки)
KIND_TO_FOLDER = {
    "zu": "Земельные участки", "oks": "ОКС", "room": "Помещения",
    "str": "Сооружения", "ons": "ОНС", "bu": "Бизнес-единицы",
    "eq": "Оборудование", "ben": "Бенефициары", "exp": "Пояснения",
}


# ─── Z-координаты для 3D-extrude ────────────────────────────────────────────
def z_for_cad(kind: str, cad: dict) -> float:
    """Z-координата вершины extrude для cad_oks_/cad_room_/cad_ons_."""
    if kind == "zu":
        return 0.0
    floors = cad.get("_floors") or 1
    if kind == "room":
        # Помещение «висит» на уровне своего этажа (floor_index × 3)
        fi = cad.get("_floor_index")
        if isinstance(fi, int) and fi > 0:
            return (fi - 1) * 3.0
        return 0.0
    if kind in ("oks", "ons"):
        return floors * 3.0
    return 0.0


# ─── Photo placement (EXIF + spiral) ────────────────────────────────────────
REALTY_CATS_SET = {"Земельные_участки", "Строения", "Сооружения",
                   "Помещения", "ОНЗ"}


def _photo_tag_from_path(jpg: Path, photos_dir: Path) -> dict:
    try:
        rel = jpg.relative_to(photos_dir)
    except Exception:
        return {}
    parts = rel.parts
    if len(parts) < 2:
        return {}
    top = parts[0]
    if (top == "Недвижимость" and len(parts) >= 3
            and parts[1] in REALTY_CATS_SET):
        cn = parts[2].replace("_", ":")
        category = parts[3] if len(parts) >= 4 else None
        return {"kind": "cad", "cad": cn,
                "realty_cat": parts[1], "category": category}
    if top == "Оборудование":
        return {"kind": "eq", "eq": parts[1]}
    if top == "Бизнес_единицы":
        return {"kind": "bu", "bu": parts[1]}
    return {}


def place_photos(photos_dir: Path, by_cn: dict[str, dict],
                 st: dict, no_spiral: bool = False
                 ) -> list[tuple[Path, dict, dict, str, float | None, float | None]]:
    """Возвращает список (jpg, meta, tag, source, r_m, phi_deg).

    Координаты:
      • из EXIF GPS, если есть → source='exif'.
      • для tag.kind='cad' без GPS → спираль вокруг центроида КН →
        source='spiral_around_centroid' (r_m, phi_deg заполнены).
      • для tag.kind='eq' без GPS → центроид связанного КН + level_z →
        source='level_center'.
      • для tag.kind='bu' без GPS → центроид первого связанного КН →
        source='spiral_around_centroid'.
      • если no_spiral=True или центроид недоступен → фото пропускается.
    """
    out: list[tuple[Path, dict, dict, str, float | None, float | None]] = []
    by_cad_no_gps: dict[str, list[Path]] = {}
    by_eq_no_gps: dict[str, list[Path]] = {}
    by_bu_no_gps: dict[str, list[Path]] = {}
    meta_cache: dict[Path, dict] = {}
    tag_cache: dict[Path, dict] = {}

    for jpg in sorted(photos_dir.rglob("*.jpg")):
        tag = _photo_tag_from_path(jpg, photos_dir)
        meta = read_gps(jpg)
        meta_cache[jpg] = meta
        tag_cache[jpg] = tag
        if "lat" in meta and "lon" in meta:
            out.append((jpg, meta, tag, "exif", None, None))
            continue
        if no_spiral:
            continue
        if tag.get("kind") == "cad":
            by_cad_no_gps.setdefault(tag["cad"], []).append(jpg)
        elif tag.get("kind") == "eq":
            by_eq_no_gps.setdefault(tag["eq"], []).append(jpg)
        elif tag.get("kind") == "bu":
            by_bu_no_gps.setdefault(tag["bu"], []).append(jpg)

    # Спираль для CAD-фото
    for cn, jpgs in by_cad_no_gps.items():
        cad = by_cn.get(cn) or {}
        cen = _geom_centroid(cad.get("_geom"))
        if cen is None:
            continue
        lon0, lat0 = cen
        spiral = spiral_points(lat0, lon0, len(jpgs))
        for i, (jpg, (lat_i, lon_i, _)) in enumerate(zip(sorted(jpgs), spiral)):
            meta = dict(meta_cache[jpg])
            meta["lat"] = lat_i
            meta["lon"] = lon_i
            meta["alt"] = 0.0
            out.append((jpg, meta, tag_cache[jpg], "spiral_around_centroid",
                        _spiral_r_for(i), _spiral_phi_for(i)))

    # Eq-фото: центроид связанного КН + level_z
    for eq_inv, jpgs in by_eq_no_gps.items():
        eq = next((e for e in (st.get("equipment", []) or [])
                   if str(e.get("inv_number_hint") or "") == eq_inv), None)
        if not eq:
            continue
        cid = (eq.get("links") or {}).get("cadastre_id")
        cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
        if not cad or not cad.get("_geom"):
            continue
        cen = _geom_centroid(cad["_geom"])
        if cen is None:
            continue
        lon0, lat0 = cen
        spiral = spiral_points(lat0, lon0, len(jpgs))
        for i, (jpg, (lat_i, lon_i, _)) in enumerate(zip(sorted(jpgs), spiral)):
            meta = dict(meta_cache[jpg])
            meta["lat"] = lat_i
            meta["lon"] = lon_i
            meta["alt"] = 0.0
            out.append((jpg, meta, tag_cache[jpg], "spiral_around_centroid",
                        _spiral_r_for(i), _spiral_phi_for(i)))

    # BU-фото: центроид первого связанного КН
    for bu_slug, jpgs in by_bu_no_gps.items():
        bu = next((b for b in (st.get("business_units", []) or [])
                   if _slug(b.get("name") or "", 48) == bu_slug
                   or b.get("id") == bu_slug), None)
        if not bu:
            continue
        related_cns: list[str] = []
        for cid in bu.get("cadastre_ids") or []:
            cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
            if cad and cad.get("_geom"):
                related_cns.append(cad.get("cadastral_number"))
        if not related_cns:
            continue
        cad0 = by_cn.get(related_cns[0])
        cen = _geom_centroid(cad0.get("_geom") if cad0 else None)
        if cen is None:
            continue
        lon0, lat0 = cen
        spiral = spiral_points(lat0, lon0, len(jpgs))
        for i, (jpg, (lat_i, lon_i, _)) in enumerate(zip(sorted(jpgs), spiral)):
            meta = dict(meta_cache[jpg])
            meta["lat"] = lat_i
            meta["lon"] = lon_i
            meta["alt"] = 0.0
            out.append((jpg, meta, tag_cache[jpg], "spiral_around_centroid",
                        _spiral_r_for(i), _spiral_phi_for(i)))

    return out


# ─── Главная сборка ─────────────────────────────────────────────────────────
def build_kmz(root: Path, no_spiral: bool = False) -> Path:
    st = load_structure(root)
    if not st:
        cp("  пустой structure — KMZ будет минимальным.", C.Y)
    cache = load_nspd_cache(root)

    # Объединённый «вид» по КН
    by_cn: dict[str, dict] = {}
    for cad in st.get("cadastre_objects", []):
        cn = cad.get("cadastral_number")
        if not cn:
            continue
        info = cache.get(cn) or cad.get("_raw_info") or {}
        geom = _extract_geom(info) or _extract_geom(cad.get("_raw_info") or {})
        floors = _floors(info)
        by_cn[cn] = {**cad, "_geom": geom, "_floors": floors, "_info": info}

    # ── Документы ─────────────────────────────────────────────────────────
    docs_dir = root / "Документы_JPG"
    doc_by_cad: dict[str, list[Path]] = {}
    doc_by_inn: dict[str, list[Path]] = {}
    cad_doc_re = re.compile(
        r"^(egrn|svid|tehpasp|tehplan|doc)_(\d{2})_(\d{2})_(\d{1,8})_(\d{1,8})"
    )
    if docs_dir.exists():
        for jpg in sorted(docs_dir.rglob("*.jpg")):
            m = cad_doc_re.search(jpg.name)
            if m:
                cn = f"{m.group(2)}:{m.group(3)}:{m.group(4)}:{m.group(5)}"
                doc_by_cad.setdefault(cn, []).append(jpg)
                continue
            m = re.search(r"egr(?:ul|ip)_inn(?:fl)?(\d{10,12})", jpg.name)
            if m:
                doc_by_inn.setdefault(m.group(1), []).append(jpg)

    # XML-выписки ЕГРН
    xml_facts: dict[str, dict] = {}
    xfp = root / "_data" / "egrn_xml.json"
    if xfp.exists():
        try:
            xml_facts = json.loads(xfp.read_text(encoding="utf-8"))
        except Exception:
            xml_facts = {}

    # ── Фото ──────────────────────────────────────────────────────────────
    photos_dir = root / "Фотографии"
    photos: list[tuple[Path, dict, dict, str, float | None, float | None]] = []
    if photos_dir.exists():
        photos = place_photos(photos_dir, by_cn, st, no_spiral=no_spiral)

    # photos_by_cad / _eq / _bu — для упоминания файлов в баллонах объектов
    photos_by_cad: dict[str, list[Path]] = {}
    photos_by_eq: dict[str, list[Path]] = {}
    photos_by_bu: dict[str, list[Path]] = {}
    for jpg, _meta, tag, _src, _r, _phi in photos:
        if tag.get("kind") == "cad":
            photos_by_cad.setdefault(tag["cad"], []).append(jpg)
        elif tag.get("kind") == "eq":
            photos_by_eq.setdefault(tag["eq"], []).append(jpg)
        elif tag.get("kind") == "bu":
            photos_by_bu.setdefault(tag["bu"], []).append(jpg)

    # КН → список ИНН (для подмешивания ЕГРЮЛ/ЕГРИП в баллон каждого объекта)
    cad_to_inns: dict[str, list[str]] = {}
    bu_to_cns: dict[str, list[str]] = {}  # slug BU → список КН
    bu_to_ben: dict[str, str] = {}        # slug BU → имя бенефициара
    for bu in st.get("business_units", []) or []:
        bu_slug = _slug(bu.get("name") or bu.get("id") or "bu", 48)
        bu_to_cns[bu_slug] = []
        for cid in bu.get("cadastre_ids") or []:
            cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
            if not cad:
                continue
            cn0 = cad.get("cadastral_number")
            bu_to_cns[bu_slug].append(cn0)
            for inn in bu.get("inns") or []:
                cad_to_inns.setdefault(cn0, []).append(str(inn))
        owners = bu.get("owners") or []
        if owners and isinstance(owners, list):
            bu_to_ben[bu_slug] = str(owners[0].get("name")
                                     or owners[0].get("full_name") or "")

    # ── Группировка КН по kind ────────────────────────────────────────────
    groups_cad: dict[str, list[tuple[str, dict]]] = {
        "zu": [], "oks": [], "room": [], "str": [], "ons": [],
    }
    for cn, cad in by_cn.items():
        kind = classify_cad(cad)
        groups_cad[kind].append((cn, cad))

    # ── Собираем стили (динамически) ──────────────────────────────────────
    styles_xml: list[str] = [style_defaults()]
    seen_style_ids: set[str] = {"cad_exp_default", "photoPin_default"}

    def add_style(style_id: str, kind: str):
        if style_id in seen_style_ids:
            return
        seen_style_ids.add(style_id)
        styles_xml.append(build_style(style_id, kind))

    # Заранее создаём стили для всех КН-объектов и БУ/EQ/BEN
    for kind, items in groups_cad.items():
        for cn, _cad in items:
            add_style(style_id_for(kind, cn), kind)
    for bu in st.get("business_units", []) or []:
        add_style(style_id_for("bu", bu.get("name") or bu.get("id") or "bu"), "bu")
    for eq in st.get("equipment", []) or []:
        key = eq.get("inv_number_hint") or eq.get("id") or eq.get("name") or "?"
        add_style(style_id_for("eq", str(key)), "eq")
    # Бенефициары — собираем из business_units[].owners[]
    beneficiaries: list[dict] = []
    seen_ben_keys: set[str] = set()
    for bu in st.get("business_units", []) or []:
        for owner in bu.get("owners") or []:
            key = str(owner.get("inn") or owner.get("ogrn")
                      or owner.get("name") or "?")
            if key in seen_ben_keys:
                continue
            seen_ben_keys.add(key)
            beneficiaries.append(owner)
            add_style(style_id_for("ben", key), "ben")
    # Фото — Style id зависит от КН-привязки и индекса
    photo_style_ids: dict[Path, str] = {}
    photo_counter_by_cn: dict[str, int] = {}
    loose_counter = [0]
    for jpg, _meta, tag, _src, _r, _phi in photos:
        if tag.get("kind") == "cad":
            cn = tag["cad"]
            idx = photo_counter_by_cn.get(cn, 0)
            photo_counter_by_cn[cn] = idx + 1
            sid = STYLE_PREFIX["photo"] + cn_to_id_part(cn) + f"_{idx}"
        else:
            h = hashlib.sha1(jpg.name.encode("utf-8")).hexdigest()[:8]
            idx = loose_counter[0]
            loose_counter[0] += 1
            sid = STYLE_PREFIX["photo"] + f"loose_{h}_{idx}"
        photo_style_ids[jpg] = sid
        add_style(sid, "photo")

    # ── Сборка KML ────────────────────────────────────────────────────────
    ent = st.get("enterprise", {}) or {}
    kml_name = f"{ent.get('name_short') or ent.get('name') or root.name} — KMZ"
    # ts фиксированный по дате генерации, но для идемпотентности — округлим
    # до дня (так повторный запуск в тот же день даёт идентичный sha256).
    today_iso = datetime.now(timezone.utc).date().isoformat() + "T00:00:00Z"

    doc_header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<Document>\n'
        f'  <name><![CDATA[{kml_name}]]></name>\n'
        f'  <description><![CDATA[Сгенерировано {GENERATOR_NAME} '
        f'(KML schema {KML_SCHEMA_VERSION})]]></description>\n'
        '  <atom:author>\n'
        f'    <atom:name>{xml_escape(GENERATOR_NAME)}</atom:name>\n'
        '  </atom:author>\n'
        + extended_data({
            "kml_schema_version": KML_SCHEMA_VERSION,
            "generator": GENERATOR_NAME,
            "generated_at": today_iso,
        }) + "\n"
    )

    out: list[str] = [doc_header]
    out.extend(styles_xml)

    # 1. КН-объекты по 5 группам (zu/oks/room/str/ons)
    for folder_name in ("Земельные участки", "ОКС", "Помещения",
                        "Сооружения", "ОНС"):
        kind = FOLDER_KIND[folder_name]
        items = groups_cad[kind]
        if not items:
            continue
        out.append(folder_open(f"{folder_name} ({len(items)})", True))
        for cn, cad in items:
            geom = cad.get("_geom") or {}
            if not geom:
                continue
            docs = list(doc_by_cad.get(cn, []))
            for inn in cad_to_inns.get(cn, []):
                docs.extend(doc_by_inn.get(inn, []))
            xml_meta = xml_facts.get(cn)
            if kind == "zu":
                balloon = balloon_zu(cad, docs, photos_by_cad.get(cn), xml_meta)
            elif kind == "oks":
                balloon = balloon_oks(cad, docs, photos_by_cad.get(cn), xml_meta)
            elif kind == "room":
                balloon = balloon_room(cad, docs, photos_by_cad.get(cn), xml_meta)
            elif kind == "str":
                balloon = balloon_str(cad, docs, photos_by_cad.get(cn), xml_meta)
            else:  # ons
                balloon = balloon_ons(cad, docs, photos_by_cad.get(cn), xml_meta)
            short_addr = cad.get("address")
            if short_addr and len(short_addr) > 40:
                short_addr = short_addr[:37] + "…"
            name = name_with_cad(cn, short_addr)
            z = z_for_cad(kind, cad)
            extrude = kind in ("oks", "room", "ons")
            if geom["type"] == "Polygon":
                geom_xml = polygon_kml(geom["coords"], z, extrude)
            else:
                lon, lat = geom["coords"][0]
                geom_xml = point_kml(lon, lat, z, extrude)
            ext = extended_data({
                "object_type": kind,
                "cad_number": cn,
                "z_meters_top": z if extrude else None,
                "z_meters_bottom": 0.0 if extrude else None,
                "floors_above": cad.get("_floors") if kind in ("oks", "ons") else None,
                "parent_cad": cad.get("parent_cad") if kind == "room" else None,
                "schema_version": KML_SCHEMA_VERSION,
            })
            out.append(placemark(name, balloon, style_id_for(kind, cn),
                                 geom_xml, ext_data=ext))
        out.append("</Folder>")

    # 2. Бизнес-единицы — Point на центроиде первого связанного КН
    bus = st.get("business_units", []) or []
    bu_items: list[tuple[dict, tuple[float, float] | None, list[str]]] = []
    for bu in bus:
        related_cns: list[str] = []
        first_cen: tuple[float, float] | None = None
        for cid in bu.get("cadastre_ids") or []:
            cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
            if not cad:
                continue
            related_cns.append(cad.get("cadastral_number"))
            if first_cen is None:
                first_cen = _geom_centroid(cad.get("_geom"))
        bu_items.append((bu, first_cen, related_cns))
    bu_with_geom = [t for t in bu_items if t[1] is not None]
    if bu_with_geom:
        out.append(folder_open(f"Бизнес-единицы ({len(bu_with_geom)})", False))
        for bu, cen, related_cns in bu_with_geom:
            bu_slug = _slug(bu.get("name") or bu.get("id") or "bu", 48)
            inns = [str(x) for x in (bu.get("inns") or [])]
            docs: list[Path] = []
            for inn in inns:
                docs.extend(doc_by_inn.get(inn, []))
            balloon = balloon_bu(bu, docs, related_cns, bu_to_ben.get(bu_slug))
            name = (bu.get("name") or "БУ")[:100]
            lon, lat = cen
            geom_xml = point_kml(lon, lat, 0.0, False)
            ext = extended_data({
                "object_type": "bu",
                "bu_id": bu_slug,
                "ben_inn": ", ".join(inns) if inns else None,
                "schema_version": KML_SCHEMA_VERSION,
            })
            out.append(placemark(name, balloon, style_id_for("bu", name),
                                 geom_xml, ext_data=ext))
        out.append("</Folder>")

    # 3. Оборудование
    eqs = st.get("equipment", []) or []
    eq_placeable: list[tuple[dict, tuple[float, float], float, str, str | None]] = []
    for eq in eqs:
        cid = (eq.get("links") or {}).get("cadastre_id")
        if not cid:
            continue
        cad = next((c for c in by_cn.values() if c.get("id") == cid), None)
        if not cad or not cad.get("_geom"):
            continue
        cen = _geom_centroid(cad["_geom"])
        if cen is None:
            continue
        # level_idx — берём минимум из links.level_ids, если есть; иначе 1
        level_ids = (eq.get("links") or {}).get("level_ids") or []
        level_idx = 1
        if level_ids and isinstance(level_ids[0], dict):
            # формат [{level_index: …}, …]
            try:
                level_idx = min(int(li.get("level_index", 1)) for li in level_ids)
            except Exception:
                level_idx = 1
        z = max(0.0, (level_idx - 1) * 3.0)
        eq_placeable.append((eq, cen, z, cad.get("cadastral_number"),
                             None))  # parent_bu заполним ниже
    # parent_bu для каждого оборудования
    eq_to_bu: dict[str, str] = {}
    for bu in bus:
        bu_name = bu.get("name") or ""
        for eqid in bu.get("equipment_ids") or []:
            eq_to_bu[str(eqid)] = bu_name
    if eq_placeable:
        out.append(folder_open(f"Оборудование ({len(eq_placeable)})", False))
        for eq, (lon, lat), z, parent_cn, _ in eq_placeable:
            parent_bu = eq_to_bu.get(str(eq.get("id") or ""))
            eq_key = str(eq.get("inv_number_hint") or eq.get("id")
                         or eq.get("name") or "?")
            docs: list[Path] = []
            eq_photos = photos_by_eq.get(str(eq.get("inv_number_hint") or ""), [])
            balloon = balloon_eq(eq, parent_cn, parent_bu, docs, eq_photos)
            name = (eq.get("name") or "оборудование")[:80]
            extrude = z > 0
            geom_xml = point_kml(lon, lat, z, extrude)
            ext = extended_data({
                "object_type": "eq",
                "cad_number": parent_cn,
                "bu_id": _slug(parent_bu, 48) if parent_bu else None,
                "z_meters_top": z if extrude else None,
                "z_source": "level",
                "schema_version": KML_SCHEMA_VERSION,
            })
            out.append(placemark(name, balloon, style_id_for("eq", eq_key),
                                 geom_xml, ext_data=ext))
        out.append("</Folder>")

    # 4. Бенефициары — без геометрии или с геокодированным юр.адресом
    #    (геокодирование выходит за рамки v2 — кладём без <Point>)
    if beneficiaries:
        out.append(folder_open(f"Бенефициары ({len(beneficiaries)})", False))
        for ben in beneficiaries:
            ben_key = str(ben.get("inn") or ben.get("ogrn")
                          or ben.get("name") or "?")
            related_bus = [bu.get("name") for bu in bus
                           if any(o.get("inn") == ben.get("inn")
                                  for o in (bu.get("owners") or []))
                           and bu.get("name")]
            docs: list[Path] = []
            inn = ben.get("inn")
            if inn:
                docs.extend(doc_by_inn.get(str(inn), []))
            balloon = balloon_ben(ben, related_bus, docs)
            name = (ben.get("name") or ben.get("full_name") or "ЮЛ/ФЛ")[:100]
            # Без <Point>: Placemark в дереве, без точки на карте
            ext = extended_data({
                "object_type": "ben",
                "ben_inn": ben.get("inn"),
                "schema_version": KML_SCHEMA_VERSION,
            })
            out.append(placemark(name, balloon, style_id_for("ben", ben_key),
                                 "", ext_data=ext))
        out.append("</Folder>")

    # 5. Фотографии: подпапки по физической структуре
    if photos:
        photo_groups: dict[str, list[tuple]] = {
            "Недвижимость": [], "Оборудование": [], "Бизнес_единицы": [],
            "Не_распределено": [],
        }
        for item in photos:
            t = item[2].get("kind")
            if t == "cad":
                photo_groups["Недвижимость"].append(item)
            elif t == "eq":
                photo_groups["Оборудование"].append(item)
            elif t == "bu":
                photo_groups["Бизнес_единицы"].append(item)
            else:
                photo_groups["Не_распределено"].append(item)
        out.append(folder_open(f"Фотографии ({len(photos)})", True))
        for sub_name, items in photo_groups.items():
            if not items:
                continue
            out.append(folder_open(f"{sub_name} ({len(items)})", False))
            for jpg, meta, tag, source, r_m, phi_deg in items:
                cad_ref = tag.get("cad") if tag.get("kind") == "cad" else None
                category = tag.get("category")
                balloon = balloon_photo(jpg.name, meta, cad_ref, category,
                                        source, r_m, phi_deg)
                lat = meta["lat"]; lon = meta["lon"]
                alt = float(meta.get("alt") or 0.0)
                ts = None
                uc = meta.get("ucomment")
                if isinstance(uc, dict):
                    ts = uc.get("ts") or uc.get("DateTimeOriginal")
                geom_xml = point_kml(lon, lat, alt, alt > 0)
                ext = extended_data({
                    "object_type": "photo",
                    "cad_number": cad_ref,
                    "z_source": source,
                    "schema_version": KML_SCHEMA_VERSION,
                })
                out.append(placemark(jpg.name, balloon,
                                     photo_style_ids[jpg], geom_xml,
                                     ts=ts, ext_data=ext))
            out.append("</Folder>")
        out.append("</Folder>")

    out.append("</Document></kml>\n")
    kml_text = "".join(out)

    # ── Сборка KMZ ────────────────────────────────────────────────────────
    exp_dir = root / "kmz-kml"
    exp_dir.mkdir(parents=True, exist_ok=True)
    kmz = exp_dir / "project.kmz"
    tmp = kmz.with_suffix(".kmz.tmp")
    zinfo_date = (2025, 1, 1, 0, 0, 0)  # идемпотентность

    used_photos: set[Path] = {p for p, _m, _t, _s, _r, _f in photos}
    for lst in photos_by_cad.values():
        used_photos.update(lst)
    for lst in photos_by_eq.values():
        used_photos.update(lst)
    for lst in photos_by_bu.values():
        used_photos.update(lst)

    all_docs: set[Path] = set()
    for lst in doc_by_cad.values():
        all_docs.update(lst)
    for lst in doc_by_inn.values():
        all_docs.update(lst)

    graph_html = root / "_data" / "graph.html"
    if not graph_html.exists():
        graph_html = root / "html" / "graph.html"
    if not graph_html.exists():
        candidates = sorted(
            (root / "_data").glob("graph_*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            graph_html = candidates[0]

    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zi = zipfile.ZipInfo("doc.kml", date_time=zinfo_date)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, kml_text)
        for jpg in sorted(used_photos):
            zi = zipfile.ZipInfo(f"images/{jpg.name}", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, jpg.read_bytes())
        for p in sorted(all_docs):
            zi = zipfile.ZipInfo(f"docs/{p.name}", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, p.read_bytes())
        if graph_html.exists():
            zi = zipfile.ZipInfo("graph.html", date_time=zinfo_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, graph_html.read_bytes())

    tmp.replace(kmz)
    return kmz


# ─── CLI ────────────────────────────────────────────────────────────────────
def main() -> None:
    cp("=" * 64, C.B)
    cp(" Build KMZ — pirushin_sosn_rocha_08_build_kmz v2 (schema 2.0)", C.B)
    cp("=" * 64, C.B)

    ap = argparse.ArgumentParser(description="Сборка KMZ v2.10.0")
    ap.add_argument("--root", help=r"Путь к проекту (D:\ОБЪЕКТЫ\<Название>)")
    ap.add_argument("--no-spiral", action="store_true",
                    help="Фото без EXIF-GPS — пропускать (поведение v1)")
    args = ap.parse_args()

    raw = args.root
    if not raw:
        raw = input("\nПуть к проекту (D:\\ОБЪЕКТЫ\\<Название>): ").strip()
    if not raw:
        cp("Путь не указан — выход.", C.R)
        sys.exit(1)
    root = Path(raw)
    if not root.exists():
        cp(f"Папка не найдена: {root}", C.R)
        sys.exit(1)

    cp(f"\nСбор KMZ из {root}", C.CY)
    kmz = build_kmz(root, no_spiral=args.no_spiral)
    sz = kmz.stat().st_size / 1024
    cp(f"\nГотово: {kmz}  ({sz:.1f} КБ)", C.G)
    cp("Совместимо с https://romanbabenkorostov-ux.github.io/ekcelo/ "
       "(v2.9.62 fallback) и v2.10.0.", C.CY)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cp("\nПрервано.", C.Y)
