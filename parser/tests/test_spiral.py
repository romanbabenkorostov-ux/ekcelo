"""Тесты для spiral_points (KML schema 2.0, §A.7)."""
from __future__ import annotations
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pirushin_sosn_rocha_08_build_kmz_v2 import (
    spiral_points, _spiral_r_for, _spiral_phi_for,
    SPIRAL_R0_M, SPIRAL_DR_M, GOLDEN_DEG, LAT_M_PER_DEG,
)


def test_count():
    assert spiral_points(47.0, 39.0, 0) == []
    assert len(spiral_points(47.0, 39.0, 1)) == 1
    assert len(spiral_points(47.0, 39.0, 100)) == 100


def test_alt_is_zero():
    pts = spiral_points(47.0, 39.0, 10)
    assert all(p[2] == 0.0 for p in pts)


def test_deterministic():
    a = spiral_points(47.0, 39.0, 50)
    b = spiral_points(47.0, 39.0, 50)
    assert a == b


def test_distance_from_center():
    """Расстояние i-й точки от центра ≈ r0 + dr·√(i+1) метров, погрешность < 0.5 м."""
    lat0, lon0 = 47.0, 39.0
    pts = spiral_points(lat0, lon0, 15)
    m_lon = LAT_M_PER_DEG * math.cos(math.radians(lat0))
    for i, (lat, lon, _) in enumerate(pts):
        d_lat = (lat - lat0) * LAT_M_PER_DEG
        d_lon = (lon - lon0) * m_lon
        r = math.hypot(d_lat, d_lon)
        expected = SPIRAL_R0_M + SPIRAL_DR_M * math.sqrt(i + 1)
        assert abs(r - expected) < 0.5, f"i={i}: r={r:.2f}, expected={expected:.2f}"


def test_first_point_at_angle_zero():
    """i=0: φ=0° → точка строго к востоку от центра (Δlat≈0)."""
    pts = spiral_points(47.0, 39.0, 1)
    lat, lon, _ = pts[0]
    assert abs(lat - 47.0) < 1e-6, f"Δlat={lat-47.0}"
    assert lon > 39.0  # к востоку


def test_angles_no_collision():
    """На 100 точках никакие два угла не совпадают (золотой угол иррационален)."""
    pts = spiral_points(47.0, 39.0, 100)
    lat0, lon0 = 47.0, 39.0
    phis: list[float] = []
    for lat, lon, _ in pts:
        d_lat = lat - lat0
        d_lon = lon - lon0
        phis.append(math.atan2(d_lat, d_lon))
    for i in range(len(phis)):
        for j in range(i + 1, len(phis)):
            assert abs(phis[i] - phis[j]) > 1e-4, \
                f"collision at i={i}, j={j}"


def test_radii_monotonic():
    """r_i растёт монотонно с i."""
    rs = [_spiral_r_for(i) for i in range(50)]
    for i in range(1, len(rs)):
        assert rs[i] > rs[i - 1]


def test_first_eight_snapshot():
    """Эталон: первые 8 точек спирали вокруг (47.0, 39.0).
    Закрепляет, что рефакторинги не сдвигают раскладку.
    """
    pts = spiral_points(47.0, 39.0, 8)
    assert len(pts) == 8
    # i=0: φ=0°, r=29.0 м, точка к востоку
    lat, lon, _ = pts[0]
    assert abs(lat - 47.0) < 1e-6
    assert 39.0003 < lon < 39.0005
    # Все 8 точек различны
    assert len({(p[0], p[1]) for p in pts}) == 8
    # i=1: φ=137.508°, r=30.66м — точка во 2-й четверти (lat>lat0, lon<lon0)
    lat1, lon1, _ = pts[1]
    assert lat1 > 47.0
    assert lon1 < 39.0


def test_polar_safety():
    """На полюсе cos(lat)→0 — функция не должна делить на ноль."""
    pts = spiral_points(89.9999, 0.0, 5)
    assert len(pts) == 5
    # Долгота не уходит в бесконечность
    for _, lon, _ in pts:
        assert -180.0 < lon < 180.0


def test_phi_normalized():
    """_spiral_phi_for возвращает значение в [0, 360)."""
    for i in range(100):
        phi = _spiral_phi_for(i)
        assert 0.0 <= phi < 360.0
