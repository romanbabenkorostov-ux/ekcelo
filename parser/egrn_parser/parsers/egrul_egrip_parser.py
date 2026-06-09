"""
egrn_parser/parsers/egrul_egrip_parser.py — парсер XML-выписок ФНС из
ЕГРЮЛ (юрлица) и ЕГРИП (индивидуальные предприниматели).

Это НЕ выписки Росреестра (ЕГРН-объекты) — для них см. `xml_parser.py`.
Здесь — реестр ФНС: субъект (организация / ИП) + корпоративные связи
(руководители, управляющие организации, учредители, право-предшественники
и право-преемники).

Версионирование и автоопределение
---------------------------------
Формат опознаётся по корню `Файл` и его атрибутам:
  • `@ВерсФорм`  — версия формата ("4.08" — ЕГРЮЛ, "4.07" — ЕГРИП);
  • `@ТипИнф`    — тип сведений ("ЕГРЮЛ_ОТКР_СВЕД" / "ЕГРИП_ОТКР_СВЕД" / …).
Реестр (ЕГРЮЛ/ЕГРИП) определяется по `@ТипИнф`, версия — по `@ВерсФорм`.
Поддерживаемые пары перечислены в `SUPPORTED_FORMATS`; XSD-схемы лежат
в `parser/schema/xsd/{egrul,egrip}/` (по одной папке на реестр, новые
редакции кладутся рядом — берётся самая свежая по сортировке имени).

Схема ФНС не имеет targetNamespace, поэтому обход идёт по «голым»
локальным тегам (без префиксов). Файлы ФНС — в кодировке windows-1251;
`ElementTree.parse` подхватывает кодировку из XML-пролога автоматически.

Парсер возвращает нормализованную запись (см. `egrul_egrip_normalized.empty_record`),
единую по форме для будущих источников (checko/dadata JSON, PDF) —
маппинг «один источник → одна нормализованная запись».
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from egrn_parser.parsers._common import parse_number
from egrn_parser.parsers.egrul_egrip_normalized import empty_record

log = logging.getLogger(__name__)

# ── Версионный реестр ───────────────────────────────────────────────────────
# Папки с XSD-схемами (по реестру). Внутри — одна или несколько редакций;
# берётся самая свежая по сортировке имени файла (как в xsd/upd).
_XSD_ROOT = Path(__file__).resolve().parents[2] / "schema" / "xsd"
XSD_DIRS: dict[str, Path] = {
    "ЕГРЮЛ": _XSD_ROOT / "egrul",
    "ЕГРИП": _XSD_ROOT / "egrip",
}

# Поддерживаемые пары (реестр, версия формата). При выходе новой редакции
# ФНС — добавить версию сюда и положить XSD в соответствующую папку.
SUPPORTED_FORMATS: set[tuple[str, str]] = {
    ("ЕГРЮЛ", "4.08"),
    ("ЕГРИП", "4.07"),
}

# Соответствие @ТипИнф → реестр (берётся префикс до первого «_»).
_INFO_TYPE_TO_REGISTRY = {
    "ЕГРЮЛ": "ЕГРЮЛ",
    "ЕГРИП": "ЕГРИП",
}


@dataclass
class FnsFormat:
    """Опознанный формат выписки ФНС."""

    registry: str           # "ЕГРЮЛ" | "ЕГРИП"
    version: str            # "4.08" | "4.07" | …
    info_type: str          # "ЕГРЮЛ_ОТКР_СВЕД" | …
    file_id: Optional[str] = None

    @property
    def supported(self) -> bool:
        return (self.registry, self.version) in SUPPORTED_FORMATS


# ── XML-хелперы (обход по локальным тегам, namespace-agnostic) ───────────────
def _tag(elem: ET.Element) -> str:
    tag = elem.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag


def _find(root: Optional[ET.Element], *path: str) -> Optional[ET.Element]:
    """Первый вложенный элемент по цепочке локальных тегов."""
    cur = root
    for name in path:
        if cur is None:
            return None
        nxt = None
        for child in cur:
            if _tag(child) == name:
                nxt = child
                break
        cur = nxt
    return cur


def _findall(root: Optional[ET.Element], name: str) -> list[ET.Element]:
    """Все прямые дети с данным локальным тегом."""
    if root is None:
        return []
    return [c for c in root if _tag(c) == name]


def _attr(elem: Optional[ET.Element], name: str) -> Optional[str]:
    if elem is None:
        return None
    v = elem.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _fio(elem: Optional[ET.Element]) -> Optional[dict]:
    """ФИО из атрибутов Фамилия/Имя/Отчество (ФИОТип / ФИО1Тип)."""
    if elem is None:
        return None
    fio = {
        "last": _attr(elem, "Фамилия"),
        "first": _attr(elem, "Имя"),
        "middle": _attr(elem, "Отчество"),
    }
    return fio if any(fio.values()) else None


# ── Определение формата ──────────────────────────────────────────────────────
def detect_format(xml_path: Path | str) -> Optional[FnsFormat]:
    """Опознать формат выписки ФНС по корню `Файл`. None — если это не она."""
    try:
        root = ET.parse(str(xml_path)).getroot()
    except Exception as exc:  # noqa: BLE001 — битый/чужой файл
        log.debug("detect_format: не удалось распарсить %s: %s", xml_path, exc)
        return None
    if _tag(root) != "Файл":
        return None
    info_type = _attr(root, "ТипИнф") or ""
    version = _attr(root, "ВерсФорм") or ""
    registry = _INFO_TYPE_TO_REGISTRY.get(info_type.split("_", 1)[0])
    if registry is None:
        return None
    return FnsFormat(
        registry=registry,
        version=version,
        info_type=info_type,
        file_id=_attr(root, "ИдФайл"),
    )


def is_fns_reestr_xml(xml_path: Path | str) -> bool:
    """True, если файл — выписка ЕГРЮЛ/ЕГРИП ФНС (любой опознанной версии)."""
    return detect_format(xml_path) is not None


def find_xsd(registry: str, version: Optional[str] = None) -> Optional[Path]:
    """Путь к XSD для реестра. Берём самую свежую редакцию по имени файла.

    `version` сейчас служит фильтром-подсказкой (имя редакции ФНС не всегда
    содержит номер версии формата), но если файл с подстрокой версии есть —
    предпочитаем его.
    """
    folder = XSD_DIRS.get(registry)
    if folder is None or not folder.is_dir():
        return None
    xsds = sorted(folder.glob("*.xsd"))
    if not xsds:
        return None
    if version:
        flat = version.replace(".", "")  # "4.08" → "408"
        for p in reversed(xsds):
            if version in p.name or flat in p.name:
                return p
    return xsds[-1]


def validate(xml_path: Path | str) -> list[str]:
    """Провалидировать XML по XSD ФНС. Пустой список — валиден.

    Требует lxml (ElementTree не умеет XSD). Если lxml нет — возвращаем
    одну запись-предупреждение, не падаем.
    """
    fmt = detect_format(xml_path)
    if fmt is None:
        return ["Не выписка ЕГРЮЛ/ЕГРИП: корень не `Файл` или неизвестный ТипИнф"]
    xsd_path = find_xsd(fmt.registry, fmt.version)
    if xsd_path is None:
        return [f"XSD для {fmt.registry} не найден в {XSD_DIRS.get(fmt.registry)}"]
    try:
        from lxml import etree
    except ImportError:
        return ["lxml не установлен — XSD-валидация пропущена"]
    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    doc = etree.parse(str(xml_path))
    if schema.validate(doc):
        return []
    return [f"{e.line}: {e.message}" for e in schema.error_log]


# ── ЕГРЮЛ ────────────────────────────────────────────────────────────────────
def _org_ident(elem: Optional[ET.Element]) -> dict:
    """ОГРН/ИНН/НаимЮЛПолн из НаимИННЮЛ (СвЮЛЕГРЮЛТип) — учредитель/преемник."""
    return {
        "ogrn": _attr(elem, "ОГРН"),
        "inn": _attr(elem, "ИНН"),
        "name": _attr(elem, "НаимЮЛПолн"),
    }


def _parse_share(elem: Optional[ET.Element]) -> dict:
    """Доля в УК из ДоляУстКап (процент и/или номинал в рублях)."""
    if elem is None:
        return {}
    out: dict[str, Any] = {}
    nominal = _attr(elem, "НоминСтоим")
    if nominal:
        out["share_nominal"] = parse_number(nominal)
    proc = _find(elem, "РазмерДоли", "Процент")
    if proc is not None and proc.text:
        out["share_percent"] = parse_number(proc.text)
    frac = _find(elem, "РазмерДоли", "ДробДесят")
    if frac is not None and frac.text:
        out["share_fraction"] = frac.text.strip()
    return out


def _parse_egrul(doc: ET.Element, rec: dict) -> None:
    sv = _find(doc, "СвЮЛ")
    if sv is None:
        return
    naim = _find(sv, "СвНаимЮЛ")
    rec["subject"] = {
        "kind": "org",
        "ogrn": _attr(sv, "ОГРН"),
        "inn": _attr(sv, "ИНН"),
        "kpp": _attr(sv, "КПП"),
        "opf_code": _attr(sv, "КодОПФ"),
        "opf_name": _attr(sv, "ПолнНаимОПФ"),
        "reg_date": _attr(sv, "ДатаОГРН"),
        "name_full": _attr(naim, "НаимЮЛПолн"),
        "name_short": _attr(_find(naim, "СвНаимЮЛСокр"), "НаимСокр"),
    }
    # Статус (ликвидация/реорганизация/недействующее …)
    status = _find(sv, "СвСтатус", "СвСтатус")
    if status is not None:
        rec["subject"]["status"] = {
            "code": _attr(status, "КодСтатусЮЛ"),
            "name": _attr(status, "НаимСтатусЮЛ"),
        }
    # ОКВЭД основной
    okved = _find(sv, "СвОКВЭД", "СвОКВЭДОсн")
    if okved is not None:
        rec["subject"]["okved_main"] = {
            "code": _attr(okved, "КодОКВЭД"),
            "name": _attr(okved, "НаимОКВЭД"),
        }

    # Руководители — физлица (ЕИО)
    for d in _findall(sv, "СведДолжнФЛ"):
        post = _find(d, "СвДолжн")
        rec["directors"].append({
            "fio": _fio(_find(d, "СвФЛ")),
            "inn": _attr(_find(d, "СвФЛ"), "ИННФЛ"),
            "post": _attr(post, "НаимДолжн"),
            "post_kind": _attr(post, "НаимВидДолжн"),
            "post_kind_code": _attr(post, "ВидДолжн"),
            "ogrnip": _attr(post, "ОГРНИП"),
        })

    # Управляющие организации (ЕИО — юрлицо)
    for m in _findall(sv, "СвУпрОрг"):
        ident = _find(m, "НаимИННЮЛ")
        rec["managing_orgs"].append({
            "ogrn": _attr(ident, "ОГРН"),
            "inn": _attr(ident, "ИНН"),
            "name": _attr(ident, "НаимЮЛПолн"),
        })

    # Учредители / участники
    uchr = _find(sv, "СвУчредит")
    if uchr is not None:
        for fr in _findall(uchr, "УчрЮЛРос"):
            rec["founders"].append({
                "kind": "legal_ru",
                **_org_ident(_find(fr, "НаимИННЮЛ")),
                **_parse_share(_find(fr, "ДоляУстКап")),
            })
        for fr in _findall(uchr, "УчрЮЛИн"):
            rec["founders"].append({
                "kind": "legal_foreign",
                **_org_ident(_find(fr, "НаимИННЮЛ")),
                **_parse_share(_find(fr, "ДоляУстКап")),
            })
        for fr in _findall(uchr, "УчрФЛ"):
            rec["founders"].append({
                "kind": "person",
                "fio": _fio(_find(fr, "СвФЛ")),
                "inn": _attr(_find(fr, "СвФЛ"), "ИННФЛ"),
                **_parse_share(_find(fr, "ДоляУстКап")),
            })

    # Реорганизация: право-предшественники и право-преемники
    for p in _findall(sv, "СвПредш"):
        rec["predecessors"].append(_org_ident(p))
    for p in _findall(sv, "СвПреем"):
        rec["successors"].append(_org_ident(p))


# ── ЕГРИП ────────────────────────────────────────────────────────────────────
def _parse_egrip(doc: ET.Element, rec: dict) -> None:
    sv = _find(doc, "СвИП")
    if sv is None:
        return
    fl = _find(sv, "СвФЛ")
    rec["subject"] = {
        "kind": "person",
        "ogrnip": _attr(sv, "ОГРНИП"),
        "inn": _attr(sv, "ИННФЛ"),
        "ip_kind_code": _attr(sv, "КодВидИП"),
        "ip_kind": _attr(sv, "НаимВидИП"),
        "reg_date": _attr(sv, "ДатаОГРНИП"),
        "fio": _fio(_find(fl, "ФИОРус")),
        "gender": _attr(fl, "Пол"),
    }
    status = _find(sv, "СвСтатус", "СвСтатус")
    if status is not None:
        rec["subject"]["status"] = {
            "code": _attr(status, "КодСтатус"),
            "name": _attr(status, "НаимСтатус"),
        }
    okved = _find(sv, "СвОКВЭД", "СвОКВЭДОсн")
    if okved is not None:
        rec["subject"]["okved_main"] = {
            "code": _attr(okved, "КодОКВЭД"),
            "name": _attr(okved, "НаимОКВЭД"),
        }


# ── Точка входа ──────────────────────────────────────────────────────────────
def parse(xml_path: Path | str) -> dict[str, Any]:
    """Распарсить выписку ЕГРЮЛ/ЕГРИП → {format, records:[нормализ. запись, …]}.

    Каждый `Документ` файла → одна запись. Бросает ValueError, если файл
    не распознан как выписка ФНС или версия не поддерживается.
    """
    xml_path = Path(xml_path)
    fmt = detect_format(xml_path)
    if fmt is None:
        raise ValueError(f"{xml_path}: не выписка ЕГРЮЛ/ЕГРИП ФНС")
    if not fmt.supported:
        raise ValueError(
            f"{xml_path}: формат {fmt.registry} версии '{fmt.version}' не поддержан "
            f"(известные: {sorted(SUPPORTED_FORMATS)})"
        )

    root = ET.parse(str(xml_path)).getroot()
    parse_doc = _parse_egrul if fmt.registry == "ЕГРЮЛ" else _parse_egrip

    records: list[dict] = []
    for doc in _findall(root, "Документ"):
        rec = empty_record(fmt.registry)
        rec["source"] = {
            "system": f"ФНС-{fmt.registry}-XML",
            "version": fmt.version,
            "info_type": fmt.info_type,
            "file": xml_path.name,
            "doc_id": _attr(doc, "ИдДок"),
            "issued_at": _attr(doc, "ДатаВып"),
        }
        parse_doc(doc, rec)
        records.append(rec)

    return {
        "format": {
            "registry": fmt.registry,
            "version": fmt.version,
            "info_type": fmt.info_type,
            "file_id": fmt.file_id,
        },
        "records": records,
    }
