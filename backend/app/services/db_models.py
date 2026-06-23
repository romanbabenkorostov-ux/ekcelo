"""AUTO-GENERATED Pydantic models for C2 DB-contract interchange tables.

ВНИМАНИЕ: НЕ редактируйте вручную. Регенерация:

    python -m backend.app.services.db_codegen --output backend/app/services/db_models.py

Источник: contracts/bundle-db-slice/schema.json
Sha256 контракта (на момент генерации): bf71efea24ac138c492d2b9a1e10d9adce783d349e0a3e7a69795e4b41a5d57a

Каждая модель соответствует одной таблице sidecar-схемы Bundle. Используйте
для типизированного чтения sqlite-row'ов:

    from backend.app.services.db_models import ObjectsRow
    row = conn.execute("SELECT * FROM objects WHERE cad_number=?", (cad,)).fetchone()
    obj = ObjectsRow.model_validate(dict(row))

См. `obsidian/Architecture/p0-db-contract.md` (P0.1.3).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


CONTRACT_SHA256 = 'bf71efea24ac138c492d2b9a1e10d9adce783d349e0a3e7a69795e4b41a5d57a'

class AssetGeoLinkRow(BaseModel):
    """Row из таблицы `asset_geo_link` (§7, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    link_id: int
    asset_type: str
    asset_id: str
    geo_uuid: str
    role: str
    valid_from: str
    valid_to: str | None = None
    recorded_at: str
    source: str


class EntityRegistryRow(BaseModel):
    """Row из таблицы `entity_registry` (§2, restorable=True)."""
    model_config = ConfigDict(extra='allow')

    inn: str
    name_full: str
    name_short: str | None = None
    ogrn: str | None = None
    entity_type: str | None = None
    updated_at: str | None = None


class ExtractsRow(BaseModel):
    """Row из таблицы `extracts` (§4, restorable=True)."""
    model_config = ConfigDict(extra='allow')

    id: int
    extract_number: str | None = None
    cad_number: str
    extract_date: str
    document_type: str | None = None
    raw_json: str | None = None
    parsed_at: str | None = None
    parser_version: str | None = None


class GeoEntityRow(BaseModel):
    """Row из таблицы `geo_entity` (§7, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    geo_uuid: str
    name: str
    created_at: str
    source: str
    confidence: float


class GeoEntityContourRow(BaseModel):
    """Row из таблицы `geo_entity_contour` (§7, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    contour_id: int
    geo_uuid: str
    geometry: str
    valid_from: str
    valid_to: str | None = None
    recorded_at: str
    source: str
    confidence: float


class GeoEntityPointRow(BaseModel):
    """Row из таблицы `geo_entity_point` (§7, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    point_id: int
    geo_uuid: str
    lat: float
    lon: float
    valid_from: str
    valid_to: str | None = None
    recorded_at: str
    source: str
    confidence: float


class LotItemsRow(BaseModel):
    """Row из таблицы `lot_items` (§6, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    lot_id: str
    cad_number: str
    role: str
    ord: int


class LotsRow(BaseModel):
    """Row из таблицы `lots` (§6, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    lot_id: str
    name: str
    platform_targets: str | None = None
    procedure_type: str | None = None
    deal_type: str | None = None
    primary_cad_number: str | None = None
    notes_md: str | None = None
    created_at: str | None = None


class ObjectEtpProfileRow(BaseModel):
    """Row из таблицы `object_etp_profile` (§6, restorable=False)."""
    model_config = ConfigDict(extra='allow')

    cad_number: str
    location_extra: str | None = None
    building_extra: str | None = None
    layout: str | None = None
    legal_extra: str | None = None
    risks: str | None = None
    extras: str | None = None
    source: str
    confidence: float
    updated_at: str | None = None


class ObjectRestrictionsRow(BaseModel):
    """Row из таблицы `object_restrictions` (§5, restorable=True)."""
    model_config = ConfigDict(extra='allow')

    id: int
    cad_number: str
    restrict_type: str | None = None
    description: str | None = None
    registry_number: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    basis_doc: str | None = None
    updated_at: str | None = None


class ObjectsRow(BaseModel):
    """Row из таблицы `objects` (§1, restorable=True)."""
    model_config = ConfigDict(extra='allow')

    cad_number: str
    object_type: str
    address: str | None = None
    area: float | None = None
    category: str | None = None
    permitted_use: str | None = None
    purpose: str | None = None
    floors: int | None = None
    updated_at: str | None = None


class RightsRow(BaseModel):
    """Row из таблицы `rights` (§3, restorable=True)."""
    model_config = ConfigDict(extra='allow')

    id: int
    cad_number: str
    right_type: str
    right_holder_inn: str | None = None
    share_numerator: int | None = None
    share_denominator: int | None = None
    registration_number: str | None = None
    registration_date: str | None = None
    source_extract_id: int | None = None
    updated_at: str | None = None


TABLE_TO_MODEL: dict[str, type[BaseModel]] = {
    'asset_geo_link': AssetGeoLinkRow,
    'entity_registry': EntityRegistryRow,
    'extracts': ExtractsRow,
    'geo_entity': GeoEntityRow,
    'geo_entity_contour': GeoEntityContourRow,
    'geo_entity_point': GeoEntityPointRow,
    'lot_items': LotItemsRow,
    'lots': LotsRow,
    'object_etp_profile': ObjectEtpProfileRow,
    'object_restrictions': ObjectRestrictionsRow,
    'objects': ObjectsRow,
    'rights': RightsRow,
}
