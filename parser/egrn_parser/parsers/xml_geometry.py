"""
egrn_parser/parsers/xml_geometry.py — контуры объекта из XML-выписки ЕГРН.

ЧТО ЭТО ЗАКРЫВАЕТ. `xml_parser.py` разбирает выписку целиком, кроме одного:
геометрии. Ветка `contours_location` в нём не читается вовсе, таблица
`object_geometries` в БД стоит пустая, и контур участка приходится добирать из
НСПД/ПКК — то есть из чужого источника, хотя он лежит в самой выписке и
подписан ЭП. Этот модуль читает её оттуда.

ЧТО ИМЕННО ЧИТАЕТСЯ. Три разные вещи, которые в XML выглядят похоже и
смешивать их нельзя:

  1. `land_record/contours_location/contours/contour` — контуры САМОГО участка.
     Их может быть несколько (многоконтурный участок, ЕЗП); у каждого свой
     `number_pp`, а `sk_id` лежит рядом с координатами.
  2. `land_record/object_parts/object_part/contours/contour` — контуры ЧАСТЕЙ
     участка (ЧЗУ): охранная зона ЛЭП, водоохранная полоса. Это НЕ участок, у
     них своя площадь и свой смысл — они идут отдельным списком и в KML
     попадают отдельными Placemark, иначе площадь лота удваивается.
  3. Выписки на ОКС (`extract_about_property_build` и родня) геометрии не
     содержат ВООБЩЕ — ни контура, ни точки. Это нормальный случай, а не сбой
     разбора: здание привязывается к земле через
     `cad_links/land_cad_numbers`, и координаты берутся у участка. Модуль в
     таком случае возвращает пустую геометрию и заполненный `land_cad_numbers`,
     чтобы вызывающий код знал, у кого спрашивать.

ПРОВЕРКА, БЕЗ КОТОРОЙ РЕЗУЛЬТАТ НЕЛЬЗЯ ПУСКАТЬ ДАЛЬШЕ. Параметры зоны МСК
(`utils/msk.py`) — внешнее знание, и ошибка в них даёт правдоподобный контур
не в том месте. Единственный признак, который ловит такую ошибку своими
силами, — площадь: посчитанная по координатам она обязана сойтись с
`params/area/value` из той же выписки. Поэтому `area_check` считается всегда,
и решение «доверять или нет» принимает вызывающий, а не этот модуль.

Персональные данные модуль не трогает: он читает только координаты.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional
from xml.etree import ElementTree as ET

from egrn_parser.parsers import land_layout as _land_layout
from egrn_parser.utils.msk import (
    MSKZone,
    UnknownZoneError,
    ring_area_sqm,
    ring_to_wgs84,
    zone_for_sk_id,
)

log = logging.getLogger(__name__)

_CAD_RE = re.compile(r"\b\d{1,2}:\d{1,2}:\d{1,8}:\d{1,8}\b")

__all__ = [
    "Ring",
    "Contour",
    "ExtractGeometry",
    "AreaCheck",
    "extract_geometry",
    "extract_geometry_from_root",
]

# Допуск сверки площадей. Выписка округляет площадь до целых м², координаты —
# до сантиметров, поэтому точного равенства не бывает никогда. 1% ловит
# перепутанные оси и неверную зону (там расхождение в разы), но не ругается на
# округление; для мелких участков добавлен абсолютный порог в 1 м².
AREA_TOLERANCE_REL = 0.01
AREA_TOLERANCE_ABS = 1.0

# Корни выписок, у которых геометрия бывает, и имя их record-элемента.
_GEOMETRY_ROOTS = {
    "extract_about_property_land": "land_record",
}
# Корни выписок без собственной геометрии — привязка к земле через cad_links.
_LANDLESS_ROOTS = {
    "extract_about_property_build": "build_record",
    "extract_about_property_construction": "construction_record",
    "extract_about_property_ons": "ons_record",
    "extract_about_property_room": "room_record",
    "extract_about_property_parking": "parking_record",
}


@dataclass(frozen=True)
class Ring:
    """Одно замкнутое кольцо контура в метрах МСК.

    `points` — [(north, east), ...]; замыкающая точка, если она была в XML,
    сохраняется как есть: выписка её пишет, и выбрасывать чужие данные без
    нужды не следует. Замыкание для KML делает экспортёр.
    `accuracy_m` — `delta_geopoint`, погрешность положения точки по выписке
    (0.1 м у свежей съёмки, 2.5 м у пересчёта из старых материалов). Это
    честная характеристика источника, и она должна дойти до карточки объекта.
    """

    points: list[tuple[float, float]]
    accuracy_m: Optional[float] = None
    point_numbers: list[Optional[str]] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        return len(self.points) >= 4 and self.points[0] == self.points[-1]

    def area_sqm(self) -> float:
        return ring_area_sqm(self.points)


@dataclass(frozen=True)
class Contour:
    """Один контур: внешнее кольцо плюс, если есть, внутренние (дырки)."""

    rings: list[Ring]
    number_pp: Optional[str] = None
    cad_number: Optional[str] = None
    sk_id: Optional[str] = None
    kind: str = "parcel"            # 'parcel' | 'part'
    part_number: Optional[str] = None
    part_mnemonic: Optional[str] = None
    declared_area_sqm: Optional[float] = None

    @property
    def outer(self) -> Optional[Ring]:
        return self.rings[0] if self.rings else None

    def area_sqm(self) -> float:
        """Площадь с вычетом дырок."""
        if not self.rings:
            return 0.0
        return self.rings[0].area_sqm() - sum(r.area_sqm() for r in self.rings[1:])

    def to_wgs84_rings(self, zone: MSKZone) -> list[list[tuple[float, float]]]:
        """Кольца → [(lon, lat), ...] для KML/GeoJSON."""
        return [ring_to_wgs84(r.points, zone) for r in self.rings]

    def to_geojson(self, zone: MSKZone) -> dict:
        """Контур → GeoJSON Geometry (Polygon), кольца замкнуты.

        Замыкание делается здесь, а не при разборе: в выписке замыкающая точка
        бывает, а бывает нет, и GeoJSON со своей стороны требует её всегда.
        Портить исходные данные ради формата вывода не нужно.
        """
        rings: list[list[list[float]]] = []
        for ring in self.to_wgs84_rings(zone):
            pts = [[lon, lat] for lon, lat in ring]
            if pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            rings.append(pts)
        return {"type": "Polygon", "coordinates": rings}

    def centroid_wgs84(self, zone: MSKZone) -> Optional[tuple[float, float]]:
        """Центроид внешнего кольца, (lon, lat).

        Среднее вершин, а не центр масс полигона: у кадастрового контура
        вершины распределены по границе достаточно ровно, а разница между
        двумя определениями заведомо меньше заявленной погрешности съёмки
        (0.1-2.5 м). Точка нужна для подписи на карте, а не для геодезии.
        """
        outer = self.outer
        if outer is None:
            return None
        pts = self.to_wgs84_rings(zone)[0]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if not pts:
            return None
        return (round(sum(p[0] for p in pts) / len(pts), 7),
                round(sum(p[1] for p in pts) / len(pts), 7))


@dataclass(frozen=True)
class AreaCheck:
    """Сверка вычисленной площади с заявленной в выписке."""

    declared_sqm: Optional[float]
    computed_sqm: float
    inaccuracy_sqm: Optional[float] = None

    @property
    def delta_sqm(self) -> Optional[float]:
        if self.declared_sqm is None:
            return None
        return self.computed_sqm - self.declared_sqm

    @property
    def ok(self) -> bool:
        """None-заявленная площадь — не провал проверки, а её отсутствие."""
        if self.declared_sqm is None:
            return True
        delta = abs(self.computed_sqm - self.declared_sqm)
        return delta <= max(AREA_TOLERANCE_ABS, self.declared_sqm * AREA_TOLERANCE_REL)

    def describe(self) -> str:
        if self.declared_sqm is None:
            return f"площадь по контуру {self.computed_sqm:.1f} м², в выписке не заявлена"
        mark = "сходится" if self.ok else "НЕ СХОДИТСЯ"
        return (f"площадь по контуру {self.computed_sqm:.1f} м² против заявленных "
                f"{self.declared_sqm:.0f} м² ({self.delta_sqm:+.1f} м²) — {mark}")


@dataclass
class ExtractGeometry:
    """Геометрия одной выписки."""

    cad_number: Optional[str]
    object_type: str                       # 'land' | 'build' | ...
    contours: list[Contour] = field(default_factory=list)
    parts: list[Contour] = field(default_factory=list)
    sk_id: Optional[str] = None
    zone: Optional[MSKZone] = None
    zone_error: Optional[str] = None
    land_cad_numbers: list[str] = field(default_factory=list)
    declared_area_sqm: Optional[float] = None
    area_inaccuracy_sqm: Optional[float] = None
    source_file: Optional[str] = None
    # Реквизиты документа лежат в том же XML (`details_statement`), и читать их
    # здесь дешевле, чем заставлять каждого вызывающего разбирать файл второй
    # раз ради номера выписки. Без них у контура в базе нет ответа на вопрос
    # «откуда эта граница».
    extract_number: Optional[str] = None
    extract_date: Optional[str] = None

    @property
    def has_geometry(self) -> bool:
        return bool(self.contours)

    def area_check(self) -> AreaCheck:
        return AreaCheck(
            declared_sqm=self.declared_area_sqm,
            computed_sqm=sum(c.area_sqm() for c in self.contours),
            inaccuracy_sqm=self.area_inaccuracy_sqm,
        )

    @property
    def layout(self) -> str:
        """Раскладка участка: 'ЗУ' | 'МКУ' | 'ЕЗП'.

        Один кадастровый номер — не обязательно один контур, и различие не
        косметическое:

          ЗУ  — обычный участок, один контур;
          МКУ — многоконтурный: контуров несколько, все под одним КН,
                и они неотделимы друг от друга;
          ЕЗП — единое землепользование: каждый контур САМ объект учёта и несёт
                свой кадастровый номер обособленного участка, который можно
                продать отдельно.

        Признак ЕЗП здесь — собственный КН у контура (`contour_cad`), а не
        число контуров: многоконтурный ЕЗП и МКУ по числу контуров неотличимы.
        Тот же приоритет заложен в `land_layout.detect_land_layout`
        (ADR-005), и расходиться с ним нельзя — иначе два места в системе
        будут по-разному называть один и тот же участок.
        """
        children = [c.cad_number for c in self.contours
                    if c.cad_number and c.cad_number != self.cad_number]
        return _land_layout.detect_land_layout(
            cad_number=self.cad_number,
            contours_count=len(self.contours) or None,
            child_cads=children or None)

    @property
    def child_cad_numbers(self) -> list[str]:
        """КН обособленных участков ЕЗП. У ЗУ и МКУ — пустой список."""
        return [c.cad_number for c in self.contours
                if c.cad_number and c.cad_number != self.cad_number]

    def to_geojson(self) -> Optional[dict]:
        """Все контуры участка → GeoJSON MultiPolygon (без ЧЗУ).

        Части участка сюда НЕ попадают: они лежат внутри контура, и склеенные
        с ним в одну геометрию дают площадь лота с двойным учётом. Их отдаёт
        `parts` отдельно, и в KML они становятся отдельными Placemark.
        """
        if not self.contours or self.zone is None:
            return None
        polygons = [c.to_geojson(self.zone)["coordinates"] for c in self.contours]
        return {"type": "MultiPolygon", "coordinates": polygons}


# --- обход дерева ---------------------------------------------------------

def _tag(elem: ET.Element) -> str:
    t = elem.tag
    return (t.split("}", 1)[1] if "}" in t else t).lower()


def _kids(parent: Optional[ET.Element], name: str) -> Iterator[ET.Element]:
    if parent is None:
        return
    low = name.lower()
    for child in parent:
        if _tag(child) == low:
            yield child


def _kid(parent: Optional[ET.Element], *path: str) -> Optional[ET.Element]:
    cur = parent
    for name in path:
        cur = next(_kids(cur, name), None)
        if cur is None:
            return None
    return cur


def _text(parent: Optional[ET.Element], *path: str) -> Optional[str]:
    elem = _kid(parent, *path)
    if elem is None or elem.text is None:
        return None
    value = elem.text.strip()
    return value or None


def _number(parent: Optional[ET.Element], *path: str) -> Optional[float]:
    raw = _text(parent, *path)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _split_cad_numbers(raw: str | None) -> list[str]:
    """Строка `land_cad_number` → список КН.

    Росреестр кладёт в ОДИН тег несколько номеров через запятую, когда здание
    стоит на двух участках («26:29:130106:72, 26:29:130322:7»). Вернуть это
    одной строкой — значит потерять связь со вторым участком на первом же
    join'е по кадастровому номеру.
    """
    if not raw:
        return []
    return _CAD_RE.findall(raw)


def _read_rings(entity_spatial: Optional[ET.Element]) -> list[Ring]:
    """`entity_spatial` → кольца. Первый `spatial_element` — внешний, прочие — дырки.

    Порядок в XML значим и другого признака «внешнее/внутреннее» выписка не
    даёт, поэтому он и берётся за основу — так же читает контуры Росреестр в
    своих же чертежах.
    """
    rings: list[Ring] = []
    for element in _kids(_kid(entity_spatial, "spatials_elements"), "spatial_element"):
        points: list[tuple[float, float]] = []
        numbers: list[Optional[str]] = []
        accuracy: Optional[float] = None
        for ordinate in _kids(_kid(element, "ordinates"), "ordinate"):
            north = _number(ordinate, "x")
            east = _number(ordinate, "y")
            if north is None or east is None:
                continue
            points.append((north, east))
            numbers.append(_text(ordinate, "num_geopoint"))
            if accuracy is None:
                accuracy = _number(ordinate, "delta_geopoint")
        if len(points) >= 3:
            rings.append(Ring(points=points, accuracy_m=accuracy, point_numbers=numbers))
        elif points:
            log.warning("кольцо из %d точек пропущено — полигон невозможен", len(points))
    return rings


def _read_own_contours(record: ET.Element) -> tuple[list[Contour], Optional[str]]:
    """Контуры самого объекта + `sk_id`, если он указан."""
    contours: list[Contour] = []
    sk_id: Optional[str] = None
    holder = _kid(record, "contours_location", "contours")
    for contour_el in _kids(holder, "contour"):
        entity_spatial = _kid(contour_el, "entity_spatial")
        contour_sk = _text(entity_spatial, "sk_id")
        sk_id = sk_id or contour_sk
        rings = _read_rings(entity_spatial)
        if not rings:
            continue
        contours.append(Contour(
            rings=rings,
            number_pp=_text(contour_el, "number_pp"),
            cad_number=_text(contour_el, "cad_number"),
            sk_id=contour_sk,
            kind="parcel",
        ))
    return contours, sk_id


def _read_parts(record: ET.Element) -> list[Contour]:
    """Контуры частей объекта (ЧЗУ) — отдельным списком, не смешивая с участком."""
    parts: list[Contour] = []
    for part_el in _kids(_kid(record, "object_parts"), "object_part"):
        part_number = _text(part_el, "part_number")
        mnemonic = _text(part_el, "mnemonic")
        declared = _number(part_el, "area", "value")
        for contour_el in _kids(_kid(part_el, "contours"), "contour"):
            entity_spatial = _kid(contour_el, "entity_spatial")
            rings = _read_rings(entity_spatial)
            if not rings:
                continue
            parts.append(Contour(
                rings=rings,
                number_pp=_text(contour_el, "number_pp"),
                sk_id=_text(entity_spatial, "sk_id"),
                kind="part",
                part_number=part_number,
                part_mnemonic=mnemonic,
                declared_area_sqm=_number(contour_el, "area", "value") or declared,
            ))
    return parts


def extract_geometry_from_root(root: ET.Element,
                               *, source_file: str | None = None) -> ExtractGeometry:
    """Разобрать уже прочитанное дерево выписки."""
    root_tag = _tag(root)
    requisites = _kid(root, "details_statement", "group_top_requisites")
    extract_number = _text(requisites, "registration_number")
    extract_date = _text(requisites, "date_formation")

    record_name = _GEOMETRY_ROOTS.get(root_tag)
    if record_name is None:
        record_name = _LANDLESS_ROOTS.get(root_tag)
        record = _kid(root, record_name) if record_name else None
        cad_number = _text(record, "object", "common_data", "cad_number")
        land_numbers: list[str] = []
        for el in _kids(_kid(record, "cad_links", "land_cad_numbers"), "land_cad_number"):
            land_numbers.extend(_split_cad_numbers(_text(el, "cad_number")))
        return ExtractGeometry(
            cad_number=cad_number,
            object_type=(root_tag.replace("extract_about_property_", "")
                         if root_tag.startswith("extract_about_property_") else root_tag),
            land_cad_numbers=land_numbers,
            source_file=source_file,
            extract_number=extract_number,
            extract_date=extract_date,
        )

    record = _kid(root, record_name)
    if record is None:
        return ExtractGeometry(cad_number=None, object_type="land",
                               source_file=source_file,
                               extract_number=extract_number,
                               extract_date=extract_date)

    contours, sk_id = _read_own_contours(record)
    geometry = ExtractGeometry(
        cad_number=_text(record, "object", "common_data", "cad_number"),
        object_type="land",
        contours=contours,
        parts=_read_parts(record),
        sk_id=sk_id,
        declared_area_sqm=_number(record, "params", "area", "value"),
        area_inaccuracy_sqm=_number(record, "params", "area", "inaccuracy"),
        source_file=source_file,
        extract_number=extract_number,
        extract_date=extract_date,
    )

    if contours:
        try:
            geometry.zone = zone_for_sk_id(sk_id)
        except UnknownZoneError as exc:
            # Не исключение наружу: координаты в МСК уже извлечены и полезны
            # сами по себе (площадь, сверка, ручной пересчёт). Пересчёт в
            # WGS-84 просто недоступен, и об этом сказано явным текстом.
            geometry.zone_error = str(exc)
            log.warning("%s: %s", geometry.cad_number, exc)
    return geometry


def extract_geometry(xml_path: Path | str) -> ExtractGeometry:
    """Разобрать XML-выписку с диска."""
    path = Path(xml_path)
    root = ET.parse(str(path)).getroot()
    return extract_geometry_from_root(root, source_file=path.name)
