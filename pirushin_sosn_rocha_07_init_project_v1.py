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
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
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
DOC_KINDS_DIRS = ["ЕГРЮЛ-ЕГРИП", "ЕГРН",
                  "Свидетельства_о_праве", "Технические_паспорта",
                  "Техпланы", "Прочее"]

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
    "10_Выписки_PDF",
    *[f"09_Документы_JPG/{k}" for k in DOC_KINDS_DIRS],
    *[f"10_Выписки_PDF/{k}"  for k in DOC_KINDS_DIRS],
]

README = """# {name}

Структура GOLDEN_PATH (создана pirushin_sosn_rocha_07_init_project_v1.py).

Поток данных:
  10_Выписки_PDF/  → (скрипт 07) → 09_Документы_JPG/  (EXIF: GPS, UserComment JSON)
  _data/osv.xlsx   → (скрипт 052) → _data/structure.json
  _data/structure.json → (скрипт 04_nspd_graph) → _data/graph.html
  всё выше + 08_Фотографии/ → (скрипт 08) → _exports/project.kmz

KMZ совместим с Google Earth Pro и https://romanbabenkorostov-ux.github.io/ekcelo/

Машиночитаемые имена документов (дата документа `_dYYYYMMDD` подставляется,
если её удалось вынуть из тела PDF):

  ЕГРЮЛ:           egrul_inn<ИНН>[_dYYYYMMDD]_p<NN>.jpg     → 09_Документы_JPG/ЕГРЮЛ-ЕГРИП/
  ЕГРИП:           egrip_innfl<ИНН>[_dYYYYMMDD]_p<NN>.jpg   → 09_Документы_JPG/ЕГРЮЛ-ЕГРИП/
  ЕГРН:            egrn_<КН с _>[_dYYYYMMDD]_p<NN>.jpg      (напр. egrn_61_44_0050706_31_d20260427_p01.jpg)
  Свидетельство:   svid_<КН>[_dYYYYMMDD]_p<NN>.jpg
  Техпаспорт:      tehpasp_<КН>[_dYYYYMMDD]_p<NN>.jpg
  Техплан:         tehplan_<КН>[_dYYYYMMDD]_p<NN>.jpg
  Прочее:          doc_<slug>[_dYYYYMMDD]_p<NN>.jpg

Если рядом с PDF-выпиской ЕГРН лежит парный XML (тот же №КУВИ и КН) — XML
имеет приоритет: точные значения адреса, площади, типа объекта,
правообладателя и т.п. берутся из XML, PDF используется только как
рендеримый источник изображения.

EXIF UserComment (JSON) у каждого JPG-документа:
  {{"app":"ekcelo","kind":"egrul|egrip|egrn|svid|tehpasp|tehplan|doc",
    "inn":"...","cad":"...","obj_id":"...","bu_id":"...",
    "object_type":"land|building|room|structure|ons|null",
    "xml_matched":true|false,"extract_number":"КУВИ-..."}}
"""

# Регэкспы для распознавания имени исходного PDF
INN_UL_RE  = re.compile(r"(?<!\d)(\d{10})(?!\d)")           # 10 цифр — ЮЛ
INN_FL_RE  = re.compile(r"(?<!\d)(\d{12})(?!\d)")           # 12 цифр — ФЛ/ИП
CN_RE      = re.compile(r"(\d{2}:\d{2}:\d{1,8}:\d{1,8})")
SLUG_RE    = re.compile(r"[^A-Za-zА-Яа-я0-9._-]+")

# Парсинг тела PDF-документов (взято из 05_parse_egrn_folder_to_xlsx)
EGRN_MARKERS = (
    "выписка из единого государственного реестра недвижимости",
    "роскадастр", "росреестр",
    "сведения о характеристиках объекта недвижимости",
)
EGRUL_MARKERS = ("выписка из единого государственного реестра юридических лиц",)
EGRIP_MARKERS = ("выписка из единого государственного реестра индивидуальных предпринимателей",)
SVID_MARKERS    = ("свидетельство о государственной регистрации права",
                   "свидетельство о праве")
TEHPASP_MARKERS = ("технический паспорт",)
TEHPLAN_MARKERS = ("технический план",)
KUVI_RE     = re.compile(r"КУВИ-\d+/\d{4}-\d+")
OGRN_RE     = re.compile(r"(?<!\d)(\d{13})(?!\d)")     # ОГРН ЮЛ
OGRNIP_RE   = re.compile(r"(?<!\d)(\d{15})(?!\d)")     # ОГРНИП
DDMMYYYY_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
EGRN_OBJ_RE = re.compile(
    r"(Земельный участок|Помещение|Здание|Сооружение|Машино-место|"
    r"Объект незаверш[её]нного строительства)", re.IGNORECASE,
)
OBJ_TYPE_MAP = {
    "земельный участок": "land", "помещение": "room", "здание": "building",
    "сооружение": "structure", "машино-место": "parking",
    "объект незавершённого строительства": "ons",
    "объект незавершенного строительства": "ons",
}

def slugify(s: str) -> str:
    return SLUG_RE.sub("_", s).strip("_").lower() or "x"

def cad_to_token(cn: str) -> str:
    return cn.replace(":", "_").replace("/", "-")


def read_pdf_head(pdf: Path, max_pages: int = 3) -> str:
    """Безопасное чтение первых страниц PDF через PyMuPDF."""
    if fitz is None: return ""
    try:
        doc = fitz.open(pdf)
        text = "\n".join(doc.load_page(i).get_text()
                         for i in range(min(max_pages, doc.page_count)))
        doc.close()
        return text
    except Exception:
        return ""


# ─── LibreOffice headless: .doc/.docx → PDF ─────────────────────────────────
def find_soffice() -> str | None:
    """Возвращает путь к LibreOffice CLI или None."""
    for cand in ("soffice", "soffice.exe", "libreoffice"):
        path = shutil.which(cand)
        if path: return path
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/usr/bin/soffice", "/usr/bin/libreoffice",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(p).exists(): return p
    return None


def doc_to_pdf(src: Path, out_dir: Path) -> Path | None:
    """LibreOffice headless: <src.doc|docx> → <out_dir>/<src.stem>.pdf"""
    soffice = find_soffice()
    if not soffice: return None
    try:
        r = subprocess.run(
            [soffice, "--headless", "--nologo", "--nofirststartwizard",
             "--convert-to", "pdf", "--outdir", str(out_dir), str(src)],
            capture_output=True, timeout=180,
        )
        if r.returncode != 0: return None
    except Exception:
        return None
    out = out_dir / (src.stem + ".pdf")
    return out if out.exists() else None


def extract_text_any(path: Path) -> str:
    """Текст из .pdf/.docx/.doc для классификации (поиск КН/ИНН/маркеров)."""
    sfx = path.suffix.lower()
    if sfx == ".pdf":
        return read_pdf_head(path)
    if sfx == ".docx":
        try:
            with zipfile.ZipFile(path) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml)
        except Exception:
            return ""
    if sfx == ".doc":
        # без LibreOffice текст не достанем — но это не критично, имя
        # будет сделано из стэма; КН будет искаться в PDF после рендера
        soffice = find_soffice()
        if not soffice: return ""
        try:
            with tempfile.TemporaryDirectory() as td:
                subprocess.run(
                    [soffice, "--headless", "--nologo", "--convert-to",
                     "txt:Text", "--outdir", td, str(path)],
                    capture_output=True, timeout=120,
                )
                txt = Path(td) / (path.stem + ".txt")
                return txt.read_text(encoding="utf-8", errors="ignore") if txt.exists() else ""
        except Exception:
            return ""
    return ""


def detect_doc_kind(parent: str, name: str, body: str) -> str:
    """Определить вид документа по имени папки → имени файла → телу PDF."""
    parent_lo = parent.lower()
    name_lo = name.lower()
    bl = (body or "").lower()

    # 1) Если parent — совмещённая папка «ЕГРЮЛ-ЕГРИП», kind определяется
    #    ТОЛЬКО по имени файла или телу (маркеры/префикс ul-|fl-).
    if "егрюл-егрип" in parent_lo or "egrul-egrip" in parent_lo:
        if name_lo.startswith("ul-") or any(m in bl for m in EGRUL_MARKERS): return "egrul"
        if name_lo.startswith("fl-") or any(m in bl for m in EGRIP_MARKERS): return "egrip"
        # фолбэк: по разрядности ИНН в имени (10 → ЮЛ, 12 → ИП)
        if INN_FL_RE.search(name): return "egrip"
        if INN_UL_RE.search(name): return "egrul"
        return "doc"

    # 2) Прочие отдельные папки
    p = parent_lo + " " + name_lo
    if "егрюл" in p or "egrul" in p or name_lo.startswith("ul-"): return "egrul"
    if "егрип" in p or "egrip" in p or name_lo.startswith("fl-"): return "egrip"
    if any(k in p for k in ("свидетел", "svid")):       return "svid"
    if any(k in p for k in ("техпасп", "технич_пасп", "tehpasp")): return "tehpasp"
    if any(k in p for k in ("техплан", "технич_план", "tehplan")):  return "tehplan"
    if "егрн" in p or "кадастр" in p or "egrn" in p:    return "egrn"

    # 3) Маркеры из тела PDF (когда папка не подсказывает)
    if any(m in bl for m in EGRUL_MARKERS):   return "egrul"
    if any(m in bl for m in EGRIP_MARKERS):   return "egrip"
    if any(m in bl for m in EGRN_MARKERS):    return "egrn"
    if any(m in bl for m in SVID_MARKERS):    return "svid"
    if any(m in bl for m in TEHPASP_MARKERS): return "tehpasp"
    if any(m in bl for m in TEHPLAN_MARKERS): return "tehplan"
    return "doc"


def extract_obj_type(body: str) -> str | None:
    m = EGRN_OBJ_RE.search(body or "")
    if not m: return None
    return OBJ_TYPE_MAP.get(m.group(1).lower())


def extract_doc_date(body: str, kind: str) -> str | None:
    """Дата документа → ISO 'YYYY-MM-DD' или None."""
    if not body: return None
    if kind == "egrn":
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s*г?\.?\s*№\s*КУВИ", body)
        if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if kind in ("egrul", "egrip"):
        for pat in (
            r"Дата формирования[^\n]*?(\d{2})\.(\d{2})\.(\d{4})",
            r"[Сс]формирован[а-я]*[^\n]{0,40}(\d{2})\.(\d{2})\.(\d{4})",
            r"Дата выписки[^\n]*?(\d{2})\.(\d{2})\.(\d{4})",
        ):
            m = re.search(pat, body)
            if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = DDMMYYYY_RE.search(body or "")
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


# ─── XML-парсер (приоритет над PDF при совпадении КУВИ + КН) ────────────────
import xml.etree.ElementTree as _ET

XML_TAG_TO_OBJ = {  # корневой тег → object_type
    "extract_about_property_land":      "land",
    "extract_about_property_building":  "building",
    "extract_about_property_room":      "room",
    "extract_about_property_structure": "structure",
    "extract_about_property_ons":       "ons",
    "extract_about_property_parking":   "parking",
}

def parse_egrn_xml(xml: Path) -> dict | None:
    """Извлечь канонические данные из XML-выписки ЕГРН (формат Росреестра)."""
    try:
        root = _ET.parse(xml).getroot()
    except Exception:
        return None
    obj_type = None
    rtag = root.tag.lower()
    for k, v in XML_TAG_TO_OBJ.items():
        if k in rtag: obj_type = v; break

    def first(*paths):
        for p in paths:
            e = root.find(".//" + p)
            if e is not None and (e.text or "").strip():
                return e.text.strip()
        return None

    return {
        "kuvi":          first("registration_number"),
        "extract_date":  first("date_formation", "date_received_request"),
        "cad":           first("cad_number"),
        "obj_type":      obj_type,
        "address":       first("readable_address", "position_description"),
        "area":          first("area"),
        "purpose":       first("purpose/value", "purpose"),
        "name":          first("name"),
        "right_type":    first("right_type/value"),
        "right_number":  first("right_number"),
        "holder_name":   first("resident/name", "individual/full_name"),
        "holder_inn":    first("inn"),
        "holder_ogrn":   first("ogrn"),
        "cad_value":     first("cost/value"),
        "_source_xml":   xml.name,
    }


def build_xml_index(root: Path) -> dict:
    """{(kuvi, cad) → xml_meta}; используется для подмены PDF-данных."""
    idx: dict = {}
    base = root / "10_Выписки_PDF"
    if not base.exists(): return idx
    for xml in base.rglob("*.xml"):
        meta = parse_egrn_xml(xml)
        if meta and meta.get("kuvi") and meta.get("cad"):
            idx[(meta["kuvi"], meta["cad"])] = meta
    return idx


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


# ─── Классификация исходного документа (имя + содержимое) ──────────────────
def classify_pdf(orig: Path, pdf_for_body: Path | None = None) -> dict:
    """
    Классифицирует .pdf/.doc/.docx по имени папки/файла + телу.
    orig          — оригинальный файл (для имени и parent).
    pdf_for_body  — PDF, из которого читать body (для doc/docx — рендер
                    LibreOffice; для pdf — сам файл). Если None — берём из orig.

    Возвращает: {"kind","inn","cad","kuvi","ogrn","obj_type",
                 "doc_date" (ISO), "slug"}
    """
    name = orig.stem
    parent = orig.parent.name
    # body: для PDF берём из pdf_for_body (быстрее), для doc/docx —
    # сначала пробуем «нативно» (zip+XML), иначе из соответствующего PDF
    if orig.suffix.lower() in (".doc", ".docx"):
        body = extract_text_any(orig)
        if not body and pdf_for_body:
            body = read_pdf_head(pdf_for_body)
    else:
        body = read_pdf_head(pdf_for_body or orig)
    src  = name + "\n" + (body or "")

    kind = detect_doc_kind(parent, name, body)

    # КН — сначала имя/parent, затем тело
    cad = None
    m = CN_RE.search(name) or CN_RE.search(parent) or CN_RE.search(body or "")
    if m: cad = m.group(1)

    # ИНН (имя + тело). ОГРН/ОГРНИП — только тело.
    inn = ogrn = None
    if kind == "egrul":
        m = INN_UL_RE.search(src)
        if m: inn = m.group(1)
        m = OGRN_RE.search(src)
        if m: ogrn = m.group(1)
    elif kind == "egrip":
        m = INN_FL_RE.search(src)
        if m: inn = m.group(1)
        m = OGRNIP_RE.search(src)
        if m: ogrn = m.group(1)
    elif kind == "doc":
        m12 = INN_FL_RE.search(src); m10 = INN_UL_RE.search(src)
        if m12: inn, kind = m12.group(1), "egrip"
        elif m10: inn, kind = m10.group(1), "egrul"

    kuvi = None
    if kind == "egrn":
        km = KUVI_RE.search(body or "")
        if km: kuvi = km.group(0)

    obj_type = extract_obj_type(body) if kind in ("egrn", "svid", "tehpasp", "tehplan") else None
    doc_date = extract_doc_date(body, kind)

    return {"kind": kind, "inn": inn, "cad": cad, "kuvi": kuvi, "ogrn": ogrn,
            "obj_type": obj_type, "doc_date": doc_date,
            "slug": slugify(name)[:40]}


KIND_PREFIX = {"egrn": "egrn", "svid": "svid",
               "tehpasp": "tehpasp", "tehplan": "tehplan"}

def _date_token(iso: str | None) -> str:
    """'2026-05-17' → '_d20260517'; иначе пусто."""
    if not iso or len(iso) < 10: return ""
    return f"_d{iso[:4]}{iso[5:7]}{iso[8:10]}"

def target_name(meta: dict, page: int) -> str:
    """
    Имя стабильное и идемпотентное. Дата документа включается в имя — два
    PDF одного субъекта/объекта с разными датами дадут разные имена и не
    затрут друг друга. Совпадающий PDF (та же дата) даст то же имя.
    """
    p = f"p{page:02d}"
    dt = _date_token(meta.get("doc_date"))
    if meta["kind"] == "egrul" and meta["inn"]:
        return f"egrul_inn{meta['inn']}{dt}_{p}.jpg"
    if meta["kind"] == "egrip" and meta["inn"]:
        return f"egrip_innfl{meta['inn']}{dt}_{p}.jpg"
    if meta["kind"] in KIND_PREFIX and meta["cad"]:
        return f"{KIND_PREFIX[meta['kind']]}_{cad_to_token(meta['cad'])}{dt}_{p}.jpg"
    if meta["kind"] == "doc" and meta["cad"]:
        return f"doc_{cad_to_token(meta['cad'])}{dt}_{p}.jpg"
    return f"doc_{meta['slug']}{dt}_{p}.jpg"


def target_dir(root: Path, kind: str) -> Path:
    sub = {"egrul": "ЕГРЮЛ-ЕГРИП", "egrip": "ЕГРЮЛ-ЕГРИП", "egrn": "ЕГРН",
           "svid": "Свидетельства_о_праве",
           "tehpasp": "Технические_паспорта",
           "tehplan": "Техпланы"}.get(kind, "Прочее")
    return root / "09_Документы_JPG" / sub


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
SUPPORTED_EXTS = (".pdf", ".docx", ".doc")

def convert_pdfs(root: Path, idx: dict, dpi: int = 200) -> None:
    src = root / "10_Выписки_PDF"
    files = sorted([p for p in src.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS])
    if not files:
        cp("  файлы (.pdf/.doc/.docx) не найдены — пропускаю конвертацию.", C.Y); return
    if fitz is None or Image is None:
        cp("  PyMuPDF/Pillow не установлены — `pip install pymupdf pillow piexif`", C.R); return

    zoom = dpi / 72.0
    mtx  = fitz.Matrix(zoom, zoom)
    cp(f"  файлов к конвертации: {len(files)}", C.CY)

    # .doc/.docx требуют LibreOffice (бесплатный) для рендера в PDF
    n_office = sum(1 for p in files if p.suffix.lower() in (".doc", ".docx"))
    soffice_ok = find_soffice() is not None if n_office else True
    if n_office and not soffice_ok:
        cp(f"  ⚠ найдено {n_office} .doc/.docx, но LibreOffice не установлен.\n"
           "     поставь https://www.libreoffice.org/ — после этого эти файлы\n"
           "     сконвертируются. Сейчас пропускаю их.", C.Y)

    xml_idx = build_xml_index(root)
    if xml_idx:
        cp(f"  XML-выписок проиндексировано: {len(xml_idx)} (приоритет над PDF)", C.CY)
        # cad → xml_meta в _data/egrn_xml.json — точные данные для KMZ-сборки
        by_cad: dict = {}
        for (_kuvi, cad), meta in xml_idx.items():
            by_cad[cad] = meta
        (root / "_data" / "egrn_xml.json").write_text(
            json.dumps(by_cad, ensure_ascii=False, indent=2), encoding="utf-8")

    n_new = n_skip = n_err = 0
    tmpdir = Path(tempfile.mkdtemp(prefix="ekcelo_doc2pdf_"))
    try:
      for orig in files:
        # Получить PDF для рендеринга: либо сам файл, либо результат soffice
        ext = orig.suffix.lower()
        if ext == ".pdf":
            pdf = orig
        else:
            if not soffice_ok:
                n_err += 1; continue
            pdf = doc_to_pdf(orig, tmpdir)
            if not pdf:
                cp(f"    [err]  не могу сконвертировать через LibreOffice: {orig.name}", C.R)
                n_err += 1; continue
        meta = classify_pdf(orig, pdf_for_body=pdf)

        # XML-пара: при совпадении (КУВИ, КН) — XML переписывает данные
        xml_meta = None
        if meta["kind"] == "egrn" and meta["kuvi"] and meta["cad"]:
            xml_meta = xml_idx.get((meta["kuvi"], meta["cad"]))
            if xml_meta:
                meta["obj_type"] = xml_meta.get("obj_type") or meta["obj_type"]

        out_dir = target_dir(root, meta["kind"])
        # Геопривязка: GPS только для документов с распознанным КН
        # (ЕГРН, свидетельства, техпаспорта, техпланы).
        # ЕГРЮЛ/ЕГРИП — без GPS, связь с BU через UserComment.inn.
        lat = lon = alt = None; obj_id = None; bu_id = None
        if meta["kind"] in ("egrn", "svid", "tehpasp", "tehplan", "doc") \
                and meta["cad"] and meta["cad"] in idx["cad"]:
            c = idx["cad"][meta["cad"]]
            lat, lon, alt, obj_id = c["lat"], c["lon"], c.get("alt"), c["obj_id"]
        if meta["inn"] and meta["inn"] in idx["inn"]:
            bu_id = idx["inn"][meta["inn"]].get("bu_id")

        try:
            doc = fitz.open(pdf)
        except Exception as e:
            cp(f"    [err]  {pdf.name}: {e}", C.R); n_err += 1; continue

        pdf_new = pdf_skip = 0
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            jpg_name = target_name(meta, page_idx + 1)
            jpg = out_dir / jpg_name
            if jpg.exists():
                pdf_skip += 1; n_skip += 1
                continue  # идемпотентно
            pix = page.get_pixmap(matrix=mtx, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(jpg, "JPEG", quality=88, optimize=True)

            descr = f"{meta['kind'].upper()} стр.{page_idx+1} | {orig.name}"
            ucomment = {
                "app": "ekcelo", "kind": meta["kind"],
                "inn": meta["inn"], "ogrn": meta.get("ogrn"),
                "cad": meta["cad"],
                "obj_id": obj_id, "bu_id": bu_id,
                "object_type": meta.get("obj_type"),
                "extract_number": meta.get("kuvi"),
                "doc_date": meta.get("doc_date"),
                "xml_matched": bool(xml_meta),
                "xml_extract_date": (xml_meta or {}).get("extract_date"),
                "src": orig.name,
                "src_ext": orig.suffix.lower().lstrip("."),
                "page": page_idx + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            write_exif(jpg, lat, lon, alt, descr, ucomment)
            cp(f"    [ok]   {jpg.relative_to(root)}", C.G)
            pdf_new += 1; n_new += 1
        doc.close()
        if pdf_new == 0 and pdf_skip > 0:
            cp(f"    [skip] {orig.name}  ({pdf_skip} стр. уже сконвертированы)", C.CY)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    cp(f"\n  итого: создано {n_new}, пропущено {n_skip}"
       + (f", ошибок {n_err}" if n_err else ""),
       C.G if n_new else C.CY)


# ─── Буфер обмена (Windows clip.exe, иначе pbcopy / xclip / pyperclip) ─────
def to_clipboard(text: str) -> bool:
    try:
        if sys.platform.startswith("win"):
            p = subprocess.run("clip", input=text.encode("utf-16le"),
                               shell=True, check=False)
            return p.returncode == 0
        for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True); return True
            except FileNotFoundError: continue
        import pyperclip   # последний фолбэк
        pyperclip.copy(text); return True
    except Exception:
        return False


# ─── main / меню ────────────────────────────────────────────────────────────
def action_create() -> Path | None:
    """Создать новую болванку структуры. Вернёт путь к ней (или None)."""
    default_root = r"D:\ОБЪЕКТЫ"
    raw = input(
        f"\nВыберите папку для создания в ней новой болванки структуры "
        f"недвижимости ekcelo, [Enter — {default_root}]: "
    ).strip() or default_root
    name = input("Как назвать папку проекта: ").strip()
    if not name:
        cp("Название не указано — отмена.", C.R); return None
    root = Path(raw) / name
    cp(f"\nСоздаю структуру: {root}", C.CY)
    make_tree(root)
    cp("  дерево создано.", C.G)
    if to_clipboard(str(root)):
        cp(f"  путь скопирован в буфер обмена.", C.G)
    else:
        cp(f"  (буфер обмена недоступен в этой ОС)", C.Y)
    return root


def action_convert(last_root: Path | None) -> None:
    """Конвертация PDF → JPG из 10_Выписки_PDF/ выбранного проекта."""
    default = str(last_root) if last_root else ""
    prompt = (f"\nИз какой папки проекта конвертировать "
              f"(содержит 10_Выписки_PDF/) "
              f"[Enter — {default}]: " if default
              else "\nПуть к папке проекта (содержит 10_Выписки_PDF/): ")
    raw = input(prompt).strip() or default
    if not raw:
        cp("Путь не указан — отмена.", C.R); return
    root = Path(raw)
    if not (root / "10_Выписки_PDF").exists():
        cp(f"Не нашёл {root/'10_Выписки_PDF'}.", C.R); return

    idx = build_index(root)
    if not idx["cad"] and not idx["inn"]:
        cp("  (structure.json пока не создан — это нормально для свежей "
           "болванки; JPG получат машиночитаемые имена, GPS добавится "
           "позже после 052_make_structure.)", C.CY)
    convert_pdfs(root, idx)


def main() -> None:
    cp("=" * 64, C.B)
    cp(" pirushin_sosn_rocha_07_init_project_v1 — структура + конвертация", C.B)
    cp("=" * 64, C.B)
    last_root: Path | None = None
    while True:
        cp("\n  1  Создание структуры (новая болванка)", C.CY)
        cp("  2  Конвертация PDF → JPG (из 10_Выписки_PDF/)", C.CY)
        cp("  3  Выход", C.CY)
        ch = input("\nВаш выбор: ").strip()
        if ch == "1":
            r = action_create()
            if r: last_root = r
        elif ch == "2":
            action_convert(last_root)
        elif ch in ("3", "q", "exit", ""):
            cp("Готово.", C.B); return
        else:
            cp("Введите 1, 2 или 3.", C.Y)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: cp("\nПрервано.", C.Y)
