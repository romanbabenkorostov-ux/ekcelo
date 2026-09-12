"""
egrn_parser/utils/msk.py — пересчёт координат выписок ЕГРН из МСК в WGS-84.

ЗАЧЕМ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ. В XML-выписке контур участка лежит в местной
системе координат субъекта (тег `entity_spatial/sk_id`, напр. «МСК-26 от СК-95,
зона 1»), а KML, карта и любой просмотрщик работают в WGS-84. Между ними —
две операции: обратная проекция Гаусса-Крюгера на эллипсоиде Красовского и
7-параметрический датум-сдвиг СК-95 → WGS-84. Без них контур из выписки
нарисовать негде.

ПОЧЕМУ БЕЗ `pyproj`. Модуль сознательно не тянет бинарную зависимость: тот же
подход уже принят в `VineInvent/core/geo_precision.py`, а парсер собирается в
десктопное приложение под Windows, где лишнее C-расширение — это лишний способ
сломать сборку. Формулы ниже — стандартный ряд Снайдера; расхождение с pyproj
проверено тестом `tests/test_msk.py` и составляет < 1 мм.

ОСЕЙ ДВЕ, И ОНИ НЕ ТАМ, ГДЕ ПРИВЫЧНО. В выписке `<x>` — это СЕВЕР (northing),
`<y>` — ВОСТОК (easting). Перепутать их местами — самая дешёвая ошибка в этом
файле и самая дорогая в результате: контур уезжает за тысячу километров, но
выглядит правдоподобно. Поэтому API принимает именно `north=`/`east=` по
именам, а не безымянную пару.

ЗОНЫ ДОБАВЛЯЮТСЯ ТОЛЬКО ПОСЛЕ ПРОВЕРКИ. В реестре ниже лежат лишь те зоны,
параметры которых сверены на реальной выписке по двум независимым признакам:
(1) площадь полигона, вычисленная по формуле шнурования в метрах МСК, сходится
с `params/area/value` из той же выписки; (2) центроид после пересчёта попадает
в район, указанный в адресе. Догадка о параметрах зоны, записанная в реестр,
опаснее её отсутствия: отсутствующая зона даёт явную ошибку, а неверная —
красивый контур не в том месте. Поэтому неизвестная зона поднимает
`UnknownZoneError` с инструкцией, а не подставляет «похожие» числа.

ДВУХ ПРИЗНАКОВ МАЛО, И ЭТО ВЫЯСНИЛОСЬ ДОРОГО. Площадь инвариантна к началу
отсчёта: она сходится с выпиской при ЛЮБЫХ `x_0`, `y_0`, а «попал в район» —
проверка с допуском в десятки километров. Зона МСК-26 з1 прошла обе и всё
равно клала контур на 1.8 км южнее и 91 м западнее правды. Третий признак,
единственный обязательный для НАЧАЛ ОТСЧЁТА, — контрольные точки: контур того
же участка из независимого источника (кадастровая карта НСПД). Поэтому
параметры зоны 26 калиброваны по НСПД и сторожатся тестом с допуском 0.5 м
(ADR-010).

Ссылки: ADR-007 (obsidian/Decisions/ADR-007-msk-to-wgs84.md).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "MSKZone",
    "UnknownZoneError",
    "MSK_ZONES",
    "parse_sk_id",
    "zone_for_sk_id",
    "register_zone",
    "to_wgs84",
    "ring_to_wgs84",
    "ring_area_sqm",
]


# --- эллипсоид Красовского (СК-42/СК-95) ---------------------------------
_KRASS_A = 6378245.0
_KRASS_F = 1.0 / 298.3
_KRASS_E2 = _KRASS_F * (2.0 - _KRASS_F)

# --- WGS-84 ---------------------------------------------------------------
_WGS_A = 6378137.0
_WGS_F = 1.0 / 298.257223563
_WGS_E2 = _WGS_F * (2.0 - _WGS_F)

# Датум-сдвиг СК-95 → WGS-84, конвенция Position Vector (EPSG:9606):
# сдвиги в метрах, вращения в угловых секундах, масштаб в ppm.
# Значения — те же, что PROJ подставляет для СК-95
# (+towgs84=24.47,-130.89,-81.56,0,0,-0.13,-0.22).
_SK95_TO_WGS84 = (24.47, -130.89, -81.56, 0.0, 0.0, -0.13, -0.22)


class UnknownZoneError(LookupError):
    """Зона МСК не описана в реестре — параметры проекции неизвестны."""


@dataclass(frozen=True)
class MSKZone:
    """Параметры одной зоны местной системы координат.

    `lon_0`  — осевой меридиан, градусы.
    `x_0`    — сдвиг по востоку (false easting), метры; содержит номер зоны.
    `y_0`    — сдвиг по северу (false northing), метры; как правило огромный
               отрицательный, потому что МСК отсчитывает север от локального
               начала, а не от экватора.
    `source` — чем подтверждены параметры; пустая строка недопустима (см.
               преамбулу: непроверенная зона хуже отсутствующей).
    """

    key: str
    title: str
    lon_0: float
    x_0: float
    y_0: float
    source: str


# Ключ — результат `parse_sk_id`: «мск-<N>-з<M>».
MSK_ZONES: dict[str, MSKZone] = {
    "мск-26-з1": MSKZone(
        key="мск-26-з1",
        title="МСК-26 от СК-95, зона 1 (Ставропольский край)",
        # Осевой меридиан — паспортный для зоны 1: 41°44'56.16".
        lon_0=41 + 44 / 60 + 56.16 / 3600,
        # Начала отсчёта КАЛИБРОВАНЫ по контрольным точкам НСПД, а не взяты из
        # справочника: со справочными (1 300 000 / −4 511 057.628) контур
        # уезжал на 1.8 км к югу и 91 м к западу. Подробности — ADR-010.
        x_0=1_299_908.678,
        y_0=-4_512_891.651,
        source=(
            "калибровано 2026-09-12 по контурам НСПД (кадастровая карта "
            "Росреестра) для 26:29:130106:334, :382 и :73: каждая вершина "
            "выписки ложится на контур НСПД не дальше 0.05 м, площади по "
            "контуру 4415.6 / 1985.6 / 15120.2 м² против заявленных "
            "4416 / 1986 / 15120 м². Контрольные точки и допуск — "
            "parser/tests/test_msk_nspd.py"
        ),
    ),
}


def register_zone(zone: MSKZone) -> None:
    """Добавить зону в реестр (для зон, проверенных вне этого файла).

    `source` обязателен: строка должна говорить, на какой выписке и по какому
    признаку параметры сошлись. Пустое значение отклоняется намеренно.
    """
    if not zone.source.strip():
        raise ValueError(
            f"зона {zone.key}: пустой source — параметры зоны без подтверждения "
            "в реестр не принимаются (см. преамбулу msk.py)"
        )
    MSK_ZONES[zone.key] = zone


_SK_SYSTEM_RE = re.compile(r"МСК\s*-?\s*(\d{1,2})", re.IGNORECASE)
_SK_ZONE_RE = re.compile(r"зон[аы]\s*№?\s*(\d{1,2})", re.IGNORECASE)


def parse_sk_id(sk_id: str | None) -> str | None:
    """`sk_id` из XML → ключ реестра, либо None если строка не про МСК.

    Написание `sk_id` не нормировано и гуляет между выписками: встречались
    «МСК-26, от СК -95, зона 1» и «МСК-26 от СК-95, зона 1» — те же параметры,
    разные строки. Поэтому из строки вынимаются только два числа: номер системы
    и номер зоны.
    """
    if not sk_id:
        return None
    text = sk_id.replace(" ", " ")
    sys_m = _SK_SYSTEM_RE.search(text)
    if not sys_m:
        return None
    zone_m = _SK_ZONE_RE.search(text)
    zone_no = zone_m.group(1) if zone_m else "1"
    return f"мск-{int(sys_m.group(1))}-з{int(zone_no)}"


def zone_for_sk_id(sk_id: str | None) -> MSKZone:
    """`sk_id` → `MSKZone`; неизвестная зона — `UnknownZoneError` с инструкцией."""
    key = parse_sk_id(sk_id)
    if key is None:
        raise UnknownZoneError(
            f"не удалось определить систему координат из sk_id={sk_id!r}: "
            "ожидалась строка вида «МСК-26 от СК-95, зона 1»"
        )
    zone = MSK_ZONES.get(key)
    if zone is None:
        known = ", ".join(sorted(MSK_ZONES)) or "(реестр пуст)"
        raise UnknownZoneError(
            f"зона {key} (sk_id={sk_id!r}) не описана в MSK_ZONES. Известны: {known}. "
            "Добавить зону можно через register_zone() ПОСЛЕ сверки: площадь "
            "полигона по контуру должна сойтись с params/area/value выписки, "
            "а центроид — попасть в район из адреса."
        )
    return zone


# --- геодезия -------------------------------------------------------------

def _tm_inverse(east: float, north: float, zone: MSKZone) -> tuple[float, float]:
    """Обратная проекция Гаусса-Крюгера (k0=1) на эллипсоиде Красовского.

    На вход — координаты в метрах МСК (уже со сдвигами зоны), на выход —
    широта/долгота в градусах на эллипсоиде Красовского.
    """
    a, e2 = _KRASS_A, _KRASS_E2
    ep2 = e2 / (1.0 - e2)

    x = east - zone.x_0
    m = north - zone.y_0            # дуга меридиана от экватора, k0 = 1

    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))
    mu = m / (a * (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0))

    phi1 = (mu
            + (3.0 * e1 / 2.0 - 27.0 * e1 ** 3 / 32.0) * math.sin(2.0 * mu)
            + (21.0 * e1 ** 2 / 16.0 - 55.0 * e1 ** 4 / 32.0) * math.sin(4.0 * mu)
            + (151.0 * e1 ** 3 / 96.0) * math.sin(6.0 * mu)
            + (1097.0 * e1 ** 4 / 512.0) * math.sin(8.0 * mu))

    sin_p1, cos_p1, tan_p1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = ep2 * cos_p1 ** 2
    t1 = tan_p1 ** 2
    n1 = a / math.sqrt(1.0 - e2 * sin_p1 ** 2)
    r1 = a * (1.0 - e2) / (1.0 - e2 * sin_p1 ** 2) ** 1.5
    d = x / n1

    lat = phi1 - (n1 * tan_p1 / r1) * (
        d ** 2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 ** 2 - 9.0 * ep2) * d ** 4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 ** 2
           - 252.0 * ep2 - 3.0 * c1 ** 2) * d ** 6 / 720.0
    )
    lon = math.radians(zone.lon_0) + (
        d
        - (1.0 + 2.0 * t1 + c1) * d ** 3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 ** 2
           + 8.0 * ep2 + 24.0 * t1 ** 2) * d ** 5 / 120.0
    ) / cos_p1
    return math.degrees(lat), math.degrees(lon)


def _geodetic_to_ecef(lat_deg: float, lon_deg: float, a: float, e2: float,
                      h: float = 0.0) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return ((n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - e2) + h) * math.sin(lat))


def _ecef_to_geodetic(x: float, y: float, z: float,
                      a: float, e2: float) -> tuple[float, float]:
    """ECEF → широта/долгота (итерации Боуринга; сходится за 3-4 шага)."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - e2))
    for _ in range(8):
        n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        new_lat = math.atan2(z, p * (1.0 - e2 * n / (n + h)))
        if abs(new_lat - lat) < 1e-14:
            lat = new_lat
            break
        lat = new_lat
    return math.degrees(lat), math.degrees(lon)


def _helmert(x: float, y: float, z: float,
             params: tuple[float, ...]) -> tuple[float, float, float]:
    """7-параметрическое преобразование, конвенция Position Vector."""
    dx, dy, dz, rx_s, ry_s, rz_s, ppm = params
    rx = math.radians(rx_s / 3600.0)
    ry = math.radians(ry_s / 3600.0)
    rz = math.radians(rz_s / 3600.0)
    s = 1.0 + ppm * 1e-6
    return (dx + s * (x - rz * y + ry * z),
            dy + s * (rz * x + y - rx * z),
            dz + s * (-ry * x + rx * y + z))


def to_wgs84(*, north: float, east: float, zone: MSKZone) -> tuple[float, float]:
    """Точка МСК → (lat, lon) WGS-84.

    Аргументы только именованные — см. преамбулу про порядок осей: в выписке
    `<x>` это север, `<y>` это восток.
    """
    lat_k, lon_k = _tm_inverse(east, north, zone)
    x, y, z = _geodetic_to_ecef(lat_k, lon_k, _KRASS_A, _KRASS_E2)
    x, y, z = _helmert(x, y, z, _SK95_TO_WGS84)
    return _ecef_to_geodetic(x, y, z, _WGS_A, _WGS_E2)


def ring_to_wgs84(ring: list[tuple[float, float]], zone: MSKZone,
                  *, decimals: int = 7) -> list[tuple[float, float]]:
    """Кольцо [(north, east), ...] → [(lon, lat), ...] в порядке KML.

    Порядок пары меняется намеренно: KML пишет `lon,lat[,Z]`, и разворот
    здесь один раз надёжнее, чем в каждом месте вывода. 7 знаков — около 1 см
    на местности, то есть заведомо точнее любой выписки (там 0.1-2.5 м).
    """
    out: list[tuple[float, float]] = []
    for north, east in ring:
        lat, lon = to_wgs84(north=north, east=east, zone=zone)
        out.append((round(lon, decimals), round(lat, decimals)))
    return out


def ring_area_sqm(ring: list[tuple[float, float]]) -> float:
    """Площадь кольца [(north, east), ...] в м² по формуле шнурования.

    Считается В МЕТРАХ МСК, до всякого пересчёта: проекция здесь равноугольная,
    и площадь в ней — это площадь на местности с точностью много лучше, чем
    погрешность самой выписки. Именно это число сверяется с
    `params/area/value` и служит приёмочным признаком параметров зоны.
    """
    pts = list(ring)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    total = 0.0
    for i, (n1, e1) in enumerate(pts):
        n2, e2 = pts[(i + 1) % len(pts)]
        total += e1 * n2 - e2 * n1
    return abs(total) / 2.0
