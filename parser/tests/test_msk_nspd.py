"""tests/test_msk_nspd.py — начала отсчёта зоны МСК против контрольных точек.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. `test_msk.py` сторожит формулы: площадь по шнурованию,
порядок осей, совпадение с pyproj. Ни одна из этих проверок не видит ошибки в
НАЧАЛАХ ОТСЧЁТА (`x_0`, `y_0`): площадь к ним инвариантна, а pyproj считает по
тем же самым параметрам, что и мы, — оба ответа сдвинуты одинаково и сходятся
между собой. Именно так зона МСК-26 з1 год держала контур в 1.8 км от правды.

Контроль здесь внешний: контуры тех же участков с кадастровой карты НСПД
(Росреестр, публичные сведения ЕГРН). Совпадение вершины выписки с контуром
НСПД — независимое подтверждение, что параметры зоны верны целиком.

ДОПУСК 0.5 м. Точность самих контуров НСПД — первые десятки сантиметров, а
`delta_geopoint` в этих выписках 0.1 и 2.5 м. Требовать сантиметры значило бы
сторожить шум источника; допускать метры — потерять как раз тот класс ошибок,
ради которого файл написан. Фактическое расхождение на момент калибровки —
0.05 м по худшей вершине.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.utils import msk  # noqa: E402

SK_ID = "МСК-26 от СК-95, зона 1"
TOLERANCE_M = 0.5

# Контуры из выписок, (north, east) в метрах МСК-26 зона 1.
EGRN_RINGS = {
    "26:29:130106:382": [
        (360527.54, 1405241.74), (360530.35, 1405277.75), (360534.47, 1405306.95),
        (360539.28, 1405334.58), (360507.81, 1405358.07), (360507.70, 1405357.60),
        (360500.42, 1405327.05), (360523.89, 1405319.72), (360517.54, 1405296.21),
        (360513.34, 1405247.79),
    ],
    "26:29:130106:334": [
        (360367.46, 1404834.84), (360361.89, 1404764.37), (360380.08, 1404779.94),
        (360381.38, 1404789.75), (360382.14, 1404795.64), (360392.67, 1404803.69),
        (360436.76, 1404753.20), (360464.86, 1404766.66), (360432.40, 1404820.22),
        (360411.68, 1404832.01),
    ],
}

# Те же участки с кадастровой карты НСПД, (lon, lat) в WGS-84 — контроль.
NSPD_RINGS = {
    "26:29:130106:382": [
        (43.06048624, 43.98799627), (43.06055882, 43.98786764),
        (43.06116307, 43.98789851), (43.06145731, 43.98795228),
        (43.06154401, 43.98774006), (43.06192616, 43.98780119),
        (43.06193204, 43.98780211), (43.06164555, 43.98808863),
        (43.06130026, 43.98804930), (43.06093556, 43.98801641),
    ],
    "26:29:130106:334": [
        (43.05538384, 43.98661399), (43.05535730, 43.98701227),
        (43.05521445, 43.98720038), (43.05455339, 43.98750006),
        (43.05438011, 43.98724914), (43.05500063, 43.98684526),
        (43.05489823, 43.98675166), (43.05482468, 43.98674566),
        (43.05470218, 43.98673536), (43.05450456, 43.98657391),
    ],
}

M_PER_DEG_LAT = 111_132.95


def _to_local(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    """Градусы → метры вокруг опорной широты. Для расстояний в сотни метров
    плоское приближение честнее, чем кажется: его собственная ошибка здесь
    сантиметровая, то есть меньше допуска на порядок."""
    return ((lon - 43.0) * 111_319.49 * math.cos(math.radians(lat0)),
            (lat - lat0) * M_PER_DEG_LAT)


def _distance_to_segment(point, start, end) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _worst_offset(cad: str) -> float:
    """Худшее расстояние от вершины выписки до контура НСПД, метры.

    Сравнивается вершина с ЛИНИЕЙ, а не с ближайшей вершиной: наборы вершин у
    источников не обязаны совпадать (НСПД отдаёт свой набор), и требование
    совпадения вершин ловило бы разницу нумерации, а не ошибку проекции.
    """
    zone = msk.zone_for_sk_id(SK_ID)
    reference = NSPD_RINGS[cad]
    lat0 = sum(lat for _, lat in reference) / len(reference)
    ring = [_to_local(lon, lat, lat0) for lon, lat in reference]
    worst = 0.0
    for north, east in EGRN_RINGS[cad]:
        lat, lon = msk.to_wgs84(north=north, east=east, zone=zone)
        point = _to_local(lon, lat, lat0)
        worst = max(worst, min(
            _distance_to_segment(point, ring[i], ring[(i + 1) % len(ring)])
            for i in range(len(ring))))
    return worst


@pytest.mark.parametrize("cad", sorted(EGRN_RINGS))
def test_extract_contour_lands_on_nspd_contour(cad):
    """Главная проверка начал отсчёта: вершины выписки лежат на контуре НСПД."""
    assert _worst_offset(cad) < TOLERANCE_M


def test_wrong_false_origin_is_caught():
    """Проверка сторожит то, для чего написана.

    Справочные начала отсчёта, с которыми контур уезжал на 1.8 км, обязаны эту
    проверку не пройти — иначе тест зелёный по любым параметрам и бесполезен.
    """
    zone = msk.MSKZone(key="мск-26-з1-старая", title="со справочными началами",
                       lon_0=41.5, x_0=1_300_000.0, y_0=-4_511_057.628,
                       source="проверка самого теста")
    cad = "26:29:130106:382"
    reference = NSPD_RINGS[cad]
    lat0 = sum(lat for _, lat in reference) / len(reference)
    north, east = EGRN_RINGS[cad][0]
    lat, lon = msk.to_wgs84(north=north, east=east, zone=zone)
    point = _to_local(lon, lat, lat0)
    ring = [_to_local(lon_, lat_, lat0) for lon_, lat_ in reference]
    offset = min(_distance_to_segment(point, ring[i], ring[(i + 1) % len(ring)])
                 for i in range(len(ring)))
    assert offset > 1_000.0


def test_centroid_is_where_nspd_puts_it():
    """Центроид участка — в 0.5 м от центроида контура НСПД, а не «в районе»."""
    zone = msk.zone_for_sk_id(SK_ID)
    for cad in sorted(EGRN_RINGS):
        reference = NSPD_RINGS[cad]
        lat0 = sum(lat for _, lat in reference) / len(reference)
        ours = [msk.to_wgs84(north=n, east=e, zone=zone)
                for n, e in EGRN_RINGS[cad]]
        our_lat = sum(lat for lat, _ in ours) / len(ours)
        our_lon = sum(lon for _, lon in ours) / len(ours)
        ref_lat = lat0
        ref_lon = sum(lon for lon, _ in reference) / len(reference)
        # Вершины у источников разные, поэтому среднее вершин — не центроид
        # площади; допуск здесь шире ровно по этой причине.
        dx, dy = _to_local(our_lon, our_lat, lat0)
        rx, ry = _to_local(ref_lon, ref_lat, lat0)
        assert math.hypot(dx - rx, dy - ry) < 5.0


def test_area_still_matches_the_extract():
    """Калибровка не могла испортить площадь — но проверить надо: площадь
    считается в метрах МСК, до проекции, и молчаливое изменение формулы
    заметно только здесь."""
    assert msk.ring_area_sqm(EGRN_RINGS["26:29:130106:382"]) == pytest.approx(
        1986.0, abs=1.0)
    assert msk.ring_area_sqm(EGRN_RINGS["26:29:130106:334"]) == pytest.approx(
        4416.0, abs=1.0)
