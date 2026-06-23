"""Wire-up §7 (geo entities) → ViewModel.geo.

Покрывает поведение `_load_geo_from_section7`:
- пустой Geo, если §7 не подключён (миграция 0003 не применена);
- пустой Geo, если §7 есть, но активу нет привязки;
- наполненный Geo с center=[lon,lat] и geometry=GeoJSON, когда §7 заполнен;
- bitemporal: `as_of` пробрасывается, до даты привязки — Geo пустой;
- то же для kind=lot.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.app.services.geo import (
    add_contour, add_point, link_asset, register_geo,
)
from backend.app.services.viewmodel import (
    build_lot_viewmodel,
    build_object_viewmodel,
)
from backend.tests.test_viewmodel import _make_db


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_0003 = REPO_ROOT / "schema" / "migrations" / "0003_geo_entities.sql"


# Из фикстуры _make_db
TEST_CAD = "61:44:0050706:31"
TEST_LOT_ID = "lot-001"


def _apply_section7(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATION_0003.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def _populate_geo(path: Path, asset_type: str, asset_id: str, *,
                  valid_from: str = "2026-06-01") -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    uid = register_geo(conn, "Поле Шардоне 2023", source="kmz")
    poly = {"type": "Polygon",
            "coordinates": [[[37.7, 45.0], [37.8, 45.0], [37.75, 45.05], [37.7, 45.0]]]}
    add_contour(conn, uid, poly, valid_from, source="kmz")
    add_point(conn, uid, 45.02, 37.75, valid_from, source="kmz")
    link_asset(conn, asset_type, asset_id, uid, valid_from, role="primary", source="kmz")
    conn.commit()
    conn.close()


@pytest.fixture
def db_no_section7(tmp_path: Path) -> Path:
    p = tmp_path / "no7.sqlite"
    _make_db(p)
    return p


@pytest.fixture
def db_with_section7_empty(tmp_path: Path) -> Path:
    p = tmp_path / "empty7.sqlite"
    _make_db(p)
    _apply_section7(p)
    return p


@pytest.fixture
def db_with_section7_filled(tmp_path: Path) -> Path:
    p = tmp_path / "full7.sqlite"
    _make_db(p)
    _apply_section7(p)
    _populate_geo(p, "object", TEST_CAD, valid_from="2026-06-01")
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  Object ViewModel
# ─────────────────────────────────────────────────────────────────────────────

def test_geo_empty_when_section7_missing(db_no_section7: Path):
    vm = build_object_viewmodel(db_no_section7, TEST_CAD)
    assert vm.geo.center is None
    assert vm.geo.geometry is None


def test_geo_empty_when_section7_empty(db_with_section7_empty: Path):
    vm = build_object_viewmodel(db_with_section7_empty, TEST_CAD)
    assert vm.geo.center is None
    assert vm.geo.geometry is None


def test_geo_filled_from_section7(db_with_section7_filled: Path):
    vm = build_object_viewmodel(db_with_section7_filled, TEST_CAD)
    # center конвенция проекта = [lon, lat]
    assert vm.geo.center == [37.75, 45.02]
    assert vm.geo.geometry == {
        "type": "Polygon",
        "coordinates": [[[37.7, 45.0], [37.8, 45.0], [37.75, 45.05], [37.7, 45.0]]],
    }


def test_geo_bitemporal_as_of_before_valid_from(db_with_section7_filled: Path):
    vm = build_object_viewmodel(db_with_section7_filled,
                                TEST_CAD, as_of="2026-05-01")
    assert vm.geo.center is None
    assert vm.geo.geometry is None


def test_geo_bitemporal_as_of_after_valid_from(db_with_section7_filled: Path):
    vm = build_object_viewmodel(db_with_section7_filled,
                                TEST_CAD, as_of="2026-12-31")
    assert vm.geo.center == [37.75, 45.02]


# ─────────────────────────────────────────────────────────────────────────────
#  Lot ViewModel
# ─────────────────────────────────────────────────────────────────────────────

def test_lot_geo_filled_from_section7(tmp_path: Path):
    """Lot тоже получает geo из §7 (asset_type='lot')."""
    p = tmp_path / "lot.sqlite"
    _make_db(p)
    _apply_section7(p)
    _populate_geo(p, "lot", TEST_LOT_ID, valid_from="2026-06-01")

    vm = build_lot_viewmodel(p, TEST_LOT_ID)
    assert vm.geo.center == [37.75, 45.02]
    assert vm.geo.geometry is not None
    assert vm.geo.geometry["type"] == "Polygon"
