"""Фикстуры для тестов orchestrator'а."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def minimal_enrich_payload() -> dict:
    return {
        "schema_version": "1.0",
        "lot_id": "pirushin_001",
        "generated_at": datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "target_scenario": {
            "was": "обособленный имущественный комплекс",
            "trigger": "продажа залогового актива",
            "to_plan": "продажа единым лотом на ЭТП",
        },
        "egrn": {"tables": {"objects": [{"cad_number": "61:44:0050706:31", "area": 125.4}]}},
        "etp_profile": None,
        "graph_ref": "graph.html",
        "documents_dates": [
            {
                "document_id": "egrn_2026-01-15_pirushin",
                "type": "ЕГРН",
                "registered_date": "2026-01-15",
                "document_date": "2026-01-16",
                "covers_cad_numbers": ["61:44:0050706:31"],
            }
        ],
        "facts_index": [
            {
                "fact_path": "egrn.tables.objects[0].area",
                "value": 125.4,
                "provenance": {
                    "document_id": "egrn_2026-01-15_pirushin",
                    "as_of_date": "2026-01-15",
                    "evidence_level": 1,
                },
            }
        ],
        "conflicts": [],
        "missing_layers": [],
    }


@pytest.fixture
def populated_workspace(tmp_path, minimal_enrich_payload):
    """Готовая Memorandum/ + минимальный enrich + market_analysis.txt."""
    root = tmp_path / "project"
    root.mkdir()
    memo = root / "Memorandum"
    data = memo / "_data"
    incoming = memo / "incoming"
    for d in (memo, data, incoming):
        d.mkdir()
    (data / "enrich_pirushin_001.json").write_text(
        json.dumps(minimal_enrich_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (incoming / "market_analysis.txt").write_text(
        "Анализ рынка: офисный сегмент Ростова-на-Дону, ставка 1200 руб/м²/мес.",
        encoding="utf-8",
    )
    return root
