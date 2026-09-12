"""
egrn_parser/parsers/manual_contours.py — ручные примерные контуры и конфликты
с выпиской (ADR-008, миграция 0007 §9).

ЗАЧЕМ. У части объектов контура нет вовсе — кадастровые инженеры до них ещё не
дошли, а работать надо уже сейчас. Экономист обводит участок примерно: по
снимку, по забору, со слов арендатора. Потом приходит выписка ЕГРН с настоящим
контуром, и возникает вопрос, который нельзя решать за человека.

ПОЧЕМУ РУЧНОЙ КОНТУР НЕ ЛОЖИТСЯ В `egrn_contour`. §8 объявлен частью слепка
ЕГРН: он воспроизводится из выписок целиком. Ручная обводка из выписки не
воспроизводится никогда — попав туда, она ломает базовый инвариант проекта
(CLAUDE.md §3). Поэтому ручные контуры живут своей таблицей `manual_contour`,
не-ЕГРН слоем с `confidence`, как §6 и §7.

ПОЧЕМУ ВЫПИСКА НЕ ЗАМЕНЯЕТ ОБВОДКУ МОЛЧА. Ручной контур мог быть согласован с
заказчиком, лечь в акт, уехать в отчёт. «Появился уточнённый контур» — это
решение, а не техническая деталь: иногда исходный оставляют намеренно, потому
что на нём построена уже сданная работа. Поэтому встреча записывается строкой
в `contour_conflict` и ждёт человека, а до решения текущим остаётся РУЧНОЙ
контур: молча подменить то, что уже ушло в акт, хуже, чем показать расхождение.

ИДЕМПОТЕНТНОСТЬ. Повторная загрузка того же файла обновляет геометрию по ключу
(КН, номер контура), а не плодит копии, и НЕ заводит второй конфликт: открытый
конфликт на объект может быть только один.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from egrn_parser.parsers import xml_geometry_db as _geo_db

log = logging.getLogger(__name__)

__all__ = [
    "ManualContour",
    "ImportReport",
    "parse_kml_contours",
    "parse_geojson_contours",
    "load_contours",
    "import_manual_contours",
    "detect_conflicts",
    "resolve_conflict",
    "open_conflicts",
    "current_contours",
]

CAD_RE = re.compile(r"\b\d{1,2}:\d{1,2}:\d{1,8}:\d{1,8}\b")
KML_NS = "{http://www.opengis.net/kml/2.2}"

# Эллипсоид WGS-84 для площади контура. Сфера радиусом 6371 км, стоявшая здесь
# раньше, давала систематический минус 0.22 % — на участке 4416 м² это 10 м².
# Для обводки по спутнику такая погрешность незаметна, но контур с кадастровой
# карты НСПД точен до дециметров, и сверка его площади с выпиской (это и есть
# признак конфликта) упиралась в ошибку формулы, а не источника. С радиусами
# кривизны на широте участка расхождение падает до 1 м².
_WGS_A = 6378137.0
_WGS_E2 = 0.00669437999014


@dataclass
class ManualContour:
    """Один обведённый вручную контур."""

    cad_number: str
    rings: list[list[tuple[float, float]]]     # [(lon, lat), ...] — внешнее кольцо первым
    contour_no: int = 1
    source: str = "kml"
    source_file: Optional[str] = None
    author: Optional[str] = None
    note: Optional[str] = None
    confidence: float = 0.5

    def to_geojson(self) -> dict:
        rings: list[list[list[float]]] = []
        for ring in self.rings:
            points = [[round(lon, 7), round(lat, 7)] for lon, lat in ring]
            if points and points[0] != points[-1]:
                points.append(points[0])
            rings.append(points)
        return {"type": "Polygon", "coordinates": rings}

    def area_sqm(self) -> float:
        """Площадь внешнего кольца минус дырки."""
        if not self.rings:
            return 0.0
        return (_ring_area_sqm(self.rings[0])
                - sum(_ring_area_sqm(r) for r in self.rings[1:]))

    def centroid(self) -> Optional[tuple[float, float]]:
        if not self.rings or not self.rings[0]:
            return None
        ring = self.rings[0]
        if len(ring) >= 2 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if not ring:
            return None
        return (round(sum(p[0] for p in ring) / len(ring), 7),
                round(sum(p[1] for p in ring) / len(ring), 7))


def _ring_area_sqm(ring: list[tuple[float, float]]) -> float:
    """Площадь кольца [(lon, lat), ...] в м².

    Локальная развёртка по радиусам кривизны эллипсоида на широте кольца, затем
    шнурование. Строгая площадь на эллипсоиде здесь не нужна: кольца — участки
    в сотни метров, и разница с ней на таком размере уходит в сантиметры, а вот
    зависимость от геодезической библиотеки была бы вполне реальной.
    """
    points = list(ring)
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        return 0.0
    lat0 = math.radians(sum(p[1] for p in points) / len(points))
    sin2 = math.sin(lat0) ** 2
    # N — радиус кривизны первого вертикала, M — меридианного сечения.
    radius_n = _WGS_A / math.sqrt(1.0 - _WGS_E2 * sin2)
    radius_m = _WGS_A * (1.0 - _WGS_E2) / (1.0 - _WGS_E2 * sin2) ** 1.5
    m_per_deg_lat = radius_m * math.pi / 180.0
    m_per_deg_lon = radius_n * math.pi / 180.0 * math.cos(lat0)
    flat = [(lon * m_per_deg_lon, lat * m_per_deg_lat) for lon, lat in points]
    total = 0.0
    for i, (x1, y1) in enumerate(flat):
        x2, y2 = flat[(i + 1) % len(flat)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


@dataclass
class ImportReport:
    """Итог загрузки — и для консоли, и для таблицы в окне."""

    imported: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"загружено: {len(self.imported)}", f"обновлено: {len(self.updated)}",
                 f"пропущено: {len(self.skipped)}"]
        if self.conflicts:
            parts.append(f"КОНФЛИКТОВ: {len(self.conflicts)}")
        return "; ".join(parts)


# --- чтение файлов --------------------------------------------------------

def _cad_from_placemark(placemark: ET.Element) -> Optional[str]:
    """КН из `<name>` или `<description>` Placemark.

    Конвенция та же, что у `kml_apply_nspd_contours._cadastre_in_description`:
    человек, рисующий контур в Google Earth или Яндекс.Конструкторе, пишет
    кадастровый номер в подпись. Ищем и в имени, и в описании — в разных
    редакторах удобно по-разному, а требовать одного было бы вредным
    формализмом.
    """
    for tag in ("name", "description"):
        node = placemark.find(f"{KML_NS}{tag}")
        if node is not None and node.text:
            found = CAD_RE.search(node.text)
            if found:
                return found.group(0)
    return None


def _rings_from_kml_polygon(polygon: ET.Element) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    for boundary, _kind in ((f"{KML_NS}outerBoundaryIs", "outer"),
                            (f"{KML_NS}innerBoundaryIs", "inner")):
        for node in polygon.findall(boundary):
            coords = node.find(f".//{KML_NS}coordinates")
            if coords is None or not coords.text:
                continue
            ring: list[tuple[float, float]] = []
            for chunk in coords.text.split():
                parts = chunk.split(",")
                if len(parts) >= 2:
                    ring.append((float(parts[0]), float(parts[1])))
            if len(ring) >= 3:
                rings.append(ring)
    return rings


def parse_kml_contours(path: Path | str, **defaults) -> list[ManualContour]:
    """KML → ручные контуры. Placemark без КН в подписи пропускается.

    `source` перекрывается через `defaults`: обводка по спутнику («kml») и
    контур, снятый с кадастровой карты НСПД («nspd»), различаются точностью на
    два порядка, и при споре с выпиской человек решает по этой подписи. Одно
    слово «kml» на оба случая делало бы решение угадыванием.

    Пропуск намеренно молчаливый в возвращаемом значении и громкий в логе:
    в файле человека почти всегда есть посторонние метки (точки съёмки,
    подписи), и ронять загрузку из-за них незачем.
    """
    path = Path(path)
    root = ET.parse(str(path)).getroot()
    by_cad: dict[str, list[ManualContour]] = {}
    for placemark in root.iter(f"{KML_NS}Placemark"):
        cad = _cad_from_placemark(placemark)
        if not cad:
            log.info("%s: Placemark без кадастрового номера пропущен", path.name)
            continue
        for polygon in placemark.iter(f"{KML_NS}Polygon"):
            rings = _rings_from_kml_polygon(polygon)
            if not rings:
                continue
            bucket = by_cad.setdefault(cad, [])
            bucket.append(ManualContour(
                cad_number=cad, rings=rings, contour_no=len(bucket) + 1,
                source=defaults.get("source", "kml"),
                source_file=path.name,
                **{k: v for k, v in defaults.items() if k != "source"}))
    return [c for bucket in by_cad.values() for c in bucket]


def parse_geojson_contours(path: Path | str, **defaults) -> list[ManualContour]:
    """GeoJSON FeatureCollection → ручные контуры.

    КН берётся из `properties`: `cad_number`, `cadastral_number`, `cn` или
    `name` — четыре написания, потому что файл приходит из четырёх разных
    редакторов, а переименовывать поле руками человек не будет.
    """
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = (payload.get("features") if payload.get("type") == "FeatureCollection"
                else [payload])
    by_cad: dict[str, list[ManualContour]] = {}
    for feature in features or []:
        properties = feature.get("properties") or {}
        cad = None
        for key in ("cad_number", "cadastral_number", "cn", "name"):
            found = CAD_RE.search(str(properties.get(key) or ""))
            if found:
                cad = found.group(0)
                break
        geometry = feature.get("geometry") or {}
        if not cad or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        polygons = ([geometry["coordinates"]] if geometry["type"] == "Polygon"
                    else geometry["coordinates"])
        for polygon in polygons:
            rings = [[(float(x), float(y)) for x, y in ring]
                     for ring in polygon if len(ring) >= 3]
            if not rings:
                continue
            bucket = by_cad.setdefault(cad, [])
            bucket.append(ManualContour(
                cad_number=cad, rings=rings, contour_no=len(bucket) + 1,
                source=defaults.get("source", "geojson"),
                source_file=path.name,
                **{k: v for k, v in defaults.items() if k != "source"}))
    return [c for bucket in by_cad.values() for c in bucket]


def load_contours(path: Path | str, **defaults) -> list[ManualContour]:
    """Файл → ручные контуры; формат по расширению."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".kml":
        return parse_kml_contours(path, **defaults)
    if suffix in (".geojson", ".json"):
        return parse_geojson_contours(path, **defaults)
    raise ValueError(f"неизвестный формат {suffix}: ожидался .kml или .geojson")


# --- запись и конфликты ---------------------------------------------------

_UPSERT = """
INSERT INTO manual_contour
    (cad_number, contour_no, geom_geojson, area_computed_sqm,
     centroid_lon, centroid_lat, source, source_file, author, note, confidence)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (cad_number, contour_no) DO UPDATE SET
    geom_geojson      = excluded.geom_geojson,
    area_computed_sqm = excluded.area_computed_sqm,
    centroid_lon      = excluded.centroid_lon,
    centroid_lat      = excluded.centroid_lat,
    source            = excluded.source,
    source_file       = COALESCE(excluded.source_file, manual_contour.source_file),
    author            = COALESCE(excluded.author, manual_contour.author),
    note              = COALESCE(excluded.note, manual_contour.note),
    confidence        = excluded.confidence,
    updated_at        = datetime('now'),
    -- Повторная загрузка ВОЗВРАЩАЕТ отозванный контур в работу: человек
    -- сознательно подал тот же файл снова, и это его решение, а не случайность.
    retired_at        = NULL,
    retired_reason    = NULL
"""


def import_manual_contours(conn: sqlite3.Connection,
                           contours: list[ManualContour]) -> ImportReport:
    """Записать ручные контуры; сразу же проверить встречу с выпиской."""
    _geo_db.ensure_schema(conn)
    report = ImportReport()
    for contour in contours:
        if not contour.cad_number:
            report.skipped.append(("?", "нет кадастрового номера"))
            continue
        area = contour.area_sqm()
        if area <= 0:
            report.skipped.append((contour.cad_number, "вырожденный контур"))
            continue
        existed = conn.execute(
            "SELECT 1 FROM manual_contour WHERE cad_number=? AND contour_no=?",
            (contour.cad_number, contour.contour_no)).fetchone() is not None
        centroid = contour.centroid()
        conn.execute(_UPSERT, (
            contour.cad_number, contour.contour_no,
            json.dumps(contour.to_geojson(), ensure_ascii=False,
                       separators=(",", ":"), sort_keys=True),
            round(area, 2),
            centroid[0] if centroid else None,
            centroid[1] if centroid else None,
            contour.source, contour.source_file, contour.author, contour.note,
            contour.confidence))
        (report.updated if existed else report.imported).append(contour.cad_number)
    conn.commit()
    report.conflicts = detect_conflicts(conn)
    return report


def detect_conflicts(conn: sqlite3.Connection,
                     cad_number: Optional[str] = None) -> list[dict]:
    """Найти объекты, где живой ручной контур встретился с контуром выписки.

    Функция не решает конфликт и не трогает геометрию — она только заводит
    строку в журнале. Возвращает описания НОВЫХ конфликтов; уже открытые
    повторно не заводятся (`ux_contour_conflict_open`).
    """
    _geo_db.ensure_schema(conn)
    rows = conn.execute(
        """SELECT m.manual_id, m.cad_number, m.area_computed_sqm,
                  e.contour_id, e.area_computed_sqm, e.source_extract_number
             FROM manual_contour m
             JOIN egrn_contour e
               ON e.cad_number = m.cad_number AND e.kind = 'parcel'
                  AND e.contour_no = 1
            WHERE m.retired_at IS NULL
              AND (? IS NULL OR m.cad_number = ?)
              AND NOT EXISTS (SELECT 1 FROM contour_conflict c
                               WHERE c.cad_number = m.cad_number
                                 AND c.resolution != 'pending')
              AND NOT EXISTS (SELECT 1 FROM contour_conflict c
                               WHERE c.cad_number = m.cad_number
                                 AND c.resolution = 'pending')""",
        (cad_number, cad_number)).fetchall()

    fresh: list[dict] = []
    for manual_id, cad, manual_area, egrn_id, egrn_area, extract in rows:
        conn.execute(
            "INSERT INTO contour_conflict (cad_number, manual_id, egrn_contour_id, "
            "  manual_area_sqm, egrn_area_sqm, source_extract_number) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cad, manual_id, egrn_id, manual_area, egrn_area, extract))
        fresh.append({
            "cad_number": cad,
            "manual_area_sqm": manual_area,
            "egrn_area_sqm": egrn_area,
            "delta_sqm": (egrn_area or 0) - (manual_area or 0),
            "source_extract_number": extract,
            "message": _conflict_message(cad, manual_area, egrn_area, extract),
        })
    conn.commit()
    return fresh


def _conflict_message(cad: str, manual_area: Optional[float],
                      egrn_area: Optional[float],
                      extract: Optional[str]) -> str:
    """Текст, который человек увидит в консоли и в окне.

    Он обязан назвать три вещи: что произошло, на сколько расходятся площади и
    какие есть варианты. Сообщение без вариантов заставляет угадывать, что
    делать дальше.
    """
    manual = f"{manual_area:.0f}" if manual_area else "?"
    egrn = f"{egrn_area:.0f}" if egrn_area else "?"
    delta = ""
    if manual_area and egrn_area:
        delta = f" (расхождение {egrn_area - manual_area:+.0f} кв.м)"
    return (f"{cad}: в выписке {extract or 'ЕГРН'} появился уточнённый контур. "
            f"Ручная обводка — {manual} кв.м, контур из выписки — {egrn} кв.м"
            f"{delta}. Оставить исходный или заменить на уточнённый?")


def resolve_conflict(conn: sqlite3.Connection, cad_number: str, choice: str, *,
                     resolved_by: Optional[str] = None,
                     note: Optional[str] = None) -> dict:
    """Решить конфликт: `use_egrn` (заменить) или `keep_manual` (оставить).

    При `use_egrn` ручной контур уходит в retired — но не удаляется: на него
    мог ссылаться уже подписанный акт. При `keep_manual` контур из выписки
    остаётся в §8 нетронутым (слепок ЕГРН не правится решением человека),
    просто текущим считается ручной.
    """
    if choice not in ("use_egrn", "keep_manual"):
        raise ValueError(
            f"choice={choice!r}: допустимо 'use_egrn' (заменить на уточнённый) "
            "или 'keep_manual' (оставить исходный)")

    # База может быть ещё пустой: человек вызвал решение раньше, чем что-либо
    # загрузил. Это не ошибка схемы, а отсутствие конфликта — ответ ниже.
    _geo_db.ensure_schema(conn)
    row = conn.execute(
        "SELECT conflict_id, manual_id FROM contour_conflict "
        " WHERE cad_number = ? AND resolution = 'pending'", (cad_number,)).fetchone()
    if row is None:
        return {"cad_number": cad_number, "resolved": False,
                "reason": "открытого конфликта по этому объекту нет"}

    conflict_id, manual_id = row
    conn.execute(
        "UPDATE contour_conflict SET resolution = ?, resolved_at = datetime('now'), "
        "       resolved_by = ?, resolution_note = ? WHERE conflict_id = ?",
        (choice, resolved_by, note, conflict_id))
    if choice == "use_egrn" and manual_id is not None:
        conn.execute(
            "UPDATE manual_contour SET retired_at = datetime('now'), "
            "       retired_reason = 'заменён контуром из выписки ЕГРН' "
            " WHERE manual_id = ?", (manual_id,))
    conn.commit()
    return {"cad_number": cad_number, "resolved": True, "choice": choice,
            "conflict_id": conflict_id}


def open_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Конфликты, ждущие решения человека."""
    _geo_db.ensure_schema(conn)
    columns = ("conflict_id", "cad_number", "manual_area_sqm", "egrn_area_sqm",
               "delta_sqm", "detected_at", "source_extract_number", "author",
               "note", "confidence", "manual_source")
    rows = conn.execute("SELECT " + ", ".join(columns) +
                        " FROM v_contour_conflicts_open").fetchall()
    result = []
    for raw in rows:
        item = dict(zip(columns, raw))
        item["message"] = _conflict_message(
            item["cad_number"], item["manual_area_sqm"], item["egrn_area_sqm"],
            item["source_extract_number"])
        result.append(item)
    return result


def current_contours(conn: sqlite3.Connection,
                     cad_number: Optional[str] = None) -> list[dict]:
    """Какой контур считается текущим по каждому объекту (§9.4)."""
    _geo_db.ensure_schema(conn)
    # `manual_source` (миграция 0008) говорит, ЧЕМ снят неегрэновский контур:
    # обводка по спутнику и контур с кадастровой карты НСПД различаются
    # точностью на два порядка, и в отчёте это разные строки.
    columns = ("cad_number", "contour_source", "manual_source", "contour_no",
               "geom_geojson", "area_computed_sqm", "accuracy_m", "confidence",
               "land_layout", "source_extract_number", "extract_date")
    sql = ("SELECT " + ", ".join(columns) + " FROM v_object_contour_current"
           + (" WHERE cad_number = ?" if cad_number else "")
           + " ORDER BY cad_number, contour_no")
    rows = conn.execute(sql, (cad_number,) if cad_number else ()).fetchall()
    return [dict(zip(columns, raw)) for raw in rows]
