"""main.py: missing-key error paths (coverage boost)."""
from __future__ import annotations

import json
from pathlib import Path

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


def test_run_requires_api_key_when_no_mock(tmp_path):
    """create_app без mock_llm_text и без ANTHROPIC_API_KEY → /run возвращает 400."""
    settings = Settings(anthropic_api_key="")  # no key
    app = create_app(settings=settings, mock_llm_text=None)
    client = TestClient(app)
    workspace = tmp_path / "project"
    workspace.mkdir()
    response = client.post(
        "/lots/x/run",
        json={"workspace_path": str(workspace)},
    )
    assert response.status_code == 400
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_provide_input_requires_api_key_when_no_mock(tmp_path):
    settings = Settings(anthropic_api_key="")
    app = create_app(settings=settings, mock_llm_text=None)
    client = TestClient(app)
    workspace = tmp_path / "project"
    workspace.mkdir()
    data = workspace / "Memorandum" / "_data"
    data.mkdir(parents=True)
    (workspace / "Memorandum" / "incoming").mkdir(parents=True)
    (data / "enrich_x.json").write_text(json.dumps({
        "schema_version": "1.0",
        "lot_id": "x",
        "generated_at": "2026-05-30T12:00:00+00:00",
    }), encoding="utf-8")
    response = client.post(
        "/lots/x/provide-input",
        data={
            "workspace_path": str(workspace),
            "was": "a", "trigger": "b", "to_plan": "c",
        },
    )
    assert response.status_code == 400
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_provide_input_workspace_missing(tmp_path):
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x")
    client = TestClient(app)
    response = client.post(
        "/lots/x/provide-input",
        data={
            "workspace_path": str(tmp_path / "absent"),
            "was": "a", "trigger": "b", "to_plan": "c",
        },
    )
    assert response.status_code == 400


def test_artifacts_404_when_memorandum_missing(tmp_path):
    """Если workspace есть, а Memorandum/ нет — /artifacts → 404."""
    from lot_orchestrator_web.store import get_store
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x")
    client = TestClient(app)
    # Создаём run вручную с workspace без Memorandum/.
    store = get_store()
    bare_workspace = tmp_path / "bare"
    bare_workspace.mkdir()
    store.create("nm_lot", bare_workspace)
    response = client.get("/lots/nm_lot/artifacts")
    assert response.status_code == 404
    assert "Memorandum" in response.json()["detail"]


def test_sse_emits_done_event_for_completed_run(tmp_path):
    """SSE: завершённый run → сразу event: done."""
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(settings=settings,
                     mock_llm_text="r\n<!-- MARP_START -->\n# S")
    client = TestClient(app)
    workspace = tmp_path / "p"
    workspace.mkdir()
    memo = workspace / "Memorandum"
    data = memo / "_data"
    incoming = memo / "incoming"
    for d in (memo, data, incoming):
        d.mkdir()
    (data / "enrich_done_lot.json").write_text(json.dumps({
        "schema_version": "1.0",
        "lot_id": "done_lot",
        "generated_at": "2026-05-30T12:00:00+00:00",
        "target_scenario": {"was": "a", "trigger": "b", "to_plan": "c"},
        "egrn": {"tables": {}},
        "documents_dates": [], "facts_index": [], "conflicts": [], "missing_layers": [],
    }), encoding="utf-8")
    (incoming / "market_analysis.txt").write_text("m", encoding="utf-8")

    start = client.post(
        "/lots/done_lot/run",
        json={"workspace_path": str(workspace)},
    )
    run_id = start.json()["run_id"]
    with client.stream("GET", f"/lots/done_lot/stream/{run_id}") as r:
        body = "".join(r.iter_text())
    assert "event: done" in body
