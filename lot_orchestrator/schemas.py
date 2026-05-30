"""Pydantic-схемы SSOT `enrich_<lot_id>.json` (orchestrator_spec.md §6).

Контракт совместим с `obsidian/Prompts/llm_memorandum_pipeline/templates/enrich.json.tpl`.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_LOT_ID_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
EVIDENCE_LEVELS = (1, 2)


class TargetScenario(BaseModel):
    was: str = ""
    trigger: str = ""
    to_plan: str = ""

    def is_complete(self) -> bool:
        return bool(self.was.strip() and self.trigger.strip() and self.to_plan.strip())


class Provenance(BaseModel):
    document_id: str
    as_of_date: date
    evidence_level: Literal[1, 2]


class Fact(BaseModel):
    fact_path: str
    value: Any
    provenance: Provenance


class Entity(BaseModel):
    inn: str
    name: str | None = None
    ogrn: str | None = None


class DocumentDate(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    type: Literal["ЕГРН", "ЕГРЮЛ", "ЕГРИП"]
    registered_date: date | None = None
    document_date: date | None = None
    covers_cad_numbers: list[str] = Field(default_factory=list)
    covers_entities: list[Entity] | None = None

    @model_validator(mode="after")
    def _at_least_one_date(self) -> "DocumentDate":
        if self.registered_date is None and self.document_date is None:
            raise ValueError(
                f"DocumentDate {self.document_id}: хотя бы одно из "
                f"registered_date/document_date обязательно"
            )
        return self


class Conflict(BaseModel):
    fact_path: str
    competing_facts: list[Fact] = Field(..., min_length=2)
    resolution: Literal["newer_wins", "registered_wins", "unresolved"] = "unresolved"
    winning_fact_index: int | None = None


class EgrnLayer(BaseModel):
    model_config = ConfigDict(extra="allow")

    tables: dict[str, Any] = Field(default_factory=dict)


class EtpProfile(BaseModel):
    """Минимальный контракт по фикстуре `parser/tests/fixtures/etp/object_etp_profile_sample.json`.

    Точные поля сверяются с фикстурой на момент использования (orchestrator_spec.md §6).
    """

    model_config = ConfigDict(extra="allow")

    object_etp_profile: list[dict[str, Any]] = Field(default_factory=list)


_MISSING_LAYER_VALUES = Literal["gpzu_minkult", "field_inspection", "photo_album"]


class AssetData(BaseModel):
    """Корневой SSOT-объект `enrich_<lot_id>.json`."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["1.0"] = "1.0"
    lot_id: str
    generated_at: datetime
    target_scenario: TargetScenario = Field(default_factory=TargetScenario)
    egrn: EgrnLayer = Field(default_factory=EgrnLayer)
    etp_profile: EtpProfile | None = None
    graph_ref: str | None = None
    gpzu_minkult: dict[str, Any] | None = None
    field_inspection: dict[str, Any] | None = None
    photo_album: dict[str, Any] | None = None
    documents_dates: list[DocumentDate] = Field(default_factory=list)
    facts_index: list[Fact] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    missing_layers: list[_MISSING_LAYER_VALUES] = Field(default_factory=list)

    @field_validator("lot_id")
    @classmethod
    def _lot_id_format(cls, v: str) -> str:
        if not _LOT_ID_RE.fullmatch(v):
            raise ValueError(f"lot_id '{v}' не соответствует regex {_LOT_ID_RE.pattern}")
        return v
