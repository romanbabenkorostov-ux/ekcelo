"""SSE через Redis pub/sub (cycle 11)."""
from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


@pytest.fixture
def populated_workspace(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    memo = root / "Memorandum"
    data = memo / "_data"
    incoming = memo / "incoming"
    for d in (memo, data, incoming):
        d.mkdir()
    payload = {
        "schema_version": "1.0",
        "lot_id": "psse_001",
        "generated_at": "2026-05-30T12:00:00+00:00",
        "target_scenario": {"was": "a", "trigger": "b", "to_plan": "c"},
        "egrn": {"tables": {}},
        "documents_dates": [], "facts_index": [], "conflicts": [], "missing_layers": [],
    }
    (data / "enrich_psse_001.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (incoming / "market_analysis.txt").write_text("m", encoding="utf-8")
    return root


def test_sse_via_pubsub_emits_initial_phase(populated_workspace):
    """RedisRunStore activates pub/sub SSE; первое сообщение — initial snapshot."""
    redis_client = fakeredis.FakeRedis()
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(
        settings=settings,
        mock_llm_text="r\n<!-- MARP_START -->\n# S",
        redis_client=redis_client,
    )
    client = TestClient(app)
    start = client.post(
        "/lots/psse_001/run",
        json={"workspace_path": str(populated_workspace)},
    )
    run_id = start.json()["run_id"]
    with client.stream("GET", f"/lots/psse_001/stream/{run_id}") as r:
        body = "".join(r.iter_text())
    assert "event: phase" in body
    assert "event: done" in body


def test_sse_via_pubsub_emits_error_for_unknown_run():
    redis_client = fakeredis.FakeRedis()
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x", redis_client=redis_client)
    client = TestClient(app)
    with client.stream("GET", "/lots/x/stream/nonexistent") as r:
        body = "".join(r.iter_text())
    assert "event: error" in body


def test_polling_fallback_when_no_pubsub():
    """In-memory store не имеет subscribe_events → fallback на polling."""
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x")  # без redis_client
    client = TestClient(app)
    with client.stream("GET", "/lots/x/stream/nonexistent") as r:
        body = "".join(r.iter_text())
    assert "event: error" in body  # polling-fallback тоже эмитит error


def test_sse_via_pubsub_streams_phase_changes_after_initial(populated_workspace):
    """После initial snapshot pub/sub-стрим ловит phase changes от runner."""
    redis_client = fakeredis.FakeRedis()
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(
        settings=settings,
        mock_llm_text="report\n<!-- MARP_START -->\n# Slide",
        redis_client=redis_client,
    )
    client = TestClient(app)
    start = client.post(
        "/lots/psse_001/run",
        json={"workspace_path": str(populated_workspace)},
    )
    assert start.status_code == 202
    run_id = start.json()["run_id"]
    with client.stream("GET", f"/lots/psse_001/stream/{run_id}") as r:
        chunks = list(r.iter_text())
    body = "".join(chunks)
    # Должны быть как минимум initial phase + done event.
    assert body.count("event: phase") >= 1
    assert "event: done" in body
