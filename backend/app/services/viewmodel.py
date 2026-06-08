"""ViewModel (C4) — нормализованная форма для веб-шва backend↔frontend.

Реализует SPEC_backend.md §P0.3 (sub-stage C1). Контракт —
`contracts/api/viewmodel.schema.json` + `contracts/api/openapi.yaml`.

ViewModel — единая структура, которую рендерит фронт (полный REST-рендеринг).
Производится двумя адаптерами: kmz→ViewModel (C2/parser) и api→ViewModel (этот
модуль). 4 канонические характеристики EKCELO:

    physical   — ЧТО ЭТО     (object_type, address, area, floors, ЭТП §6)
    ownership  — ЧЬЁ ЭТО     (rights, beneficiaries, граф владения)
    geo        — ГДЕ ЭТО     (center, geometry WGS84, z_meters_top)
    temporal   — КОГДА ЭТО   (extract_date, as_of_date)

Sub-stage C1 покрывает:
- ViewModel object (cad) ← objects + entity_registry + rights + extracts
  + object_etp_profile §6.
- CatalogCard list ← objects + lots (+ latest extract per object).

Sub-stages C2, C3 добавят:
- ViewModel lot (lot_id), graph endpoint, KMZ-storage + download (см.
  `obsidian/Architecture/p0-bundle-importer.md` → §«Что НЕ в этом подэтапе»).

См. также: `backend/app/services/bundle.py` (импортирует данные, которые этот
модуль читает), `parser/egrn_parser/normalize/` (источник concept для
field mapping).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic-зеркало `viewmodel.schema.json`
# ─────────────────────────────────────────────────────────────────────────────
#  Открытая схема (extra="allow") — фронт получает все поля БД без переписи
#  бэка при расширении контракта.

class Physical(BaseModel):
    model_config = ConfigDict(extra="allow")
    object_type: str | None = None
    address: str | None = None
    area_m2: float | None = None
    floors: int | None = None
    etp: dict[str, Any] | None = None


class RightItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    right_type: str
    right_holder_inn: str | None = None
    share: str | None = None
    registration_number: str | None = None
    registration_date: str | None = None


class Beneficiary(BaseModel):
    model_config = ConfigDict(extra="allow")
    inn: str
    name_full: str
    name_short: str | None = None
    entity_type: str | None = None


class OwnershipGraph(BaseModel):
    model_config = ConfigDict(extra="allow")
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class Ownership(BaseModel):
    model_config = ConfigDict(extra="allow")
    rights: list[RightItem] = Field(default_factory=list)
    beneficiaries: list[Beneficiary] = Field(default_factory=list)
    graph: OwnershipGraph | None = None


class Geo(BaseModel):
    model_config = ConfigDict(extra="allow")
    center: list[float] | None = None
    geometry: dict[str, Any] | None = None
    z_meters_top: float | None = None
    extrude: bool = False


class Temporal(BaseModel):
    model_config = ConfigDict(extra="allow")
    extract_date: str | None = None
    as_of_date: str | None = None


class Media(BaseModel):
    model_config = ConfigDict(extra="allow")
    photos: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class ViewModel(BaseModel):
    """ViewModel — соответствует `contracts/api/viewmodel.schema.json`."""
    model_config = ConfigDict(extra="allow")

    kind: Literal["object", "lot"]
    id: str
    physical: Physical
    ownership: Ownership
    geo: Geo
    temporal: Temporal
    media: Media | None = None
    members: list[str] | None = None  # для kind=lot


class CatalogCard(BaseModel):
    """Карточка каталога — соответствует `openapi.yaml::CatalogCard`."""
    model_config = ConfigDict(extra="allow")

    kind: Literal["object", "lot"]
    id: str
    title: str
    address: str | None = None
    extract_date: str | None = None
    thumb_url: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
#  Ошибки
# ─────────────────────────────────────────────────────────────────────────────

class ObjectNotFound(Exception):
    """cad_number отсутствует в `objects`."""


# ─────────────────────────────────────────────────────────────────────────────
#  Catalog
# ─────────────────────────────────────────────────────────────────────────────

def build_catalog(
    db_path: Path,
    *,
    q: str | None = None,
    kind: Literal["object", "lot"] | None = None,
) -> list[CatalogCard]:
    """Собирает плоский список карточек (objects + lots) для `/catalog`.

    - `q` — case-insensitive substring; ищет в `id`, `title`, `address`.
    - `kind` — фильтр по типу.
    - `extract_date` объекта — последняя дата из `extracts` по cad.
    - `title` для object = cad_number; для lot = `lots.name`.

    Безопасно работает на БД без §6/lots-таблиц (старый ЕГРН-слепок).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cards: list[CatalogCard] = []

        if kind != "lot":
            cards.extend(_load_object_cards(conn))

        if kind != "object" and _table_exists(conn, "lots"):
            cards.extend(_load_lot_cards(conn))

        if q:
            needle = q.casefold()
            cards = [c for c in cards if _card_matches(c, needle)]
        return cards
    finally:
        conn.close()


def _load_object_cards(conn: sqlite3.Connection) -> list[CatalogCard]:
    # extracts может отсутствовать — LEFT JOIN недоступен через optional table,
    # поэтому делаем два запроса и сшиваем.
    rows = conn.execute(
        "SELECT cad_number, address FROM objects ORDER BY cad_number"
    ).fetchall()
    extract_map = _latest_extract_map(conn)
    return [
        CatalogCard(
            kind="object",
            id=row["cad_number"],
            title=row["cad_number"],
            address=row["address"],
            extract_date=extract_map.get(row["cad_number"]),
        )
        for row in rows
    ]


def _load_lot_cards(conn: sqlite3.Connection) -> list[CatalogCard]:
    rows = conn.execute(
        "SELECT lot_id, name, primary_cad_number FROM lots ORDER BY lot_id"
    ).fetchall()
    addr_map: dict[str, str | None] = {}
    if rows:
        primary_cads = [r["primary_cad_number"] for r in rows if r["primary_cad_number"]]
        if primary_cads:
            placeholders = ",".join("?" * len(primary_cads))
            for r in conn.execute(
                f"SELECT cad_number, address FROM objects "
                f"WHERE cad_number IN ({placeholders})",
                primary_cads,
            ):
                addr_map[r["cad_number"]] = r["address"]
    return [
        CatalogCard(
            kind="lot",
            id=row["lot_id"],
            title=row["name"],
            address=addr_map.get(row["primary_cad_number"]) if row["primary_cad_number"] else None,
        )
        for row in rows
    ]


def _latest_extract_map(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "extracts"):
        return {}
    rows = conn.execute(
        "SELECT cad_number, MAX(extract_date) AS d FROM extracts "
        "GROUP BY cad_number"
    ).fetchall()
    return {r["cad_number"]: r["d"] for r in rows if r["d"]}


def _card_matches(card: CatalogCard, needle: str) -> bool:
    for value in (card.id, card.title, card.address):
        if value and needle in value.casefold():
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Object ViewModel
# ─────────────────────────────────────────────────────────────────────────────

def build_object_viewmodel(
    db_path: Path,
    cad: str,
    *,
    as_of: str | None = None,
) -> ViewModel:
    """Собирает ViewModel объекта по cad_number.

    - 4 характеристики физ/ownership/geo/temporal — обязательны.
    - `geo` для C1 stub (пока KMZ-геометрия не материализована в БД; будет в C3).
    - `as_of` (YYYY-MM-DD) — фильтр для temporal.as_of_date + ограничение
      `rights.registration_date <= as_of`; реальное снапшоттинг будет в C2/C3.
    - Подкидывает `etp` подсекцию из object_etp_profile §6 (JSON-поля).

    Raises:
        ObjectNotFound — если cad нет в `objects`.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        obj_row = conn.execute(
            "SELECT cad_number, object_type, address, area, floors "
            "FROM objects WHERE cad_number = ?",
            (cad,),
        ).fetchone()
        if obj_row is None:
            raise ObjectNotFound(cad)

        physical = Physical(
            object_type=obj_row["object_type"],
            address=obj_row["address"],
            area_m2=obj_row["area"],
            floors=obj_row["floors"],
            etp=_load_etp_block(conn, cad),
        )
        ownership = _load_ownership(conn, cad, as_of=as_of)
        geo = Geo()  # stub для C1; геометрию даёт C3
        temporal = Temporal(
            extract_date=_latest_extract_date(conn, cad),
            as_of_date=as_of,
        )
        return ViewModel(
            kind="object",
            id=cad,
            physical=physical,
            ownership=ownership,
            geo=geo,
            temporal=temporal,
        )
    finally:
        conn.close()


def _load_etp_block(conn: sqlite3.Connection, cad: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "object_etp_profile"):
        return None
    row = conn.execute(
        "SELECT location_extra, building_extra, layout, legal_extra, risks, "
        "extras, source, confidence "
        "FROM object_etp_profile WHERE cad_number = ?",
        (cad,),
    ).fetchone()
    if row is None:
        return None
    block: dict[str, Any] = {}
    for col in ("location_extra", "building_extra", "layout",
                "legal_extra", "risks", "extras"):
        block[col] = _safe_json(row[col])
    block["source"] = row["source"]
    block["confidence"] = row["confidence"]
    return block


def _safe_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _load_ownership(
    conn: sqlite3.Connection,
    cad: str,
    *,
    as_of: str | None,
) -> Ownership:
    sql = (
        "SELECT r.right_type, r.right_holder_inn, r.share_numerator, "
        "       r.share_denominator, r.registration_number, r.registration_date "
        "FROM rights r WHERE r.cad_number = ?"
    )
    params: list[Any] = [cad]
    if as_of:
        sql += " AND (r.registration_date IS NULL OR r.registration_date <= ?)"
        params.append(as_of)
    sql += " ORDER BY r.id"
    rights: list[RightItem] = []
    inns: set[str] = set()
    for r in conn.execute(sql, params):
        share = _format_share(r["share_numerator"], r["share_denominator"])
        rights.append(RightItem(
            right_type=r["right_type"],
            right_holder_inn=r["right_holder_inn"],
            share=share,
            registration_number=r["registration_number"],
            registration_date=r["registration_date"],
        ))
        if r["right_holder_inn"]:
            inns.add(r["right_holder_inn"])

    beneficiaries: list[Beneficiary] = []
    if inns:
        placeholders = ",".join("?" * len(inns))
        for b in conn.execute(
            f"SELECT inn, name_full, name_short, entity_type "
            f"FROM entity_registry WHERE inn IN ({placeholders})",
            list(inns),
        ):
            beneficiaries.append(Beneficiary(
                inn=b["inn"],
                name_full=b["name_full"],
                name_short=b["name_short"],
                entity_type=b["entity_type"],
            ))
        beneficiaries.sort(key=lambda x: x.inn)
    return Ownership(rights=rights, beneficiaries=beneficiaries, graph=None)


def _format_share(num: int | None, den: int | None) -> str | None:
    if num is None or den is None or den == 0:
        return None
    return f"{num}/{den}"


def _latest_extract_date(conn: sqlite3.Connection, cad: str) -> str | None:
    if not _table_exists(conn, "extracts"):
        return None
    row = conn.execute(
        "SELECT MAX(extract_date) AS d FROM extracts WHERE cad_number = ?",
        (cad,),
    ).fetchone()
    return row["d"] if row and row["d"] else None


# ─────────────────────────────────────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None
