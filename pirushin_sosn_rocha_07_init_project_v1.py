#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pirushin_sosn_rocha_07_init_project_v1.py

Инициализация GOLDEN_PATH-структуры проекта объекта:

    D:\\ОБЪЕКТЫ\\<Название_проекта>\\
        _data/         — входы и кеш (osv.xlsx, structure.json, nspd_cache, db)
        _exports/      — артефакты (project.kmz, project.xlsx, graph.html)
        00_Нераспределенные/
        01_Земельные_участки/  02_Здания/  03_Сооружения/
        04_Помещения/  05_ОНС/
        06_Бизнес_единицы/     07_Оборудование/
        08_Фотографии/         (централизованно — отдаваема одной папкой)
            00_Нераспределенные/  По_объектам/<КН>/  По_оборудованию/<inv>/  По_BU/<bu>/
        09_Документы_JPG/      (выписки, конвертированные в JPG + EXIF)
            ЕГРЮЛ/  ЕГРИП/  ЕГРН/  Прочее/
        10_Выписки_PDF/        (исходники до конвертации)
            ЕГРЮЛ/  ЕГРИП/  ЕГРН/  Прочее/

Дополнительно:
  • Опц. конвертирует все PDF из 10_Выписки_PDF/ → 09_Документы_JPG/ с
    машиночитаемыми именами (`egrul_inn<ИНН>_p01.jpg`, `egrn_<КН>_p01.jpg` …).
  • Если в _data/structure.json есть привязка ИНН↔BU↔КН и для КН найдены
    координаты — дописывает в EXIF JPG: GPS lat/lon (центроид связанного
    объекта), ImageDescription, UserComment={JSON для машинной сшивки}.

Зависимости:  PyMuPDF (fitz), Pillow, piexif

Python 3.13+, Windows 10.
"""

from __future__ import annotations
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Опциональные импорты — скрипт умеет создавать дерево даже без них
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import piexif
    from piexif.helper import UserComment
except ImportError:
    piexif = None
    UserComment = None


# ─── Цветной вывод (Windows ANSI) ───────────────────────────────────────────
class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; CY = "\033[96m"; B = "\033[1m"; X = "\033[0m"

def cp(t="", c=""): print(f"{c}{t}{C.X}" if c else t)


# ─── Структура папок ────────────────────────────────────────────────────────
DIRS = [
    "_data",
    "_data/nspd_cache",
    "_exports",
    "00_Нераспределенные",
    "01_Земельные_участки",
    "02_Здания",
    "03_Сооружения",
    "04_Помещения",
    "05_ОНС",
    "06_Бизнес_единицы",
    "07_Оборудование",
    "08_Фотографии",
    "08_Фотографии/00_Нераспределенные",
    "08_Фотографии/По_объектам",
    "08_Фотографии/По_оборудованию",
    "08_Фотографии/По_BU",
    "09_Документы_JPG",
    "09_Документы_JPG/ЕГРЮЛ",
    "09_Документы_JPG/ЕГРИП",
    "09_Документы_JPG/ЕГРН",
    "09_Документы_JPG/Прочее",
    "10_Выписки_PDF",
    "10_Выписки_PDF/ЕГРЮЛ",
    "10_Выписки_PDF/ЕГРИП",
    "10_Выписки_PDF/ЕГРН",
    "10_Выписки_PDF/Прочее",
]

README = """# {name}

Структура GOLDEN_PATH (создана pirushin_sosn_rocha_07_init_project_v1.py).

Поток данных:
  10_Выписки_PDF/  → (скрипт 07) → 09_Документы_JPG/  (EXIF: GPS, UserComment JSON)
  _data/osv.xlsx   → (скрипт 052) → _data/structure.json
  _data/structure.json → (скрипт 04_nspd_graph) → _data/graph.html
  всё выше + 08_Фотографии/ → (скрипт 08) → _exports/project.kmz

KMZ совместим с Google Earth Pro и https://romanbabenkorostov-ux.github.io/ekcelo/

Машиночитаемые имена документов:
  ЕГРЮЛ:  egrul_inn<ИНН>_p<NN>.jpg
  ЕГРИП:  egrip_innfl<ИНН>_p<NN>.jpg
  ЕГРН:   egrn_<КН с _>_p<NN>.jpg            (напр. egrn_61_44_0050706_31_p01.jpg)
  Прочее: doc_<slug>_p<NN>.jpg

EXIF UserComment (JSON) у каждого JPG-документа:
  {{"app":"ekcelo","kind":"egrul|egrip|egrn|doc",
    "inn":"...","cad":"...","obj_id":"...","bu_id":"..."}}
"""

# Регэкспы для распознавания имени исходного PDF
INN_UL_RE  = re.compile(r"(?<!\d)(\d{10})(?!\d)")           # 10 цифр — ЮЛ
INN_FL_RE  = re.compile(r"(?<!\d)(\d{12})(?!\d)")           # 12 цифр — ФЛ/ИП
CN_RE      = re.compile(r"(\d{2}:\d{2}:\d{1,8}:\d{1,8})")
SLUG_RE    = re.compile(r"[^A-Za-zА-Яа-я0-9._-]+")

def slugify(s: str) -> str:
    return SLUG_RE.sub("_", s).strip("_").lower() or "x"

def cad_to_token(cn: str) -> str:
    return cn.replace(":", "_").replace("/", "-")


# ─── Создание структуры ─────────────────────────────────────────────────────
def make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    rdm = root / "README.md"
    if not rdm.exists():
        rdm.write_text(README.format(name=root.name), encoding="utf-8")
    # Пустой sqlite-плейсхолдер (создаст 052 / другие скрипты)
    db = root / "_data" / "project.db"
    if not db.exists():
        db.touch()


# ─── Классификация исходного PDF по имени файла + пути ─────────────────────
def classify_pdf(pdf: Path) -> dict:
    """
    Возвращает: {"kind": "egrul|egrip|egrn|doc",
                 "inn": str|None, "cad": str|None, "slug": str}
    """
    name = pdf.stem
    parent = pdf.parent.name.lower()
    text = name + " " + parent

    cad = None
    m = CN_RE.search(text)
    if m:
        cad = m.group(1)

    # Сначала смотрим парент-папку
    kind = None
    if "егрюл" in parent or "egrul" in parent:
        kind = "egrul"
    elif "егрип" in parent or "egrip" in parent:
        kind = "egrip"
    elif "егрн" in parent or "кадастр" in parent or "egrn" in parent or cad:
        kind = "egrn"

    inn = None
    m10 = INN_UL_RE.search(name)
    m12 = INN_FL_RE.search(name)
    if m12 and (kind == "egrip" or not kind):
        inn = m12.group(1)
        kind = kind or "egrip"
    elif m10 and (kind == "egrul" or not kind):
        inn = m10.group(1)
        kind = kind or "egrul"

    if not kind:
        kind = "doc"

    return {"kind": kind, "inn": inn, "cad": cad, "slug": slugify(name)[:40]}


def target_name(meta: dict, page: int) -> str:
    p = f"p{page:02d}"
    if meta["kind"] == "egrul" and meta["inn"]:
        return f"egrul_inn{meta['inn']}_{p}.jpg"
    if meta["kind"] == "egrip" and meta["inn"]:
        return f"egrip_innfl{meta['inn']}_{p}.jpg"
    if meta["kind"] == "egrn" and meta["cad"]:
        return f"egrn_{cad_to_token(meta['cad'])}_{p}.jpg"
    return f"doc_{meta['slug']}_{p}.jpg"


def target_dir(root: Path, kind: str) -> Path:
    return root / "09_Документы_JPG" / {
        "egrul": "ЕГРЮЛ", "egrip": "ЕГРИП", "egrn": "ЕГРН"
    }.get(kind, "Прочее")


# ─── EXIF: запись GPS + UserComment + ImageDescription ──────────────────────
def deg_to_rational(d: float):
    """[(deg,1),(min,1),(sec,100)] — формат GPS-rational."""
    a = abs(d)
    deg = int(a)
    minf = (a - deg) * 60
    mins = int(minf)
    sec = round((minf - mins) * 60 * 100)
    return [(deg, 1), (mins, 1), (sec, 100)]

def write_exif(jpg: Path, lat: float | None, lon: float | None,
               alt: float | None, descr: str, ucomment: dict) -> None:
    if piexif is None:
        return
    try:
        exif = piexif.load(str(jpg))
    except Exception:
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    exif["0th"][piexif.ImageIFD.ImageDescription] = descr.encode("utf-8", "ignore")
    exif["0th"][piexif.ImageIFD.Software] = b"ekcelo-07-init"
    exif["Exif"][piexif.ExifIFD.UserComment] = UserComment.dump(
        json.dumps(ucomment, ensure_ascii=False), encoding="unicode"
    )

    if lat is not None and lon is not None:
        gps = {
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: deg_to_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: deg_to_rational(lon),
        }
        if alt is not None:
            gps[piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
            gps[piexif.GPSIFD.GPSAltitude] = (int(round(abs(alt) * 100)), 100)
        exif["GPS"] = gps

    try:
        piexif.insert(piexif.dump(exif), str(jpg))
    except Exception as e:
        cp(f"    [exif] не записан: {e}", C.Y)


# ─── Координаты КН из structure.json + NSPD cache ──────────────────────────
def _centroid(coords: list) -> tuple[float, float] | None:
    """Полигон [[lon,lat], ...] → (lat, lon). Поддерживает вложенные кольца."""
    pts: list[tuple[float, float]] = []
    def walk(v):
        if isinstance(v, list) and v and isinstance(v[0], (int, float)) and len(v) >= 2:
            pts.append((float(v[0]), float(v[1])))
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(coords)
    if not pts: return None
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return lat, lon

def build_index(root: Path) -> dict:
    """
    Индексы для геопривязки:
      idx["cad"][КН]      → {"lat":..,"lon":..,"alt":..,"obj_id":..,"address":..,"object_type":..}
      idx["inn"][ИНН]     → {"bu_id":..,"name":..,"lat":..,"lon":..}  (центроид всех КН этого ИНН)
      idx["structure"]    → весь structure.json (или {})
    """
    idx = {"cad": {}, "inn": {}, "structure": {}}
    st_path = root / "_data" / "structure.json"
    if not st_path.exists():
        # пробуем найти structure_*.json
        cand = sorted((root / "_data").glob("structure_*.json"))
        if cand: st_path = cand[-1]
    if not st_path.exists():
        return idx
    try:
        st = json.loads(st_path.read_text(encoding="utf-8"))
    except Exception as e:
        cp(f"  structure.json не прочитан: {e}", C.Y); return idx
    idx["structure"] = st

    cache_dir = root / "_data" / "nspd_cache"
    cad_geom: dict[str, dict] = {}
    if cache_dir.exists():
        for jf in cache_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Формат 052: payload — словарь {category: {cn: {...}}}
            for _, by_cn in (data.items() if isinstance(data, dict) else []):
                if not isinstance(by_cn, dict): continue
                for cn, rec in by_cn.items():
                    info = (rec or {}).get("info", {}) if isinstance(rec, dict) else {}
                    cad_geom[cn] = _extract_geom_from_info(info)

    for cad in st.get("cadastre_objects", []):
        cn = cad.get("cadastral_number")
        if not cn: continue
        g = cad_geom.get(cn) or _extract_geom_from_info(cad.get("_raw_info", {}) or {})
        floors = _floors_from_info(cad.get("_raw_info", {}) or {})
        alt = (floors or 0) * 3.0 if cad.get("object_type", "").lower() != "земельный участок" else 0.0
        idx["cad"][cn] = {
            "lat": g.get("lat"), "lon": g.get("lon"), "alt": alt,
            "obj_id": cad.get("id"),
            "address": cad.get("address"),
            "object_type": cad.get("object_type"),
            "polygon": g.get("polygon"),
        }

    # ИНН → BU центроид: возьмём из бизнес-единиц, если в них есть addr и
    # привязанные cadastre_ids; в structure 052 ИНН-связи нет — заполнится позднее.
    for bu in st.get("business_units", []):
        bu_id = bu.get("id")
        cad_ids = bu.get("cadastre_ids") or []
        pts = []
        for cid in cad_ids:
            cad = next((c for c in st.get("cadastre_objects", []) if c.get("id") == cid), None)
            if not cad: continue
            g = idx["cad"].get(cad.get("cadastral_number") or "", {})
            if g.get("lat") is not None: pts.append((g["lat"], g["lon"]))
        if pts:
            lat = sum(p[0] for p in pts)/len(pts); lon = sum(p[1] for p in pts)/len(pts)
            for inn in bu.get("inns", []) or []:
                idx["inn"][str(inn)] = {"bu_id": bu_id, "name": bu.get("name"),
                                        "lat": lat, "lon": lon}
    return idx


def _extract_geom_from_info(info: dict) -> dict:
    """Лучшая попытка: вытащить точку/полигон из NSPD-карточки."""
    if not isinstance(info, dict): return {}
    # Геометрия может быть в разных ключах — пробуем популярные
    for key in ("geometry", "Геометрия", "geom"):
        g = info.get(key)
        if isinstance(g, dict):
            t = g.get("type"); c = g.get("coordinates")
            if t == "Point" and isinstance(c, list) and len(c) >= 2:
                return {"lon": float(c[0]), "lat": float(c[1]), "polygon": None}
            if t in ("Polygon", "MultiPolygon") and c:
                cen = _centroid(c)
                if cen: return {"lat": cen[0], "lon": cen[1], "polygon": c}
    # Координаты вручную ("Координаты центра" / широта/долгота)
    for klat, klon in (("Широта", "Долгота"), ("lat", "lon")):
        if klat in info and klon in info:
            try: return {"lat": float(info[klat]), "lon": float(info[klon]), "polygon": None}
            except Exception: pass
    return {}


def _floors_from_info(info: dict) -> int | None:
    if not isinstance(info, dict): return None
    for k in ("Количество этажей", "Этажность", "floors", "Этажей"):
        v = info.get(k)
        if v is None: continue
        m = re.search(r"\d+", str(v))
        if m: return int(m.group(0))
    return None


# ─── Конвертация PDF → JPG ──────────────────────────────────────────────────
def convert_pdfs(root: Path, idx: dict, dpi: int = 200) -> None:
    src = root / "10_Выписки_PDF"
    pdfs = [p for p in src.rglob("*.pdf") if p.is_file()]
    if not pdfs:
        cp("  PDF не найдены — пропускаю конвертацию.", C.Y); return
    if fitz is None or Image is None:
        cp("  PyMuPDF/Pillow не установлены — `pip install pymupdf pillow piexif`", C.R); return

    zoom = dpi / 72.0
    mtx  = fitz.Matrix(zoom, zoom)
    cp(f"  PDF к конвертации: {len(pdfs)}", C.CY)

    for pdf in pdfs:
        meta = classify_pdf(pdf)
        out_dir = target_dir(root, meta["kind"])
        # Геопривязка: только для документов недвижимости (ЕГРН) и прочих, у
        # которых распознан КН. ЕГРЮЛ/ЕГРИП — без GPS (бенефициары → BU, не
        # точка на карте). Связь с BU остаётся через UserComment.inn.
        lat = lon = alt = None; obj_id = None; bu_id = None
        if meta["kind"] in ("egrn", "doc") and meta["cad"] and meta["cad"] in idx["cad"]:
            c = idx["cad"][meta["cad"]]
            lat, lon, alt, obj_id = c["lat"], c["lon"], c.get("alt"), c["obj_id"]
        if meta["inn"] and meta["inn"] in idx["inn"]:
            bu_id = idx["inn"][meta["inn"]].get("bu_id")

        try:
            doc = fitz.open(pdf)
        except Exception as e:
            cp(f"    [skip] {pdf.name}: {e}", C.R); continue

        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            jpg_name = target_name(meta, page_idx + 1)
            jpg = out_dir / jpg_name
            if jpg.exists():
                continue  # идемпотентно
            pix = page.get_pixmap(matrix=mtx, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(jpg, "JPEG", quality=88, optimize=True)

            descr = f"{meta['kind'].upper()} стр.{page_idx+1} | {pdf.name}"
            ucomment = {
                "app": "ekcelo", "kind": meta["kind"],
                "inn": meta["inn"], "cad": meta["cad"],
                "obj_id": obj_id, "bu_id": bu_id, "src": pdf.name,
                "page": page_idx + 1,
                "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            write_exif(jpg, lat, lon, alt, descr, ucomment)
            cp(f"    [ok] {jpg.relative_to(root)}", C.G)
        doc.close()


# ─── main ───────────────────────────────────────────────────────────────────
def main() -> None:
    cp("=" * 64, C.B)
    cp(" GOLDEN_PATH init — pirushin_sosn_rocha_07_init_project_v1", C.B)
    cp("=" * 64, C.B)

    default_root = r"D:\ОБЪЕКТЫ"
    raw = input(f"\nКорневая папка [{default_root}]: ").strip() or default_root
    name = input("Название проекта (папка внутри): ").strip()
    if not name:
        cp("Название не указано — выход.", C.R); sys.exit(1)

    root = Path(raw) / name
    cp(f"\nСоздаю структуру: {root}", C.CY)
    make_tree(root)
    cp("  дерево создано.", C.G)

    ans = input("\nКонвертировать PDF из 10_Выписки_PDF/ в JPG? [Y/n]: ").strip().lower()
    if ans in ("", "y", "yes", "д", "да"):
        idx = build_index(root)
        if not idx["cad"] and not idx["inn"]:
            cp("  structure.json не найден — JPG без GPS, только машиночитаемые имена.", C.Y)
        convert_pdfs(root, idx)

    cp("\nГотово.", C.B)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: cp("\nПрервано.", C.Y)
