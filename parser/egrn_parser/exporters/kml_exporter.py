"""
egrn_parser/exporters/kml_exporter.py — контуры из БД в KML (CONTRACT_KMZ 2.13.0).

ЧТО ЭТО И ЧЕМ ОТЛИЧАЕТСЯ ОТ 08_build_kmz. Тот собирает ПРОЕКТ целиком: фото,
документы, граф связей, бизнес-единицы, бенефициары — и упаковывает в KMZ. Этот
модуль делает одну вещь: выдаёт контуры участков из §8 (`egrn_contour`) одним
.kml. Он нужен там, где проекта ещё нет — пришли выписки, надо посмотреть, что
где лежит, и отдать файл на объект.

ПОЧЕМУ ФОРМАТ ВСЁ РАВНО КОНТРАКТНЫЙ. Контрактная поверхность (CONTRACT_KMZ §2) —
это KMZ-архив, и отдельный .kml формально вне её. Но файл, написанный «как
удобно», через месяц попадёт во вьюер — и не откроется, потому что классификация
объектов там идёт по префиксу `styleUrl`, а разбор подписи — по парам
`Ключ: значение; `. Поэтому здесь соблюдены все инварианты §6, которые вообще
применимы к одиночному .kml:

  • префикс `cad_zu_` у Placemark и уникальный `Style id`;
  • кад.№ отдельным токеном в `<name>` и ключом `Кадастровый номер:` в
    `<description>`;
  • `<description>` — пары `Ключ: значение; `, без HTML и без `<img>`;
  • координаты `lon,lat`, кольцо замкнуто, ≥4 точки, WGS-84;
  • `kml_schema_version` = 2.1 и `<atom:author>` в `<Document>`;
  • `graph_node_id` в `<ExtendedData>` каждого Placemark — по формуле 04
    (`<КН>`), чтобы файл был drop-in для KMZ-пайплайна;
  • детерминизм: одинаковый вход → побитово одинаковый файл.

Не соблюдается ровно одно и намеренно: из десяти `<Folder>` создаётся одна —
«Земельные участки». Спека прямо разрешает (§A.3: «Пустые папки НЕ создаются»),
а больше здесь взяться неоткуда: в §8 только земля.

КАК СЮДА ПОПАДАЮТ ЧЗУ. Части участка (охранная зона ЛЭП, водоохранная полоса)
своего класса в контракте не имеют, и это не упущение — они не объекты учёта.
Но у контракта есть ровно для них оставленный суффикс: регулярка кад.№ в §6
допускает `/N` с подписью «часть/контур». Поэтому ЧЗУ и дополнительные контуры
многоконтурного участка идут отдельными Placemark с именем `<КН>/<N>` в той же
папке. Складывать их площадь с площадью участка нельзя — ЧЗУ лежит ВНУТРИ него
(см. obsidian/Database/egrn-geometry-8.md), поэтому в подписи у части стоит
«Часть участка», а не «Площадь участка».

ПОЧЕМУ ОДНА ГЕОМЕТРИЯ НА PLACEMARK, А НЕ MultiGeometry. Так требует §6
(«Геометрия: одна на Placemark»), и так же устроено хранение: в §8 строка = один
контур. Многоконтурный участок даёт N Placemark, у каждого своя площадь и свой
номер точки — именно то, что нужно человеку на объекте.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

__all__ = [
    "KML_SCHEMA_VERSION",
    "GENERATOR_NAME",
    "build_kml",
    "export_kml",
    "kml_filename",
]

KML_SCHEMA_VERSION = "2.1"
GENERATOR_NAME = "egrn_parser.exporters.kml_exporter"

# Цвета совпадают с STYLE_TABLE['zu'] в 08_build_kmz_v2_2.py. KML пишет цвет как
# AABBGGRR (альфа, синий, зелёный, красный) — не RGBA; перепутать порядок легко,
# и тогда зелёный контур становится красным.
ZU_LINE_COLOR = "ff007f00"
ZU_POLY_COLOR = "33007f00"
# Часть участка рисуется тем же зелёным, но тоньше и почти без заливки: она
# лежит поверх участка, и плотная заливка скрыла бы его границу.
PART_LINE_COLOR = "ffff7f00"
PART_POLY_COLOR = "22ff7f00"

FOLDER_ZU = "Земельные участки"
STYLE_PREFIX_ZU = "cad_zu_"

_CAD_TOKEN_RE = re.compile(r"^\d{2}:\d{2}:\d{2,8}:\d{1,8}(?:/\d+)?$")


def _esc(text: Any) -> str:
    """XML-экранирование для атрибутов и текстовых узлов вне CDATA."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


def _cad_id(cad_number: str) -> str:
    """КН → токен для `Style id` / `styleUrl`.

    `:` → `_`, `/` → `__`. Конвенция та же, что `cn_to_id_part` в
    08_build_kmz_v2_2.py: `/` внутри идентификатора ломает фрагмент URL, и
    styleUrl перестаёт указывать на стиль.
    """
    return cad_number.replace(":", "_").replace("/", "__")


def _kv(pairs: Iterable[tuple[str, Any]]) -> str:
    """Пары → `Ключ: значение; …` по §A.5.

    Пустые значения выбрасываются целиком (не пишем `Площадь: ;`), точка с
    запятой внутри значения заменяется на запятую — иначе разбор пар на стороне
    вьюера разъедется на первом же адресе с перечислением.
    """
    out: list[str] = []
    for key, value in pairs:
        if value is None or value == "":
            continue
        safe = str(value).replace(";", ",").replace("\n", " ").strip()
        if safe:
            out.append(f"{key}: {safe}")
    return "; ".join(out) + (";" if out else "")


def _num(value: Optional[float], digits: int = 1) -> Optional[str]:
    """Число → строка без хвостовых нулей. None остаётся None и выпадет из пар."""
    if value is None:
        return None
    text = f"{float(value):.{digits}f}"
    # Хвостовые нули срезаются ТОЛЬКО в дробной части: у целого «15120» такой
    # rstrip отрезает разряд и превращает участок в 1512 кв.м. Ошибка тихая —
    # число остаётся правдоподобным, и заметить её можно лишь сверив с выпиской.
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _extended_data(values: dict[str, Any]) -> str:
    rows = [f'<Data name="{_esc(k)}"><value>{_esc(v)}</value></Data>'
            for k, v in values.items() if v not in (None, "")]
    return "<ExtendedData>" + "".join(rows) + "</ExtendedData>" if rows else ""


def _coordinates(ring: list[list[float]]) -> str:
    """Кольцо GeoJSON → строка координат KML.

    GeoJSON и KML сходятся в порядке пары (lon, lat), и это единственное место,
    где они сходятся без оговорок. Кольцо замыкается, если выписка замыкающей
    точки не дала: KML требует её всегда.
    """
    pts = [(round(float(lon), 7), round(float(lat), 7)) for lon, lat in ring]
    if len(pts) >= 2 and pts[0] != pts[-1]:
        pts.append(pts[0])
    return " ".join(f"{lon},{lat}" for lon, lat in pts)


def _polygon_xml(geojson: dict) -> Optional[str]:
    """GeoJSON Polygon → `<Polygon>` с внешним кольцом и дырками."""
    rings = geojson.get("coordinates") or []
    if not rings or len(rings[0]) < 3:
        return None
    outer = (f"<outerBoundaryIs><LinearRing><coordinates>"
             f"{_coordinates(rings[0])}</coordinates></LinearRing></outerBoundaryIs>")
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{_coordinates(r)}"
        f"</coordinates></LinearRing></innerBoundaryIs>"
        for r in rings[1:] if len(r) >= 3)
    return f"<Polygon><tessellate>1</tessellate>{outer}{inner}</Polygon>"


def _style(style_id: str, *, line: str, poly: str, width: str = "2") -> str:
    return (f'<Style id="{_esc(style_id)}">'
            f"<LineStyle><color>{line}</color><width>{width}</width></LineStyle>"
            f"<PolyStyle><color>{poly}</color><fill>1</fill><outline>1</outline>"
            f"</PolyStyle></Style>")


# --- чтение из БД ---------------------------------------------------------

_SELECT = """
SELECT cad_number, kind, contour_no, contour_cad, part_number, part_mnemonic,
       geom_geojson, area_computed_sqm, area_declared_sqm, accuracy_m,
       sk_id, msk_zone, source, source_extract_number, source_file, extract_date
  FROM egrn_contour
 WHERE (:cad IS NULL OR cad_number = :cad)
   AND (:with_parts OR kind = 'parcel')
 ORDER BY cad_number, kind DESC, CAST(part_number AS INTEGER), part_number, contour_no
"""


def _object_facts(conn: sqlite3.Connection, cad_numbers: set[str]) -> dict[str, dict]:
    """Карточка объекта из `land_objects`, если таблица есть.

    Контуры сами по себе отвечают на «где», а человеку на объекте нужно ещё
    «что»: категория земель, разрешённое использование, адрес. Они приходят из
    того же разбора выписки (`xml_parser`), но живут в другой таблице, и её
    может не быть — БД, собранная только из геометрии, тоже валидна.
    """
    try:
        rows = conn.execute(
            "SELECT cad_number, address, area, land_category, permitted_uses, "
            "       cadastral_value, lifecycle_status_text "
            "  FROM land_objects").fetchall()
    except sqlite3.OperationalError:
        return {}
    keys = ("address", "area", "land_category", "permitted_uses",
            "cadastral_value", "status")
    return {r[0]: dict(zip(keys, r[1:])) for r in rows if r[0] in cad_numbers}


def _placemark_name(row: dict, facts: dict) -> str:
    """`<name>` Placemark. Кад.№ обязан быть отдельным токеном (§A.4)."""
    cad = row["cad_number"]
    if row["kind"] == "part":
        label = row["part_mnemonic"] or f"часть {row['part_number'] or '?'}"
        return f"{cad} · {label}"
    if row["_multi"]:
        return f"{cad}/{row['contour_no']}"
    short = (facts.get("address") or "").strip()
    if short and len(short) <= 60:
        return f"{cad} · {short}"
    return cad


def _description(row: dict, facts: dict) -> str:
    """`<description>` — пары по §A.5, порядок ключей фиксирован ради diff."""
    if row["kind"] == "part":
        return _kv([
            ("Кадастровый номер", row["cad_number"]),
            ("Часть участка", row["part_number"]),
            ("Зона", row["part_mnemonic"]),
            ("Площадь части", f"{_num(row['area_computed_sqm'])} кв.м"),
            ("Площадь по выписке", (f"{_num(row['area_declared_sqm'], 0)} кв.м"
                                    if row["area_declared_sqm"] is not None else None)),
            ("Точность", (f"{_num(row['accuracy_m'], 2)} м"
                          if row["accuracy_m"] is not None else None)),
            ("Система координат", row["sk_id"]),
            ("Источник", "выписка ЕГРН"),
            ("Выписка", row["source_extract_number"]),
            ("Дата выписки", row["extract_date"]),
        ])
    return _kv([
        ("Кадастровый номер", row["cad_number"]),
        ("Обособленный участок", row["contour_cad"]),
        ("Контур", f"{row['contour_no']}" if row["_multi"] else None),
        ("Площадь", f"{_num(row['area_computed_sqm'])} кв.м"),
        ("Площадь по выписке", (f"{_num(row['area_declared_sqm'], 0)} кв.м"
                                if row["area_declared_sqm"] is not None else None)),
        ("Категория", facts.get("land_category")),
        ("Разрешённое использование", facts.get("permitted_uses")),
        ("Адрес", facts.get("address")),
        ("Кадастровая стоимость", (f"{_num(facts.get('cadastral_value'), 2)} руб"
                                   if facts.get("cadastral_value") else None)),
        ("Статус", facts.get("status")),
        ("Точность", (f"{_num(row['accuracy_m'], 2)} м"
                      if row["accuracy_m"] is not None else None)),
        ("Система координат", row["sk_id"]),
        ("Источник", "выписка ЕГРН"),
        ("Выписка", row["source_extract_number"]),
        ("Дата выписки", row["extract_date"]),
    ])


def _style_id(row: dict) -> str:
    base = STYLE_PREFIX_ZU + _cad_id(row["cad_number"])
    if row["kind"] == "part":
        return f"{base}__p{_cad_id(str(row['part_number'] or row['contour_no']))}"
    if row["_multi"]:
        return f"{base}__{row['contour_no']}"
    return base


def build_kml(conn: sqlite3.Connection, *, cad_number: Optional[str] = None,
              with_parts: bool = True, title: Optional[str] = None,
              generated_on: Optional[str] = None) -> str:
    """Собрать документ KML одной строкой.

    `generated_on` фиксирует дату в шапке. По умолчанию — сегодняшняя, но
    округлённая до суток: контракт §6 требует, чтобы два прогона на одном входе
    давали побитово одинаковый файл, а секундная метка это ломает.
    """
    rows: list[dict] = []
    columns = ("cad_number", "kind", "contour_no", "contour_cad", "part_number",
               "part_mnemonic", "geom_geojson", "area_computed_sqm",
               "area_declared_sqm", "accuracy_m", "sk_id", "msk_zone", "source",
               "source_extract_number", "source_file", "extract_date")
    for raw in conn.execute(_SELECT, {"cad": cad_number,
                                      "with_parts": 1 if with_parts else 0}):
        rows.append(dict(zip(columns, raw)))

    # «Многоконтурный» определяется по числу контуров участка, а не по числу
    # строк вообще: части не делают участок многоконтурным.
    parcel_counts: dict[str, int] = {}
    for row in rows:
        if row["kind"] == "parcel":
            parcel_counts[row["cad_number"]] = parcel_counts.get(row["cad_number"], 0) + 1
    for row in rows:
        row["_multi"] = parcel_counts.get(row["cad_number"], 0) > 1

    facts = _object_facts(conn, {r["cad_number"] for r in rows})

    styles: list[str] = []
    placemarks: list[str] = []
    for row in rows:
        try:
            geojson = json.loads(row["geom_geojson"])
        except (TypeError, ValueError):
            continue
        polygon = _polygon_xml(geojson)
        if polygon is None:
            continue
        style_id = _style_id(row)
        is_part = row["kind"] == "part"
        styles.append(_style(
            style_id,
            line=PART_LINE_COLOR if is_part else ZU_LINE_COLOR,
            poly=PART_POLY_COLOR if is_part else ZU_POLY_COLOR,
            width="1.5" if is_part else "2"))
        object_facts = facts.get(row["cad_number"], {})
        extended = _extended_data({
            "object_type": "land",
            "cad_number": row["cad_number"],
            # Формула 04_nspd_graph для узла КН — просто сам КН. Держим её,
            # чтобы файл был drop-in для KMZ-пайплайна (контракт §6, 2.11.0+).
            "graph_node_id": row["cad_number"],
            "contour_no": row["contour_no"],
            "part_number": row["part_number"],
            "accuracy_m": row["accuracy_m"],
            "msk_zone": row["msk_zone"],
            "geom_source": row["source"],
            "schema_version": KML_SCHEMA_VERSION,
        })
        placemarks.append(
            "<Placemark>"
            f"<name><![CDATA[{_placemark_name(row, object_facts)}]]></name>"
            f"<styleUrl>#{_esc(style_id)}</styleUrl>"
            f"<description><![CDATA[{_description(row, object_facts)}]]></description>"
            f"{extended}{polygon}</Placemark>")

    day = generated_on or date.today().isoformat()
    doc_name = title or f"Контуры ЕГРН на {day}"
    doc_extended = _extended_data({
        "kml_schema_version": KML_SCHEMA_VERSION,
        "generator": GENERATOR_NAME,
        "generated_at": f"{day}T00:00:00Z",
        "extract_date": _dominant_extract_date(rows),
    })

    folder = ""
    if placemarks:
        folder = (f"<Folder><name>{_esc(FOLDER_ZU)} ({len(placemarks)})</name>"
                  f"<open>1</open>" + "".join(placemarks) + "</Folder>")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<Document>\n"
        f"<name><![CDATA[{doc_name}]]></name>\n"
        f"<description><![CDATA[Сгенерировано {GENERATOR_NAME} "
        f"(KML schema {KML_SCHEMA_VERSION})]]></description>\n"
        f"<atom:author><atom:name>{_esc(GENERATOR_NAME)}</atom:name></atom:author>\n"
        f"{doc_extended}\n"
        + "".join(styles) + folder +
        "\n</Document>\n</kml>\n")


def _dominant_extract_date(rows: list[dict]) -> Optional[str]:
    """Дата выписки для `<Document>` (контракт 2.12.0+).

    Выписки в одном файле могут быть разных дат; в шапку идёт САМАЯ ПОЗДНЯЯ —
    она отвечает на вопрос «на какое число этот снимок актуален», а самая
    ранняя не отвечает ни на какой. У каждого Placemark своя дата в подписи.
    """
    dates = sorted({r["extract_date"] for r in rows if r.get("extract_date")})
    return dates[-1] if dates else None


def kml_filename(cad_number: Optional[str], day: Optional[str] = None) -> str:
    day = day or date.today().isoformat()
    if cad_number:
        return f"Контуры_ЕГРН_{cad_number.replace(':', '-')}_на_{day}.kml"
    return f"Контуры_ЕГРН_на_{day}.kml"


def export_kml(conn: sqlite3.Connection, out_path: Path | str, **kwargs) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_kml(conn, **kwargs), encoding="utf-8")
    return path
