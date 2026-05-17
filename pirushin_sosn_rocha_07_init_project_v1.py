#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pirushin_sosn_rocha_07_init_project_v1.py

Инициализация и поддержка GOLDEN_PATH-структуры проекта объекта (v3):

    D:\\ОБЪЕКТЫ\\<Название_проекта>\\
        _data/, _data/nspd_cache/    — служебный кэш
        ОСВ/                          — оборотно-сальдовая ведомость 1С
        XLSX/                         — выгрузки/отчёты
        DB/                           — project.db (SQLite)
        Документы_JPG/{ЕГРЮЛ-ЕГРИП,ЕГРН,Свидетельства_о_праве,
                       Технические_паспорта,Техпланы,Прочее}/
        Выписки_PDF/<те же подпапки>/  — исходники + KML/KMZ
        Не_распределено/               — «свалка» пользователя (любые типы файлов:
                                         фото, PDF, XML, DOC, XLS, DB, HTML, JSON, KML);
                                         меню 3 разносит её по структуре
        Фотографии/
            Недвижимость/{Земельные_участки,Строения,Сооружения,Помещения,ОНЗ}/
            Оборудование/<инв№>/      Бизнес_единицы/<slug>/
        Бизнес_единицы/                — пользовательские материалы по BU
        KMZ-KML/                       — выход 08_build_kmz + сторонние KML
        HTML/                          — выход 04_nspd_graph

Меню скрипта:
  1) Создание структуры — болванка по приведённой схеме + путь в буфер обмена.
  2) Конвертация документов — PDF/DOC/DOCX → JPG (рендер: PyMuPDF, для
     DOC/DOCX — LibreOffice или MS Word) с машиночитаемыми именами и
     EXIF/UserComment. После конвертации синхронизирует фото-дерево из
     обнаруженных документов: создаёт `Фотографии/Недвижимость/<категория>/
     <КН с _>/[План/]` для каждого распознанного КН.
  3) Сортировка папки Не_распределено/ (в корне болванки) — разносит
     любые типы файлов (фото / PDF / XML / DOC / XLS / DB / HTML / JSON /
     KML) по структуре проекта. Для JPG дописывает в EXIF привязку к КН,
     не затирая оригинальные даты съёмки и GPS, сохраняет mtime файла.
     Сначала dry-run + подтверждение, затем move.
  4) Выход.

Зависимости:  PyMuPDF (fitz), Pillow, piexif

Python 3.13+, Windows 10.
"""

from __future__ import annotations
import io
import json
import os
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
# Корневая папка для «хаотичного дампа» от пользователя. Лежит в КОРНЕ
# болванки (не внутри Фотографии/), потому что в неё могут попадать
# любые типы файлов: фото, PDF/XML-выписки, DOC/XLS/DB/HTML/JSON/KML.
UNSORTED_DIR = "Не_распределено"

DOC_KINDS_DIRS = ["ЕГРЮЛ-ЕГРИП", "ЕГРН",
                  "Свидетельства_о_праве", "Технические_паспорта",
                  "Техпланы", "Прочее"]
REALTY_CATS    = ["Земельные_участки", "Строения", "Сооружения",
                  "Помещения", "ОНЗ"]
PLAN_CATS      = ("Строения", "Сооружения", "ОНЗ")  # доп. подпапка «План»

DIRS = [
    "_data", "_data/nspd_cache",          # служебный кэш (NSPD, XML-выписки)
    "ОСВ",                                # вход: оборотно-сальдовая ведомость 1С
    "XLSX",                               # выгрузки/отчёты
    "DB",                                 # SQLite-БД проекта
    "KMZ-KML",                            # выход 08_build_kmz и исходные KML/KMZ
    "HTML",                               # граф 04_nspd_graph
    "doc",                                # произвольные пользовательские .doc/.docx
    "json", "json/objects",               # агрегированные паспорта объектов
    "Бизнес_единицы",
    "Документы_JPG",
    "Выписки_PDF",
    *[f"Документы_JPG/{k}" for k in DOC_KINDS_DIRS],
    *[f"Выписки_PDF/{k}"   for k in DOC_KINDS_DIRS],
    UNSORTED_DIR,                         # «свалка» в корне болванки
    "Фотографии",
    "Фотографии/Недвижимость",            # подкатегории создаются динамически
    "Фотографии/Оборудование",
    "Фотографии/Бизнес_единицы",
]

README = """# {name}

Структура GOLDEN_PATH v3 (создана pirushin_sosn_rocha_07_init_project_v1.py).

Корневые папки:
  ОСВ/             — оборотно-сальдовая ведомость 1С (вход для 052_make_structure)
  XLSX/            — пользовательские выгрузки/отчёты
  DB/              — project.db (SQLite)
  Документы_JPG/   — JPG-снимки документов (генерит 07: PDF/DOC/DOCX → JPG)
  Выписки_PDF/     — исходники документов (включая XML-пары ЕГРН и KML/KMZ)
  Не_распределено/ — «свалка» произвольных файлов от пользователя
                     (фото, PDF, XML, DOC, XLS, DB, HTML, JSON, KML);
                     меню 3 разносит её по структуре проекта
  Фотографии/      — фотоматериалы (см. ниже)
  Бизнес_единицы/  — материалы по BU
  KMZ-KML/         — выход 08_build_kmz + сторонние KML
  HTML/            — выход 04_nspd_graph
  _data/           — служебный кэш (nspd_cache/, egrn_xml.json, structure.json)

Поток данных:
  Выписки_PDF/   → (07)  → Документы_JPG/  (EXIF: GPS, UserComment JSON)
  Не_распределено/ → (07 меню 3) → Фотографии/Недвижимость/ + Выписки_PDF/ + …
  ОСВ/osv.xlsx   → (052) → _data/structure.json
  _data/structure.json → (04_nspd_graph) → HTML/graph.html
  всё выше + Фотографии/ → (08) → KMZ-KML/project.kmz

Фото-дерево (07 создаёт + идемпотентно синхронизирует из обнаруженных
документов: КН из XML-выписок, имён JPG-документов, KML/KMZ-файлов):
  Фотографии/
    Недвижимость/
      Земельные_участки/<КН с _>/
      Строения/<КН с _>/<КН с _>/План/         — План создаётся автоматом
      Сооружения/<КН с _>/<КН с _>/План/
      Помещения/<КН с _>/
      ОНЗ/<КН с _>/<КН с _>/План/
    Оборудование/<инв №>/
    Бизнес_единицы/<slug>/

KMZ совместим с Google Earth Pro и https://romanbabenkorostov-ux.github.io/ekcelo/

Машиночитаемые имена документов (дата документа `_dYYYYMMDD` подставляется,
если её удалось вынуть из тела PDF):

  ЕГРЮЛ:           egrul_inn<ИНН>[_dYYYYMMDD]_p<NN>.jpg     → Документы_JPG/ЕГРЮЛ-ЕГРИП/
  ЕГРИП:           egrip_innfl<ИНН>[_dYYYYMMDD]_p<NN>.jpg   → Документы_JPG/ЕГРЮЛ-ЕГРИП/
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
CN_UND_RE  = re.compile(r"(?<!\d)(\d{2})_(\d{2})_(\d{1,8})_(\d{1,8})(?!\d)")
CN_FLAT_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{7})(\d{1,4})(?!\d)")  # 12-15 цифр
SLUG_RE    = re.compile(r"[^A-Za-zА-Яа-я0-9._-]+")


def find_cads_in_text(text: str) -> list[str]:
    """Извлекает КН в стандартной форме '61:44:0050706:31' из текста.
    Поддерживает три написания: с двоеточиями, с подчёркиваниями
    (61_44_0050706_31), и «плоское» 12-15 цифр подряд (61440040713308)."""
    if not text: return []
    out: list[str] = []
    for m in CN_RE.finditer(text):
        out.append(m.group(1))
    for m in CN_UND_RE.finditer(text):
        out.append(f"{m.group(1)}:{m.group(2)}:{m.group(3)}:{m.group(4)}")
    for m in CN_FLAT_RE.finditer(text):
        out.append(f"{m.group(1)}:{m.group(2)}:{m.group(3)}:{m.group(4)}")
    return list(dict.fromkeys(out))


# Сокращения и опечатки для типа недвижимости
LAND_HINT_RE      = re.compile(
    r"\b(?:зу|з/у|з\.у\.|зем(?:ельн\w*)?\s*участ\w*|земучаст\w*|"
    r"участ\w*\s*зем|зучест\w*)\b|земельный\s*участок", re.IGNORECASE)
BUILDING_HINT_RE  = re.compile(r"жилой\s*дом|многокварт|здан|строен", re.IGNORECASE)
ROOM_HINT_RE      = re.compile(r"квартир|\bкв\.?\b|помещен|нежил\w*\s*помещ|кладов", re.IGNORECASE)
STRUCTURE_HINT_RE = re.compile(r"сооруж", re.IGNORECASE)
ONS_HINT_RE       = re.compile(r"\b(?:онс|онз)\b|незаверш", re.IGNORECASE)

def detect_category_from_text(text: str) -> str | None:
    """Распознаёт object_type по русским сокращениям/опечаткам.
    Порядок приоритета: квартира/помещение → здание → сооружение → ОНЗ → ЗУ."""
    if not text: return None
    if ROOM_HINT_RE.search(text):      return "room"
    if BUILDING_HINT_RE.search(text):  return "building"
    if STRUCTURE_HINT_RE.search(text): return "structure"
    if ONS_HINT_RE.search(text):       return "ons"
    if LAND_HINT_RE.search(text):      return "land"
    return None


# Нормализация имён семантических подпапок (Вход, Подвал, Кухня, Этаж, …)
SEMANTIC_STATIC = [
    (re.compile(r"входн\w*\s*в\s*объект|входн\w*\s*дверь|^\s*вход\s*$|^вход\b", re.I),
     "Вход_в_объект"),
    (re.compile(r"общий\s*вид\s*адрес", re.I),         "Общий_вид_адреса"),
    (re.compile(r"общий\s*вид", re.I),                  "Общий_вид"),
    (re.compile(r"прилегающ\w*\s*территор", re.I),      "Прилегающая_территория"),
    (re.compile(r"окружен\w*\s*квартал|окружен", re.I), "Окружение_квартала"),
    (re.compile(r"состояние\s*внутри|внутри\b", re.I),  "Состояние_внутри"),
    (re.compile(r"состояние\s*отделки|отделк", re.I),   "Состояние_отделки"),
    (re.compile(r"состояние\s*(?:на\s*)?объект", re.I), "Состояние_объекта"),
    (re.compile(r"подвал|подавал", re.I),               "Подвал"),
    (re.compile(r"чердак|мансард", re.I),               "Чердак"),
    (re.compile(r"(?:вид\s*(?:от|из)\s*окна|из\s*окна)", re.I), "Вид_от_окна"),
    (re.compile(r"план\s*эвакуац", re.I),               "План_эвакуации"),
    (re.compile(r"экспликац", re.I),                    "Экспликация"),
    (re.compile(r"планы?|чертеж", re.I),                "Планы"),
    (re.compile(r"кухн", re.I),                         "Кухня"),
    (re.compile(r"санузел|туалет|ванная|с/у", re.I),    "Санузел"),
    (re.compile(r"фасад", re.I),                        "Фасад"),
    (re.compile(r"коммерч\w*\s*аналог|^аналог", re.I),  "Аналоги"),
    (re.compile(r"^документ", re.I),                    "Документы_фото"),
    (re.compile(r"^фото$|^foto$", re.I),                None),  # игнор — это контейнер
]
SEMANTIC_DYNAMIC = [
    (re.compile(r"\bлит\.?\s*([а-я])\b", re.I),                                "Литер_{0}"),
    (re.compile(r"\bкв\.?\s*(\d+\s*[а-я]?(?:\s*[,+]\s*\d+\s*[а-я]?)*)", re.I), "Кв_{0}"),
    (re.compile(r"\bэтаж\s*(\d+)", re.I),                                       "Этаж_{0}"),
]

def folder_semantic(name: str) -> str | None:
    """Имя папки → нормализованная семантическая метка (None — игнорируем)."""
    if not name: return None
    n = name.replace("_", " ").strip()
    for rx, sem in SEMANTIC_STATIC:
        if rx.search(n): return sem
    for rx, tmpl in SEMANTIC_DYNAMIC:
        m = rx.search(n)
        if m:
            arg = re.sub(r"[\s,+]+", "_", m.group(1)).strip("_").lower()
            return tmpl.format(arg)
    return None


def address_tokens(addr: str) -> set[str]:
    """Информативные токены адреса (нижний регистр, не служебные слова)."""
    if not addr: return set()
    stop = {"д", "дом", "кв", "корп", "стр", "обл", "область", "р-н", "район",
            "г", "город", "ул", "улица", "пер", "переулок", "пр", "проспект",
            "шоссе", "пом", "россия", "почтовый", "адрес", "ориентира",
            "местоположение", "относительно", "расположенного", "границах",
            "участка", "литер", "лит", "этаж", "квартира"}
    out: set[str] = set()
    for t in re.findall(r"[\wа-я-]+", addr.lower()):
        t = t.strip("-")
        if not t or t in stop: continue
        if t.isdigit() and len(t) > 3: continue  # год вроде 2006
        out.add(t)
    return out


def load_objects_index(root: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Грузит json/objects/*.json → ({cn: object_type}, {cn: address_tokens})."""
    objdir = root / "json" / "objects"
    types: dict[str, str] = {}
    addrs: dict[str, set[str]] = {}
    if not objdir.exists(): return types, addrs
    for f in objdir.glob("*.json"):
        try: data = json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        cn = data.get("cadastral_number") or f.stem.replace("_", ":")
        if data.get("object_type"): types[cn] = data["object_type"]
        if data.get("address"):     addrs[cn] = address_tokens(data["address"])
    return types, addrs

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


def _soffice_to_pdf(src: Path, out_dir: Path) -> Path | None:
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


def _msword_to_pdf(src: Path, out_dir: Path) -> Path | None:
    """MS Word (COM-автоматизация через comtypes) — fallback для Windows."""
    if not sys.platform.startswith("win"): return None
    try:
        import comtypes.client  # pip install comtypes
    except ImportError:
        return None
    out = (out_dir / (src.stem + ".pdf")).resolve()
    word = None
    try:
        word = comtypes.client.CreateObject("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(src.resolve()), ReadOnly=True)
        # 17 = wdExportFormatPDF
        doc.SaveAs(str(out), FileFormat=17)
        doc.Close(False)
        return out if out.exists() else None
    except Exception:
        return None
    finally:
        try:
            if word is not None: word.Quit()
        except Exception:
            pass


def doc_to_pdf(src: Path, out_dir: Path) -> Path | None:
    """Конвертер .doc/.docx → PDF. Сначала LibreOffice, затем MS Word."""
    return _soffice_to_pdf(src, out_dir) or _msword_to_pdf(src, out_dir)


def find_office_converter() -> str | None:
    """Имя доступного конвертера для пользовательских сообщений."""
    if find_soffice(): return "LibreOffice"
    if sys.platform.startswith("win"):
        try:
            import comtypes.client  # noqa
            return "MS Word"
        except ImportError:
            return None
    return None


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
    base = root / "Выписки_PDF"
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
    # Пустой sqlite-плейсхолдер (заполняется 052 и др.)
    db = root / "DB" / "project.db"
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
    return root / "Документы_JPG" / sub


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
               altitude_amsl: float | None, descr: str, ucomment: dict) -> None:
    """
    GPS: широта/долгота центра объекта + GPSAltitude (если задана) —
    стандарт EXIF трактует GPSAltitude как высоту НАД УРОВНЕМ МОРЯ (AMSL).
    Высота объекта над землёй (height_m) и AMSL также продублированы в
    UserComment JSON для машинного потребления.
    """
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
        if altitude_amsl is not None:
            gps[piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude_amsl >= 0 else 1
            gps[piexif.GPSIFD.GPSAltitude] = (int(round(abs(altitude_amsl) * 100)), 100)
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
    src = root / "Выписки_PDF"
    files = sorted([p for p in src.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS])
    if not files:
        cp("  файлы (.pdf/.doc/.docx) не найдены — пропускаю конвертацию.", C.Y); return
    if fitz is None or Image is None:
        cp("  PyMuPDF/Pillow не установлены — `pip install pymupdf pillow piexif`", C.R); return

    zoom = dpi / 72.0
    mtx  = fitz.Matrix(zoom, zoom)
    cp(f"  файлов к конвертации: {len(files)}", C.CY)

    # .doc/.docx → PDF: сначала LibreOffice, затем MS Word (Windows + comtypes)
    n_office = sum(1 for p in files if p.suffix.lower() in (".doc", ".docx"))
    converter = find_office_converter() if n_office else "—"
    office_ok = bool(converter)
    if n_office:
        if office_ok:
            cp(f"  .doc/.docx найдено: {n_office} (конвертер: {converter})", C.CY)
        else:
            cp(f"  ⚠ найдено {n_office} .doc/.docx, но не найден ни LibreOffice, "
               "ни MS Word.\n     Поставь LibreOffice (https://www.libreoffice.org/) "
               "или, если на Windows есть Word — установи `pip install comtypes`.\n"
               "     Сейчас .doc/.docx пропускаются.", C.Y)

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
            if not office_ok:
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
        # Гео: GPS только для документов с распознанным КН. ЕГРЮЛ/ЕГРИП —
        # без GPS, связь с BU через UserComment.inn.
        center_lat = center_lon = height_m = altitude_amsl_m = None
        obj_id = bu_id = None
        if meta["kind"] in ("egrn", "svid", "tehpasp", "tehplan", "doc") \
                and meta["cad"] and meta["cad"] in idx["cad"]:
            c = idx["cad"][meta["cad"]]
            center_lat, center_lon = c["lat"], c["lon"]
            height_m = c.get("alt")           # высота объекта над землёй
            altitude_amsl_m = c.get("amsl")   # абс. отметка (None — на будущее)
            obj_id = c["obj_id"]
        if meta["inn"] and meta["inn"] in idx["inn"]:
            bu_id = idx["inn"][meta["inn"]].get("bu_id")

        # Дедупликация задвоенных документов: если в out_dir уже есть JPG'и с
        # тем же базовым именем (kind+КН+дата, без `_pNN`), не разворачиваем
        # вторую копию по страницам.
        base_stem = target_name(meta, 1).rsplit("_p", 1)[0]
        existing_pages = sorted(out_dir.glob(f"{base_stem}_p*.jpg"))
        if existing_pages:
            cp(f"    [skip] {orig.name}  (дубль, уже сконвертирован: "
               f"{len(existing_pages)} стр.)", C.CY)
            n_skip += len(existing_pages); continue

        try:
            doc = fitz.open(pdf)
        except Exception as e:
            cp(f"    [err]  {pdf.name}: {e}", C.R); n_err += 1; continue

        page_count = doc.page_count
        pdf_new = pdf_skip = 0
        for page_idx in range(page_count):
            page = doc.load_page(page_idx)
            jpg_name = target_name(meta, page_idx + 1)
            jpg = out_dir / jpg_name
            if jpg.exists():
                pdf_skip += 1; n_skip += 1
                continue  # идемпотентно
            pix = page.get_pixmap(matrix=mtx, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(jpg, "JPEG", quality=88, optimize=True)

            descr = (f"{meta['kind'].upper()} стр.{page_idx+1}/{page_count} | "
                     f"{orig.name}")
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
                "page_count": page_count,
                # Гео-факты объекта (продублированы в GPS-секции EXIF):
                "center_lat": center_lat,
                "center_lon": center_lon,
                "height_m": height_m,             # высота объекта над землёй
                "altitude_amsl_m": altitude_amsl_m,  # AMSL (этаж/потолок) — на будущее
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            write_exif(jpg, center_lat, center_lon, altitude_amsl_m, descr, ucomment)
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


# ─── Идемпотентная синхронизация фото-дерева из обнаруженных документов ────
OBJ_TYPE_TO_CAT = {
    "land": "Земельные_участки", "building": "Строения",
    "structure": "Сооружения", "room": "Помещения",
    "parking": "Помещения", "ons": "ОНЗ",
}

# Поля JSON-узлов, в которых ищем КН (graph.json, egrn_*.json, structure.json)
_CAD_KEYS = ("cadNumber", "cad_number", "cadastral_number", "cn")
_OBJ_TYPE_KEYS = ("type", "objectClass", "object_type")
# Узлы, которые не являются недвижимостью
_NON_REALTY_TYPES = {"holder", "entity", "right", "encumbrance",
                     "restriction", "person", "company"}


def _walk_json_for_cads(obj, acc: dict[str, dict]) -> None:
    """Рекурсивно ищет dict-узлы с кадастровым номером. Накапливает в acc:
       acc[КН] = {object_type, address, area, cadastral_value, geometry, ...}"""
    if isinstance(obj, dict):
        cn = None
        for k in _CAD_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and CN_RE.fullmatch(v):
                cn = v; break
        if cn:
            rec = acc.setdefault(cn, {})
            # тип объекта
            for k in _OBJ_TYPE_KEYS:
                tv = obj.get(k)
                if isinstance(tv, str) and tv.lower() in OBJ_TYPE_TO_CAT:
                    rec.setdefault("object_type", tv.lower()); break
                if isinstance(tv, str) and tv.lower() in _NON_REALTY_TYPES:
                    return  # это узел владельца/права, не недвижимости
            # скаляры
            for k_in, k_out in (("address", "address"), ("area", "area"),
                                ("cadastralValue", "cadastral_value"),
                                ("cadastral_value", "cadastral_value"),
                                ("name", "name"), ("purpose", "purpose"),
                                ("permittedUse", "permitted_use"),
                                ("permitted_uses", "permitted_use"),
                                ("floorsAboveGround", "floors_above_ground"),
                                ("undergroundFloors", "underground_floors")):
                v = obj.get(k_in)
                if v not in (None, "", []) and rec.get(k_out) in (None, "", []):
                    rec[k_out] = v
            # геометрия (lat/lon/wkt)
            g = obj.get("geometry")
            if isinstance(g, dict):
                if g.get("lat") is not None and not rec.get("geometry"):
                    rec["geometry"] = {"lat": g["lat"], "lon": g.get("lon")}
                if g.get("wkt") and not rec.get("wkt"):
                    rec["wkt"] = g["wkt"]
        for v in obj.values():
            _walk_json_for_cads(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_json_for_cads(v, acc)


def _scan_user_json(root: Path) -> dict[str, dict]:
    """Собирает данные из всех *.json в json/ и _data/ (graph.json,
    egrn_*.json, structure.json, любые пользовательские)."""
    acc: dict[str, dict] = {}
    for d in (root / "json", root / "_data"):
        if not d.exists(): continue
        for jf in d.rglob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            _walk_json_for_cads(data, acc)
    return acc


def _write_object_passport(root: Path, cn: str, rec: dict,
                           jpg_names: list[str]) -> None:
    """Идемпотентно пишет/обновляет json/objects/<КН>.json — паспорт
    объекта (тип, адрес, площадь, геометрия, высоты, список JPG-документов)."""
    objdir = root / "json" / "objects"
    objdir.mkdir(parents=True, exist_ok=True)
    f = objdir / f"{cn.replace(':', '_')}.json"
    # height_m из этажности (если есть)
    height_m = None
    fag = rec.get("floors_above_ground")
    try:
        if fag is not None: height_m = float(fag) * 3.0
    except Exception: pass
    passport = {
        "cadastral_number":     cn,
        "object_type":          rec.get("object_type"),
        "address":              rec.get("address"),
        "area":                 rec.get("area"),
        "cadastral_value":      rec.get("cadastral_value"),
        "name":                 rec.get("name"),
        "purpose":              rec.get("purpose"),
        "permitted_use":        rec.get("permitted_use"),
        "floors_above_ground":  rec.get("floors_above_ground"),
        "underground_floors":   rec.get("underground_floors"),
        "geometry":             rec.get("geometry"),
        "wkt":                  rec.get("wkt"),
        "height_m":             height_m,
        "altitude_amsl_m":      None,
        "documents":            sorted(jpg_names),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                              .replace("+00:00", "Z"),
    }
    if f.exists():
        # merge: новые непустые поля переопределяют старые None,
        # старые непустые поля сохраняются если новых нет
        try:
            old = json.loads(f.read_text(encoding="utf-8"))
            for k, v in old.items():
                if passport.get(k) in (None, [], "") and v not in (None, [], ""):
                    passport[k] = v
        except Exception: pass
    f.write_text(json.dumps(passport, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _read_jpg_object_type(jpg: Path) -> str | None:
    """Читает EXIF.UserComment.object_type из JPG-документа (если есть)."""
    if piexif is None or UserComment is None: return None
    try:
        exif = piexif.load(str(jpg))
        uc = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment)
        if not uc: return None
        s = UserComment.load(uc)
        meta = json.loads(s) if isinstance(s, str) else None
        return (meta or {}).get("object_type")
    except Exception:
        return None


def _extract_cads_from_kml(path: Path) -> set[str]:
    """КН из KML или KMZ (внутри zip — doc.kml)."""
    try:
        if path.suffix.lower() == ".kmz":
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if n.lower().endswith(".kml"):
                        return set(CN_RE.findall(
                            z.read(n).decode("utf-8", "ignore")))
        else:
            return set(CN_RE.findall(
                path.read_text(encoding="utf-8", errors="ignore")))
    except Exception:
        pass
    return set()


def sync_photo_tree(root: Path) -> None:
    """
    Идемпотентно создаёт подпапки в Фотографии/Недвижимость/<категория>/<КН>/
    и записывает json/objects/<КН>.json (паспорт объекта) на основе:

      1) _data/egrn_xml.json (точный obj_type из XML Росреестра)
      2) _data/structure.json (cadastre_objects)
      3) Любые *.json в json/ — graph.json, egrn_*.json, выгрузки 1С и т.п.;
         рекурсивно извлекаются КН, тип, адрес, площадь, координаты, высоты.
      4) EXIF.UserComment.object_type в Документы_JPG/**/*.jpg
      5) Имена JPG-документов egrn_/svid_/tehpasp_/tehplan_/doc_
      6) KML/KMZ в Выписки_PDF/ и KMZ-KML/

    Категории и подпапки создаются по требованию (если КН такого типа есть).
    Пустые категории не создаются — болванка остаётся компактной.
    """
    photos_root = root / "Фотографии" / "Недвижимость"
    cad_data: dict[str, dict] = {}

    def add_type(cn: str, t: str | None):
        rec = cad_data.setdefault(cn, {})
        if t and not rec.get("object_type"):
            rec["object_type"] = t

    # 1) XML-факты ЕГРН
    xfp = root / "_data" / "egrn_xml.json"
    if xfp.exists():
        try:
            for cn, meta in json.loads(xfp.read_text(encoding="utf-8")).items():
                add_type(cn, (meta or {}).get("obj_type"))
                if meta:
                    rec = cad_data[cn]
                    for k_in, k_out in (("address", "address"),
                                         ("area", "area"),
                                         ("cad_value", "cadastral_value"),
                                         ("name", "name"),
                                         ("purpose", "purpose")):
                        v = meta.get(k_in)
                        if v not in (None, "") and not rec.get(k_out):
                            rec[k_out] = v
        except Exception: pass

    # 2) structure.json — точные типы из 052_make_structure
    for sp in [root / "_data" / "structure.json",
               *sorted((root / "_data").glob("structure_*.json"))]:
        if not sp.exists(): continue
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
            for cad in st.get("cadastre_objects", []):
                cn = cad.get("cadastral_number")
                if not cn: continue
                ot = (cad.get("object_type") or "").lower()
                t = None
                if "земельн" in ot:        t = "land"
                elif "помещ" in ot:        t = "room"
                elif "здан" in ot:         t = "building"
                elif "сооруж" in ot:       t = "structure"
                elif "незаверш" in ot:     t = "ons"
                elif "машино" in ot:       t = "parking"
                add_type(cn, t)
                rec = cad_data[cn]
                for k_in, k_out in (("address", "address"),):
                    v = cad.get(k_in)
                    if v and not rec.get(k_out): rec[k_out] = v
        except Exception: pass

    # 3) Пользовательские JSON в json/ + _data
    for cn, rec in _scan_user_json(root).items():
        merged = cad_data.setdefault(cn, {})
        for k, v in rec.items():
            if v not in (None, "", []) and not merged.get(k):
                merged[k] = v

    # 4+5) Имена JPG-документов + EXIF object_type
    docs_dir = root / "Документы_JPG"
    cad_doc_re = re.compile(
        r"^(egrn|svid|tehpasp|tehplan|doc)_(\d{2})_(\d{2})_(\d{1,8})_(\d{1,8})"
    )
    docs_by_cad: dict[str, list[str]] = {}
    if docs_dir.exists():
        for jpg in docs_dir.rglob("*.jpg"):
            m = cad_doc_re.search(jpg.name)
            if not m: continue
            cn = f"{m.group(2)}:{m.group(3)}:{m.group(4)}:{m.group(5)}"
            ot = _read_jpg_object_type(jpg)
            add_type(cn, ot)
            docs_by_cad.setdefault(cn, []).append(jpg.name)

    # 6) KML/KMZ
    for d in (root / "Выписки_PDF", root / "KMZ-KML"):
        if not d.exists(): continue
        for k in list(d.rglob("*.kml")) + list(d.rglob("*.kmz")):
            for cn in _extract_cads_from_kml(k):
                cad_data.setdefault(cn, {})

    # ─ Создаём папки + пишем паспорта ─
    n_dir = n_plan = n_passport = 0
    for cn, rec in cad_data.items():
        cat = OBJ_TYPE_TO_CAT.get((rec.get("object_type") or "").lower())
        token = cn.replace(":", "_")
        if cat:
            d = photos_root / cat / token
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True); n_dir += 1
            if cat in PLAN_CATS:
                plan = d / "План"
                if not plan.exists():
                    plan.mkdir(parents=True, exist_ok=True); n_plan += 1
        _write_object_passport(root, cn, rec, docs_by_cad.get(cn, []))
        n_passport += 1

    if n_dir or n_plan:
        bits = [f"{n_dir} КН-папок"]
        if n_plan: bits.append(f"{n_plan} «План»")
        cp(f"  фото-дерево: создано {', '.join(bits)}", C.G)
    if n_passport:
        cp(f"  паспортов объектов записано/обновлено: {n_passport} "
           f"→ json/objects/", C.CY)


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
    """Конвертация PDF → JPG из Выписки_PDF/ выбранного проекта."""
    default = str(last_root) if last_root else ""
    prompt = (f"\nИз какой папки проекта конвертировать "
              f"(содержит Выписки_PDF/) "
              f"[Enter — {default}]: " if default
              else "\nПуть к папке проекта (содержит Выписки_PDF/): ")
    raw = input(prompt).strip() or default
    if not raw:
        cp("Путь не указан — отмена.", C.R); return
    root = Path(raw)
    if not (root / "Выписки_PDF").exists():
        cp(f"Не нашёл {root/'10_Выписки_PDF'}.", C.R); return

    idx = build_index(root)
    if not idx["cad"] and not idx["inn"]:
        cp("  (structure.json пока не создан — это нормально для свежей "
           "болванки; JPG получат машиночитаемые имена, GPS добавится "
           "позже после 052_make_structure.)", C.CY)
    convert_pdfs(root, idx)
    cp("\n  синхронизация фото-дерева…", C.CY)
    sync_photo_tree(root)


# ─── Сортировка хаотичной папки Не_распределено/ в нормализованное дерево ──
# Маршрутизация по расширению (для не-фото файлов)
PDF_KIND_TO_SUBDIR = {
    "egrn":    "ЕГРН",
    "egrul":   "ЕГРЮЛ-ЕГРИП", "egrip": "ЕГРЮЛ-ЕГРИП",
    "svid":    "Свидетельства_о_праве",
    "tehpasp": "Технические_паспорта",
    "tehplan": "Техпланы",
    "doc":     "Прочее",
}

def _is_photo(path: Path) -> bool:
    return path.suffix.lower() in (".jpg", ".jpeg")

def _route_non_photo(root: Path, src: Path) -> Path | None:
    """Куда перенести файл, не являющийся фото. None — оставить как есть."""
    sfx = src.suffix.lower()
    if sfx == ".pdf":
        meta = classify_pdf(src)
        sub = PDF_KIND_TO_SUBDIR.get(meta["kind"], "Прочее")
        return root / "Выписки_PDF" / sub / src.name
    if sfx == ".xml":
        # XML обычно парный к PDF из той же папки. Если рядом есть PDF —
        # подбираем подпапку по нему; иначе считаем выпиской ЕГРН.
        sibling_pdf = None
        for s in src.parent.iterdir():
            if s.suffix.lower() == ".pdf" and s.stem.split(".")[0] == src.stem.split(".")[0]:
                sibling_pdf = s; break
        if sibling_pdf:
            sub = PDF_KIND_TO_SUBDIR.get(classify_pdf(sibling_pdf)["kind"], "Прочее")
        else:
            sub = "ЕГРН"
        return root / "Выписки_PDF" / sub / src.name
    if sfx in (".doc", ".docx"):
        return root / "doc" / src.name
    if sfx in (".xls", ".xlsx"):
        return root / "XLSX" / src.name
    if sfx == ".db":
        return root / "DB" / src.name
    if sfx in (".html", ".htm"):
        return root / "HTML" / src.name
    if sfx == ".json":
        return root / "json" / src.name
    if sfx in (".kml", ".kmz"):
        return root / "KMZ-KML" / src.name
    if sfx in (".sig", ".asc"):
        # ЭП-подписи переезжают вслед за основным файлом — упростим:
        # положим в ту же подпапку Выписки_PDF/Прочее.
        return root / "Выписки_PDF" / "Прочее" / src.name
    return None  # неизвестный тип — не трогаем


def annotate_photo_exif(jpg: Path, cn: str | None, category: str | None,
                        semantic: str | None, source_path: str) -> None:
    """Дописывает в EXIF JPG привязку к КН/категории/семантике, СОХРАНЯЯ:
       - оригинальные DateTime/DateTimeOriginal/DateTimeDigitized,
       - оригинальные GPS-координаты,
       - mtime/atime файла на диске.
    Меняем только: ImageDescription (добавляется), UserComment (записывается)."""
    if piexif is None or UserComment is None:
        return
    try:
        stat = jpg.stat()
    except Exception:
        stat = None
    try:
        exif = piexif.load(str(jpg))
    except Exception:
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    # ImageDescription — добавляем, не затирая
    descr_new = "ekcelo: " + " · ".join(filter(None, [cn, category, semantic]))
    existing = exif.get("0th", {}).get(piexif.ImageIFD.ImageDescription, b"")
    try:
        existing_s = existing.decode("utf-8", "ignore") if isinstance(existing, bytes) else str(existing)
    except Exception:
        existing_s = ""
    if existing_s and "ekcelo:" not in existing_s:
        descr_new = f"{existing_s} | {descr_new}"
    exif["0th"][piexif.ImageIFD.ImageDescription] = descr_new.encode("utf-8")

    # UserComment — JSON с метаданными миграции; ts_migrated отдельно от ts_photo
    ucomment = {
        "app": "ekcelo", "kind": "photo",
        "cad": cn, "category": category, "semantic": semantic,
        "source": source_path,
        "migrated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                              .replace("+00:00", "Z"),
    }
    exif.setdefault("Exif", {})[piexif.ExifIFD.UserComment] = UserComment.dump(
        json.dumps(ucomment, ensure_ascii=False), encoding="unicode")

    # GPS, DateTime*, Software — НЕ ТРОГАЕМ (остаются от оригинала)
    try:
        piexif.insert(piexif.dump(exif), str(jpg))
    except Exception as e:
        cp(f"    [exif] не записан в {jpg.name}: {e}", C.Y)

    # Восстанавливаем mtime/atime — иначе move/insert обновит их
    if stat is not None:
        try: os.utime(jpg, (stat.st_atime, stat.st_mtime))
        except Exception: pass


def scan_unsorted(root: Path) -> dict:
    """Просматривает Не_распределено/ в корне болванки, формирует план
    миграции для любых типов файлов.

    Для каждого *.jpg ищет КН по приоритету:
      1) КН в цепочке родительских папок (включая 12-15-значный «плоский»);
      2) КН в братском PDF/XML той же папки;
      3) адресный матчинг по верхней папке (≥2 общих токена). Если по адресу
         больше 1 КН и в пути нет уточняющего КН — фото остаётся, в логе
         фиксируется неоднозначность.

    Тип объекта берётся из json/objects/<КН>.json; при отсутствии — из
    текста пути (квартира→room, жилой дом→building, ЗУ/зу/земучасток→land).

    Семантические подпапки нормализуются по словарю (Вход_в_объект,
    Подвал, Состояние_внутри, Вид_от_окна, Кухня, Санузел, …) и
    сохраняются в полном виде иерархии."""
    src = root / UNSORTED_DIR
    plan: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                                .replace("+00:00", "Z"),
        "items": [],
        "address_ambiguous": {},
    }
    if not src.exists(): return plan

    obj_types, obj_addrs = load_objects_index(root)

    for f in sorted(src.rglob("*")):
        if not f.is_file(): continue
        rel = f.relative_to(src)
        parts = list(rel.parts)
        full_text = " ".join(parts)
        evidence: list[str] = []
        kind_label = "photo" if _is_photo(f) else f.suffix.lower().lstrip(".") or "file"

        # Не-фото файлы: PDF/XML/DOC/XLS/DB/HTML/JSON/KML/KMZ → отдельные корни.
        # Их КН/категория не нужны: они идут в Выписки_PDF/<подпапка>, doc/,
        # XLSX/, DB/, HTML/, json/, KMZ-KML/ — независимо от КН.
        if not _is_photo(f):
            target = _route_non_photo(root, f)
            if target is None:
                plan["items"].append({
                    "from": str(f.relative_to(root)).replace("\\", "/"),
                    "to":   None,
                    "kind": kind_label,
                    "reason": "неизвестный тип файла",
                })
                continue
            plan["items"].append({
                "from": str(f.relative_to(root)).replace("\\", "/"),
                "to":   str(target.relative_to(root)).replace("\\", "/"),
                "kind": kind_label,
                "evidence": ["routing_by_extension"],
            })
            continue

        # ──── фото: ищем КН и семантику ────
        # 1) КН в полном пути
        cads = find_cads_in_text(full_text)
        cn = cads[0] if cads else None
        if cn: evidence.append(f"cn_in_path:{cn}")

        # 2) КН в братских PDF/XML
        if not cn:
            for sibling in f.parent.iterdir():
                if sibling.suffix.lower() in (".pdf", ".xml"):
                    if sibling.suffix.lower() == ".pdf":
                        body = extract_text_any(sibling)
                    else:
                        try: body = sibling.read_text(encoding="utf-8", errors="ignore")
                        except Exception: body = ""
                    sib_cads = find_cads_in_text(body)
                    if sib_cads:
                        cn = sib_cads[0]
                        evidence.append(f"cn_in_sibling:{sibling.name}"); break

        # 3) Адресный матчинг по верхней папке
        addr_folder = parts[0] if parts else ""
        if not cn and obj_addrs:
            folder_t = address_tokens(addr_folder.replace("_", " ").replace("-", " "))
            cands = [(c, len(folder_t & ta)) for c, ta in obj_addrs.items()
                     if len(folder_t & ta) >= 2]
            cands.sort(key=lambda x: -x[1])
            if len(cands) == 1:
                cn = cands[0][0]; evidence.append(f"address_unique:{addr_folder}")
            elif len(cands) > 1:
                plan["address_ambiguous"].setdefault(addr_folder, {
                    "candidates": [c for c, _ in cands], "photos": 0,
                })
                plan["address_ambiguous"][addr_folder]["photos"] += 1

        # 4) Категория
        category = None
        if cn:
            category = OBJ_TYPE_TO_CAT.get(obj_types.get(cn, "").lower())
            if not category:
                t = detect_category_from_text(full_text)
                if t: category = OBJ_TYPE_TO_CAT.get(t)

        # 5) Семантическая цепочка (полная иерархия)
        sem_chain: list[str] = []
        for p in parts[:-1]:
            sem = folder_semantic(p)
            if sem and (not sem_chain or sem_chain[-1] != sem):
                sem_chain.append(sem)
        sem_path = "/".join(sem_chain) if sem_chain else None

        if cn and category:
            target = (root / "Фотографии" / "Недвижимость" / category /
                      cn.replace(":", "_"))
            if sem_path: target = target / sem_path
            target = target / f.name
            plan["items"].append({
                "from": str(f.relative_to(root)).replace("\\", "/"),
                "to":   str(target.relative_to(root)).replace("\\", "/"),
                "kind": "photo",
                "cn": cn, "category": category, "semantic": sem_path,
                "evidence": evidence,
            })
        else:
            plan["items"].append({
                "from": str(f.relative_to(root)).replace("\\", "/"),
                "to":   None,
                "kind": "photo",
                "reason": "КН/категория не определены",
                "evidence": evidence,
            })

    return plan


def action_sort(last_root: Path | None) -> None:
    """Меню 3: dry-run сортировка содержимого корневой Не_распределено/."""
    default = str(last_root) if last_root else ""
    prompt = (f"\nПуть к проекту [Enter — {default}]: " if default
              else "\nПуть к проекту: ")
    raw = input(prompt).strip() or default
    if not raw:
        cp("Путь не указан — отмена.", C.R); return
    root = Path(raw)
    src = root / UNSORTED_DIR
    if not src.exists():
        cp(f"Не нашёл {src}.", C.R); return

    cp(f"\nСканирую {UNSORTED_DIR}/ …", C.CY)
    plan = scan_unsorted(root)
    items = plan["items"]
    matched = [i for i in items if i.get("to")]
    cp(f"  фото проанализировано: {len(items)}", C.CY)
    cp(f"  с уверенной привязкой:  {len(matched)}",
       C.G if matched else C.Y)
    cp(f"  без привязки (останутся как есть): {len(items) - len(matched)}",
       C.CY)
    if plan["address_ambiguous"]:
        cp("\n  ⚠ адресные конфликты — несколько КН по одному адресу,"
           " переноса не будет:", C.Y)
        for folder, info in plan["address_ambiguous"].items():
            cp(f"     {folder}: фото {info['photos']}, кандидаты "
               + ", ".join(info["candidates"]), C.Y)

    plan_file = root / "json" / "photo_migration_plan.json"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    cp(f"\n  план сохранён: {plan_file.relative_to(root)}", C.CY)

    if not matched:
        cp("  переносить нечего.", C.Y); return

    # Сводка по типам
    by_kind: dict[str, int] = {}
    for it in matched: by_kind[it.get("kind", "photo")] = by_kind.get(it.get("kind", "photo"), 0) + 1
    cp(f"\n  по типам: " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())),
       C.CY)

    cp("\nПримеры (первые 8 из плана):", C.B)
    for it in matched[:8]:
        cp(f"  [{it.get('kind','?')}] {it['from']}")
        cp(f"    → {it['to']}", C.G)

    ans = input(f"\nПрименить план (перенести {len(matched)} файлов)? [y/N]: "
                ).strip().lower()
    if ans not in ("y", "yes", "д", "да"):
        cp("Отмена. План сохранён, файлы не перенесены.", C.CY); return

    moved = err = annotated = 0
    for it in matched:
        src_p = root / it["from"]
        dst_p = root / it["to"]
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        if dst_p.exists():
            continue  # идемпотентно
        try:
            # Сохраняем исходные mtime/atime, чтобы move не сдвинул
            try: stat = src_p.stat()
            except Exception: stat = None
            shutil.move(str(src_p), str(dst_p)); moved += 1
            if stat is not None:
                try: os.utime(dst_p, (stat.st_atime, stat.st_mtime))
                except Exception: pass
            # Дописываем привязку в EXIF только для JPG; даты съёмки и GPS
            # оригинала сохраняются. Для не-фото — ничего не меняем.
            if it.get("kind") == "photo" and it.get("cn"):
                annotate_photo_exif(dst_p, it["cn"], it.get("category"),
                                    it.get("semantic"), it["from"])
                annotated += 1
        except Exception as e:
            cp(f"  [err] {src_p.name}: {e}", C.R); err += 1
    cp(f"\n  перенесено: {moved}, фото с записью EXIF: {annotated}"
       + (f", ошибок: {err}" if err else ""), C.G)


def main() -> None:
    cp("=" * 64, C.B)
    cp(" pirushin_sosn_rocha_07_init_project_v1 — структура + конвертация", C.B)
    cp("=" * 64, C.B)
    last_root: Path | None = None
    while True:
        cp("\n  1  Создание структуры (новая болванка)", C.CY)
        cp("  2  Конвертация PDF → JPG (из Выписки_PDF/)", C.CY)
        cp("  3  Сортировка папки Не_распределено/ (в корне болванки)", C.CY)
        cp("  4  Выход", C.CY)
        ch = input("\nВаш выбор: ").strip()
        if ch == "1":
            r = action_create()
            if r: last_root = r
        elif ch == "2":
            action_convert(last_root)
        elif ch == "3":
            action_sort(last_root)
        elif ch in ("4", "q", "exit", ""):
            cp("Готово.", C.B); return
        else:
            cp("Введите 1, 2 или 3.", C.Y)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: cp("\nПрервано.", C.Y)
