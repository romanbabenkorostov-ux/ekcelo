"""Тесты §7 Geo entities (миграция 0003) + helper `backend.app.services.geo`.

Покрывают:
- Запись: register_geo, add_contour, add_point, link_asset.
- Bitemporal-чтение: geo_for_asset с as_of, выбор актуальной версии контура/
  точки, фильтр по role, M:N (несколько geo у одного актива).
- DB-инварианты: CHECK lat/lon range, CHECK valid_to > valid_from, UNIQUE
  на (asset_type, asset_id, geo_uuid, role, valid_from), FK CASCADE для
  contour/point, RESTRICT для asset_geo_link.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from backend.app.services.geo import (
    GeoSnapshot,
    add_contour,
    add_point,
    geo_for_asset,
    link_asset,
    primary_geo_for_asset,
    register_geo,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_0003 = REPO_ROOT / "schema" / "migrations" / "0003_geo_entities.sql"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(tmp_path / "geo.sqlite")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(MIGRATION_0003.read_text(encoding="utf-8"))
    yield c
    c.close()


# Простейший полигон-треугольник в Тамани.
POLY_TAMAN = {
    "type": "Polygon",
    "coordinates": [[[37.7, 45.0], [37.8, 45.0], [37.75, 45.05], [37.7, 45.0]]],
}
POLY_TAMAN_2 = {
    "type": "Polygon",
    "coordinates": [[[37.7, 45.0], [37.85, 45.0], [37.78, 45.1], [37.7, 45.0]]],
}


# ─────────────────────────────────────────────────────────────────────────────
#  Запись
# ─────────────────────────────────────────────────────────────────────────────

def test_register_geo_returns_uuid(conn):
    uid = register_geo(conn, "Поле №3")
    assert isinstance(uid, str) and len(uid) == 36
    row = conn.execute("SELECT name FROM geo_entity WHERE geo_uuid=?", (uid,)).fetchone()
    assert row[0] == "Поле №3"


def test_register_geo_custom_uuid(conn):
    uid = register_geo(conn, "x", geo_uuid="my-id")
    assert uid == "my-id"


def test_add_contour_and_point(conn):
    uid = register_geo(conn, "Поле №3", source="kmz")
    cid = add_contour(conn, uid, POLY_TAMAN, "2024-01-01", source="kmz")
    pid = add_point(conn, uid, 45.02, 37.75, "2024-01-01", source="kmz")
    assert cid > 0 and pid > 0


def test_link_asset_rejects_unknown_type(conn):
    uid = register_geo(conn, "x")
    with pytest.raises(ValueError):
        link_asset(conn, "alien_type", "id", uid, "2024-01-01")


# ─────────────────────────────────────────────────────────────────────────────
#  Bitemporal чтение
# ─────────────────────────────────────────────────────────────────────────────

def test_geo_for_asset_empty(conn):
    assert geo_for_asset(conn, "object", "23:15:0000000:2267") == []


def test_geo_for_asset_returns_current_contour_and_point(conn):
    uid = register_geo(conn, "Поле №3")
    add_contour(conn, uid, POLY_TAMAN, "2024-01-01")
    add_point(conn, uid, 45.02, 37.75, "2024-01-01")
    link_asset(conn, "object", "23:15:0000000:2267", uid, "2024-01-01")

    snaps = geo_for_asset(conn, "object", "23:15:0000000:2267")
    assert len(snaps) == 1
    s = snaps[0]
    assert s.geo_uuid == uid
    assert s.name == "Поле №3"
    assert s.point == (45.02, 37.75)
    assert s.contour == POLY_TAMAN


def test_bitemporal_picks_latest_valid_contour(conn):
    """Две записи контура. as_of в будущем → берётся вторая (свежее
    valid_from). as_of до второй записи → берётся первая."""
    uid = register_geo(conn, "Поле №3")
    add_contour(conn, uid, POLY_TAMAN, "2024-01-01")
    add_contour(conn, uid, POLY_TAMAN_2, "2025-06-01")
    link_asset(conn, "object", "C1", uid, "2024-01-01")

    now = geo_for_asset(conn, "object", "C1", as_of="2025-12-31")
    assert now[0].contour == POLY_TAMAN_2

    past = geo_for_asset(conn, "object", "C1", as_of="2024-06-01")
    assert past[0].contour == POLY_TAMAN


def test_as_of_before_link_returns_empty(conn):
    uid = register_geo(conn, "x")
    add_contour(conn, uid, POLY_TAMAN, "2020-01-01")
    link_asset(conn, "object", "C1", uid, "2024-01-01")
    # запрос до valid_from линка → актив ещё не привязан
    assert geo_for_asset(conn, "object", "C1", as_of="2023-12-31") == []


def test_closed_link_excluded_after_valid_to(conn):
    """Линк закрыт через valid_to. После — не отдаётся; до — отдаётся."""
    uid = register_geo(conn, "x")
    add_contour(conn, uid, POLY_TAMAN, "2024-01-01")
    link_asset(conn, "object", "C1", uid, "2024-01-01", valid_to="2025-01-01")

    assert geo_for_asset(conn, "object", "C1", as_of="2024-06-01")[0].geo_uuid == uid
    assert geo_for_asset(conn, "object", "C1", as_of="2025-06-01") == []


def test_m_n_multiple_geo_per_asset(conn):
    """Один актив привязан к двум geo с разными ролями."""
    u1 = register_geo(conn, "Основной контур")
    u2 = register_geo(conn, "Точка доступа")
    add_contour(conn, u1, POLY_TAMAN, "2024-01-01")
    add_point(conn, u2, 45.02, 37.75, "2024-01-01")
    link_asset(conn, "object", "C1", u1, "2024-01-01", role="primary")
    link_asset(conn, "object", "C1", u2, "2024-01-01", role="access_point")

    all_ = geo_for_asset(conn, "object", "C1")
    assert {s.geo_uuid for s in all_} == {u1, u2}

    only_primary = geo_for_asset(conn, "object", "C1", role="primary")
    assert [s.geo_uuid for s in only_primary] == [u1]


def test_primary_geo_for_asset_shortcut(conn):
    uid = register_geo(conn, "x")
    add_point(conn, uid, 1.0, 2.0, "2024-01-01")
    link_asset(conn, "object", "C1", uid, "2024-01-01")
    snap = primary_geo_for_asset(conn, "object", "C1")
    assert isinstance(snap, GeoSnapshot)
    assert snap.point == (1.0, 2.0)


def test_primary_geo_returns_none_when_no_link(conn):
    assert primary_geo_for_asset(conn, "object", "missing") is None


# ─────────────────────────────────────────────────────────────────────────────
#  DB-инварианты
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_lat_rejected(conn):
    uid = register_geo(conn, "x")
    with pytest.raises(sqlite3.IntegrityError):
        add_point(conn, uid, 91.0, 0.0, "2024-01-01")


def test_invalid_lon_rejected(conn):
    uid = register_geo(conn, "x")
    with pytest.raises(sqlite3.IntegrityError):
        add_point(conn, uid, 0.0, 181.0, "2024-01-01")


def test_valid_to_before_from_rejected(conn):
    uid = register_geo(conn, "x")
    with pytest.raises(sqlite3.IntegrityError):
        add_contour(conn, uid, POLY_TAMAN, "2024-06-01", valid_to="2024-01-01")


def test_unique_link_constraint(conn):
    uid = register_geo(conn, "x")
    link_asset(conn, "object", "C1", uid, "2024-01-01", role="primary")
    with pytest.raises(sqlite3.IntegrityError):
        link_asset(conn, "object", "C1", uid, "2024-01-01", role="primary")


def test_cascade_deletes_contour_and_point(conn):
    uid = register_geo(conn, "x")
    add_contour(conn, uid, POLY_TAMAN, "2024-01-01")
    add_point(conn, uid, 1.0, 2.0, "2024-01-01")
    conn.execute("DELETE FROM geo_entity WHERE geo_uuid=?", (uid,))
    assert conn.execute(
        "SELECT COUNT(*) FROM geo_entity_contour"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM geo_entity_point"
    ).fetchone()[0] == 0


def test_restrict_delete_when_asset_linked(conn):
    """ON DELETE RESTRICT в asset_geo_link: пока есть линк — нельзя удалить
    geo_entity (защита целостности)."""
    uid = register_geo(conn, "x")
    link_asset(conn, "object", "C1", uid, "2024-01-01")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM geo_entity WHERE geo_uuid=?", (uid,))


def test_geometry_stored_as_valid_json(conn):
    uid = register_geo(conn, "x")
    add_contour(conn, uid, POLY_TAMAN, "2024-01-01")
    raw = conn.execute(
        "SELECT geometry FROM geo_entity_contour WHERE geo_uuid=?", (uid,)
    ).fetchone()[0]
    parsed = json.loads(raw)
    assert parsed["type"] == "Polygon"
    assert len(parsed["coordinates"][0]) == 4
