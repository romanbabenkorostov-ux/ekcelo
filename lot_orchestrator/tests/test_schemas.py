"""Pydantic-схемы SSOT."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from lot_orchestrator.schemas import (
    AssetData,
    Conflict,
    DocumentDate,
    Fact,
    Provenance,
    TargetScenario,
)


def test_lot_id_format_strict():
    with pytest.raises(ValidationError):
        AssetData(lot_id="bad id with spaces", generated_at=datetime.now(timezone.utc))


def test_lot_id_accepts_colon_and_dash():
    AssetData(lot_id="lot:pirushin-001", generated_at=datetime.now(timezone.utc))


def test_target_scenario_is_complete():
    assert not TargetScenario().is_complete()
    assert not TargetScenario(was="a", trigger="b").is_complete()
    assert TargetScenario(was="a", trigger="b", to_plan="c").is_complete()
    assert not TargetScenario(was="   ", trigger="b", to_plan="c").is_complete()


def test_document_date_requires_at_least_one_date():
    with pytest.raises(ValidationError):
        DocumentDate(document_id="x", type="ЕГРН")
    DocumentDate(document_id="x", type="ЕГРН", registered_date="2026-01-01")
    DocumentDate(document_id="x", type="ЕГРН", document_date="2026-01-01")


def test_evidence_level_constrained():
    with pytest.raises(ValidationError):
        Provenance(document_id="d", as_of_date="2026-01-01", evidence_level=3)
    Provenance(document_id="d", as_of_date="2026-01-01", evidence_level=1)


def test_conflict_requires_min_2_competing():
    f = Fact(
        fact_path="x",
        value=1,
        provenance=Provenance(document_id="d", as_of_date="2026-01-01", evidence_level=1),
    )
    with pytest.raises(ValidationError):
        Conflict(fact_path="x", competing_facts=[f])
    Conflict(fact_path="x", competing_facts=[f, f])


def test_asset_data_from_minimal(minimal_enrich_payload):
    data = AssetData.model_validate(minimal_enrich_payload)
    assert data.lot_id == "pirushin_001"
    assert data.target_scenario.is_complete()
    assert len(data.facts_index) == 1
