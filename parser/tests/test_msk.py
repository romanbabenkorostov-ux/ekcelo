"""tests/test_msk.py — пересчёт МСК → WGS-84 (ADR-007).

Эталонные числа взяты из реальной выписки КУВИ-001/2026-120869336 на
26:29:130106:382 (Предгорный МО, Ставропольский край). Персональных данных в
тесте нет: используются только координаты контура и площадь — сведения,
открытые в ЕГРН по определению.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.utils import msk  # noqa: E402

# Контур 26:29:130106:382, (north, east) в метрах МСК-26 зона 1.
RING_382 = [
    (360527.54, 1405241.74), (360530.35, 1405277.75), (360534.47, 1405306.95),
    (360539.28, 1405334.58), (360507.81, 1405358.07), (360507.70, 1405357.60),
    (360500.42, 1405327.05), (360523.89, 1405319.72), (360517.54, 1405296.21),
    (360513.34, 1405247.79),
]
DECLARED_AREA_382 = 1986.0

# Контур 26:29:130106:334 из выписки КУВИ-001/2026-120869307.
RING_334 = [
    (360367.46, 1404834.84), (360361.89, 1404764.37), (360380.08, 1404779.94),
    (360381.38, 1404789.75), (360382.14, 1404795.64), (360392.67, 1404803.69),
    (360436.76, 1404753.20), (360464.86, 1404766.66), (360432.40, 1404820.22),
    (360411.68, 1404832.01),
]
DECLARED_AREA_334 = 4416.0


@pytest.mark.parametrize("sk_id", [
    "МСК-26, от СК -95, зона 1",      # написание из выписки :382
    "МСК-26 от СК-95, зона 1",        # написание из выписки :334
    "МСК-26 зона 1",
    "МСК - 26 от СК-95, зоны 1",
])
def test_parse_sk_id_tolerates_spelling(sk_id):
    """Написание sk_id гуляет между выписками — ключ зоны обязан не гулять."""
    assert msk.parse_sk_id(sk_id) == "мск-26-з1"


def test_parse_sk_id_rejects_garbage():
    assert msk.parse_sk_id(None) is None
    assert msk.parse_sk_id("") is None
    assert msk.parse_sk_id("Система координат не установлена") is None


def test_unknown_zone_raises_with_instruction():
    """Неизвестная зона — явная ошибка, а не «похожие» параметры молча."""
    with pytest.raises(msk.UnknownZoneError) as exc:
        msk.zone_for_sk_id("МСК-61 от СК-95, зона 2")
    text = str(exc.value)
    assert "мск-61-з2" in text
    assert "register_zone" in text


def test_register_zone_demands_evidence():
    bad = msk.MSKZone(key="мск-99-з1", title="тест", lon_0=0.0, x_0=0.0,
                      y_0=0.0, source="  ")
    with pytest.raises(ValueError):
        msk.register_zone(bad)
    assert "мск-99-з1" not in msk.MSK_ZONES


@pytest.mark.parametrize("ring,declared", [
    (RING_382, DECLARED_AREA_382),
    (RING_334, DECLARED_AREA_334),
])
def test_area_matches_extract(ring, declared):
    """Приёмочный признак параметров зоны: площадь сходится с выпиской."""
    computed = msk.ring_area_sqm(ring)
    assert abs(computed - declared) < 1.0


def test_area_ignores_closing_point():
    """Замыкающая точка в выписке есть не всегда — площадь от этого не зависит."""
    assert msk.ring_area_sqm(RING_382) == pytest.approx(
        msk.ring_area_sqm(RING_382 + [RING_382[0]]))


def test_point_lands_in_predgorny():
    """Центроид обязан попасть в район из адреса выписки, а не «куда-то в РФ».

    Эталон обновлён после калибровки начал отсчёта по НСПД (ADR-010): прежние
    43.97156 / 42.81086 были ответом со справочными `x_0`, `y_0`, то есть на
    1.8 км южнее и 20 км западнее правды. Саму калибровку сторожит
    `test_msk_nspd.py` — там контроль внешний.
    """
    zone = msk.zone_for_sk_id("МСК-26 от СК-95, зона 1")
    lat, lon = msk.to_wgs84(north=360534.40, east=1405306.46, zone=zone)
    assert lat == pytest.approx(43.98805, abs=1e-4)
    assert lon == pytest.approx(43.06129, abs=1e-4)


def test_axes_are_not_interchangeable():
    """Перепутанные оси должны давать заведомо другой результат, а не «почти то же».

    Тест сторожит именно ту ошибку, которую легче всего внести и труднее всего
    заметить глазами: x — север, y — восток.
    """
    zone = msk.zone_for_sk_id("МСК-26 от СК-95, зона 1")
    right = msk.to_wgs84(north=360534.40, east=1405306.46, zone=zone)
    wrong = msk.to_wgs84(north=1405306.46, east=360534.40, zone=zone)
    assert abs(right[0] - wrong[0]) > 1.0


def test_ring_to_wgs84_returns_lon_lat_order():
    """KML пишет lon,lat — разворот пары делается один раз, здесь."""
    zone = msk.zone_for_sk_id("МСК-26 от СК-95, зона 1")
    pts = msk.ring_to_wgs84(RING_382, zone)
    assert len(pts) == len(RING_382)
    for lon, lat in pts:
        assert 43.0 < lon < 43.1
        assert 43.9 < lat < 44.1


def test_ring_shape_survives_projection():
    """Пересчёт не должен деформировать фигуру: площадь на сфере ≈ площадь в МСК.

    Считается по проекции Гаусса-Крюгера в обратную сторону (локальная
    равнопромежуточная развёртка вокруг центроида) — грубо, но достаточно,
    чтобы поймать масштабную ошибку в датум-сдвиге.
    """
    zone = msk.zone_for_sk_id("МСК-26 от СК-95, зона 1")
    pts = msk.ring_to_wgs84(RING_382, zone)
    lat0 = sum(p[1] for p in pts) / len(pts)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
    local = [((lat - lat0) * m_per_deg_lat, lon * m_per_deg_lon) for lon, lat in pts]
    assert msk.ring_area_sqm(local) == pytest.approx(DECLARED_AREA_382, rel=0.01)


def test_matches_pyproj_if_available():
    """Сверка с эталоном. pyproj в зависимостях нет — тест необязательный."""
    pyproj = pytest.importorskip("pyproj")
    zone = msk.MSK_ZONES["мск-26-з1"]
    proj4 = (f"+proj=tmerc +lat_0=0 +lon_0={zone.lon_0} +k=1 +x_0={zone.x_0} "
             f"+y_0={zone.y_0} +ellps=krass "
             "+towgs84=24.47,-130.89,-81.56,0,0,-0.13,-0.22 +units=m +no_defs")
    transformer = pyproj.Transformer.from_crs(
        pyproj.CRS.from_proj4(proj4), pyproj.CRS.from_epsg(4326), always_xy=True)
    for north, east in RING_382:
        lat, lon = msk.to_wgs84(north=north, east=east, zone=zone)
        ref_lon, ref_lat = transformer.transform(east, north)
        assert abs(lat - ref_lat) * 111320.0 < 0.01   # < 1 см
        assert abs(lon - ref_lon) * 111320.0 < 0.01
