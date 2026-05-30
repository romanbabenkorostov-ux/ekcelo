"""Тестовые фикстуры FastAPI-обёртки."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset_store():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


@pytest.fixture
def client():
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(settings=settings, mock_llm_text="Mock report.\n<!-- MARP_START -->\n# Slide")
    return TestClient(app)


@pytest.fixture
def populated_workspace(tmp_path):
    """Готовая Memorandum/ с минимальным enrich + market_analysis.txt (дубликат backend-фикстуры)."""
    root = tmp_path / "project"
    root.mkdir()
    memo = root / "Memorandum"
    data = memo / "_data"
    incoming = memo / "incoming"
    for d in (memo, data, incoming):
        d.mkdir()
    payload = {
        "schema_version": "1.0",
        "lot_id": "pirushin_001",
        "generated_at": datetime(2026, 5, 30, tzinfo=timezone.utc).isoformat(),
        "target_scenario": {"was": "a", "trigger": "b", "to_plan": "c"},
        "egrn": {"tables": {}},
        "graph_ref": "graph.html",
        "documents_dates": [],
        "facts_index": [],
        "conflicts": [],
        "missing_layers": [],
    }
    (data / "enrich_pirushin_001.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (incoming / "market_analysis.txt").write_text("market", encoding="utf-8")
    return root
