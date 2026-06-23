"""Геосущности §7 — регистрация и bitemporal-lookup.

Покрывает четыре таблицы из миграции 0003:
  geo_entity            — реестр (uuid + name).
  geo_entity_contour    — история полигонов (GeoJSON).
  geo_entity_point      — история точек.
  asset_geo_link        — M:N привязка активов с историей.

Bitemporal semantics:
  valid_from/valid_to — «реальное время».
  recorded_at         — «когда узнали» (для аудита; здесь только пишется).
Запросы `current_*` / `geo_for_asset` фильтруют по valid_from ≤ as_of <
valid_to(или ∞).

API сознательно минимальное: только то, что нужно для (a) парсера-импортёра
KMZ→DB и (b) сборки ViewModel.geo бэкендом. Расширение «закрыть открытый
интервал автоматом при вставке новой записи» — добавляется при подключении
к парсер-пайплайну (см. obsidian/Database/geo-entities-7.md §«Workflow»).

См. также:
  schema/migrations/0003_geo_entities.sql (DDL)
  obsidian/Decisions/ADR-002-geo-entities.md (rationale)
"""
from __future__ import annotations

import json
import sqlite3
import uuid as _uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable


# Какие asset_type считаем валидными. Не CHECK на уровне БД — расширяемо без
# миграции (можно завести новый тип, например 'photo', не трогая schema).
ASSET_TYPES = ("object", "lot", "oks", "room", "land", "bu", "equipment")

DEFAULT_ROLE = "primary"


@dataclass(frozen=True)
class GeoSnapshot:
    """Текущая привязка активного: центр (lat,lon) и/или контур (GeoJSON)."""
    geo_uuid: str
    name: str
    point: tuple[float, float] | None  # (lat, lon)
    contour: dict[str, Any] | None     # GeoJSON Geometry


# ─────────────────────────────────────────────────────────────────────────────
#  Запись
# ─────────────────────────────────────────────────────────────────────────────

def register_geo(
    conn: sqlite3.Connection,
    name: str,
    *,
    geo_uuid: str | None = None,
    source: str = "manual",
    confidence: float = 1.0,
) -> str:
    """Создаёт geo_entity; возвращает uuid."""
    uid = geo_uuid or str(_uuid.uuid4())
    conn.execute(
        "INSERT INTO geo_entity(geo_uuid, name, source, confidence) "
        "VALUES (?,?,?,?)",
        (uid, name, source, confidence),
    )
    return uid


def add_contour(
    conn: sqlite3.Connection,
    geo_uuid: str,
    geometry: dict[str, Any],
    valid_from: str | date | datetime,
    *,
    valid_to: str | date | datetime | None = None,
    source: str = "manual",
    confidence: float = 1.0,
) -> int:
    """Добавляет запись истории контура. Не закрывает предыдущую (политика —
    при чтении берётся актуальная по valid_from)."""
    conn.execute(
        "INSERT INTO geo_entity_contour(geo_uuid, geometry, valid_from, valid_to,"
        " source, confidence) VALUES (?,?,?,?,?,?)",
        (
            geo_uuid,
            json.dumps(geometry, ensure_ascii=False),
            _iso(valid_from),
            _iso(valid_to) if valid_to else None,
            source,
            confidence,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def add_point(
    conn: sqlite3.Connection,
    geo_uuid: str,
    lat: float,
    lon: float,
    valid_from: str | date | datetime,
    *,
    valid_to: str | date | datetime | None = None,
    source: str = "manual",
    confidence: float = 1.0,
) -> int:
    conn.execute(
        "INSERT INTO geo_entity_point(geo_uuid, lat, lon, valid_from, valid_to,"
        " source, confidence) VALUES (?,?,?,?,?,?,?)",
        (
            geo_uuid,
            lat,
            lon,
            _iso(valid_from),
            _iso(valid_to) if valid_to else None,
            source,
            confidence,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def link_asset(
    conn: sqlite3.Connection,
    asset_type: str,
    asset_id: str,
    geo_uuid: str,
    valid_from: str | date | datetime,
    *,
    role: str = DEFAULT_ROLE,
    valid_to: str | date | datetime | None = None,
    source: str = "manual",
) -> int:
    """Связывает актив с гео-сущностью (M:N, история). Уникальность —
    (asset_type, asset_id, geo_uuid, role, valid_from)."""
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"unknown asset_type: {asset_type!r}")
    conn.execute(
        "INSERT INTO asset_geo_link(asset_type, asset_id, geo_uuid, role,"
        " valid_from, valid_to, source) VALUES (?,?,?,?,?,?,?)",
        (
            asset_type,
            asset_id,
            geo_uuid,
            role,
            _iso(valid_from),
            _iso(valid_to) if valid_to else None,
            source,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


# ─────────────────────────────────────────────────────────────────────────────
#  Чтение (bitemporal — фильтр по as_of, default = today)
# ─────────────────────────────────────────────────────────────────────────────

def geo_for_asset(
    conn: sqlite3.Connection,
    asset_type: str,
    asset_id: str,
    *,
    as_of: str | date | datetime | None = None,
    role: str | None = None,
) -> list[GeoSnapshot]:
    """Возвращает активные на `as_of` (default = today) привязки актива.

    Для каждой привязки тянет актуальные контур и точку (если есть).
    Несколько ролей → несколько `GeoSnapshot`. Пустой список — нет привязок.
    """
    as_of_iso = _iso(as_of or date.today())
    sql_links = (
        "SELECT geo_uuid, role FROM asset_geo_link "
        "WHERE asset_type = ? AND asset_id = ? "
        "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
    )
    params: list[Any] = [asset_type, asset_id, as_of_iso, as_of_iso]
    if role is not None:
        sql_links += " AND role = ?"
        params.append(role)

    snapshots: list[GeoSnapshot] = []
    rows = conn.execute(sql_links, params).fetchall()
    for geo_uuid, _role in rows:
        snap = _snapshot_for_geo(conn, geo_uuid, as_of_iso)
        if snap is not None:
            snapshots.append(snap)
    return snapshots


def primary_geo_for_asset(
    conn: sqlite3.Connection,
    asset_type: str,
    asset_id: str,
    *,
    as_of: str | date | datetime | None = None,
) -> GeoSnapshot | None:
    """Удобная обёртка: одна основная привязка (role='primary')."""
    snaps = geo_for_asset(conn, asset_type, asset_id, as_of=as_of, role=DEFAULT_ROLE)
    return snaps[0] if snaps else None


# ─────────────────────────────────────────────────────────────────────────────
#  Internals
# ─────────────────────────────────────────────────────────────────────────────

def _snapshot_for_geo(
    conn: sqlite3.Connection,
    geo_uuid: str,
    as_of_iso: str,
) -> GeoSnapshot | None:
    name_row = conn.execute(
        "SELECT name FROM geo_entity WHERE geo_uuid = ?", (geo_uuid,)
    ).fetchone()
    if name_row is None:
        return None
    contour = _latest_in_window(
        conn,
        "SELECT geometry FROM geo_entity_contour WHERE geo_uuid = ? "
        "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?) "
        "ORDER BY valid_from DESC LIMIT 1",
        (geo_uuid, as_of_iso, as_of_iso),
    )
    point = _latest_in_window(
        conn,
        "SELECT lat, lon FROM geo_entity_point WHERE geo_uuid = ? "
        "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?) "
        "ORDER BY valid_from DESC LIMIT 1",
        (geo_uuid, as_of_iso, as_of_iso),
    )
    return GeoSnapshot(
        geo_uuid=geo_uuid,
        name=name_row[0],
        point=(point[0], point[1]) if point else None,
        contour=json.loads(contour[0]) if contour else None,
    )


def _latest_in_window(
    conn: sqlite3.Connection, sql: str, params: Iterable[Any]
) -> tuple[Any, ...] | None:
    row = conn.execute(sql, tuple(params)).fetchone()
    return tuple(row) if row else None


def _iso(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
