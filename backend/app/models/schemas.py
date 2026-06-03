"""Pydantic-схемы SSOT (re-export `lot_orchestrator.schemas`).

В шаблоне fastapi/full-stack-fastapi-template схемы живут в
`app/models/{entity}.py` (SQLModel) и `app/schemas/{entity}.py`
(Pydantic in/out). У нас единая Pydantic-only схема (без ORM-моделей);
DB-слой sqlite3 + JSON-колонки. См. ADR-001 + ADR-003 (тема 4 deferred).
"""
from __future__ import annotations

from lot_orchestrator.schemas import (
    AssetData,
    Conflict,
    DocumentDate,
    EgrnLayer,
    Entity,
    EtpProfile,
    Fact,
    Provenance,
    TargetScenario,
)


__all__ = [
    "AssetData",
    "Conflict",
    "DocumentDate",
    "EgrnLayer",
    "Entity",
    "EtpProfile",
    "Fact",
    "Provenance",
    "TargetScenario",
]
