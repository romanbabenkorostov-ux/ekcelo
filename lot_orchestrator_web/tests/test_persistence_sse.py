"""Cycle 8: SQLite persistence + SSE streaming."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.persistence import RunSnapshot, SQLitePersistence
from lot_orchestrator_web.store import RunStore, reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


# ─────────────────────────────────────────────────────────────────────────────
#  Persistence
# ─────────────────────────────────────────────────────────────────────────────

def test_persistence_save_and_load(tmp_path):
    db = tmp_path / "runs.sqlite"
    p = SQLitePersistence(db)
    snap = RunSnapshot(
        run_id="abc123",
        lot_id="lot1",
        workspace_path=str(tmp_path),
        status="complete",
        phase="done",
        warnings=["w1"],
        errors=[],
        started_at="2026-05-30T12:00:00+00:00",
        finished_at="2026-05-30T12:01:00+00:00",
    )
    p.save(snap)
    loaded = p.load_all()
    assert len(loaded) == 1
    assert loaded[0].run_id == "abc123"
    assert loaded[0].warnings == ["w1"]


def test_persistence_upsert_overwrites(tmp_path):
    db = tmp_path / "runs.sqlite"
    p = SQLitePersistence(db)
    snap = RunSnapshot("r1", "lot1", str(tmp_path), "pending", "validating",
                      [], [], "2026-05-30T12:00:00+00:00", None)
    p.save(snap)
    snap.status = "complete"
    snap.phase = "done"
    snap.finished_at = "2026-05-30T12:05:00+00:00"
    p.save(snap)
    loaded = p.load_all()
    assert len(loaded) == 1
    assert loaded[0].status == "complete"
    assert loaded[0].finished_at == "2026-05-30T12:05:00+00:00"


def test_store_persists_run_on_create_and_update(tmp_path):
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    store = RunStore(persistence=p)
    run = store.create("lot1", tmp_path)
    assert len(p.load_all()) == 1

    store.update(run.run_id, status="complete")
    snaps = p.load_all()
    assert snaps[0].status == "complete"
    assert snaps[0].finished_at is not None


def test_store_loads_persisted_runs_on_startup(tmp_path):
    p1 = SQLitePersistence(tmp_path / "runs.sqlite")
    store1 = RunStore(persistence=p1)
    run = store1.create("lot1", tmp_path)
    store1.update(run.run_id, status="complete")

    # Новый процесс/инстанс.
    p2 = SQLitePersistence(tmp_path / "runs.sqlite")
    store2 = RunStore(persistence=p2)
    restored = store2.get(run.run_id)
    assert restored is not None
    assert restored.status == "complete"
    assert restored.phase == "complete"  # Был "pending" → но мы пометили его complete


def test_store_marks_orphaned_runs_after_restart(tmp_path):
    """Незавершённый run (status != 'complete') после рестарта → 'orphaned by restart'."""
    p1 = SQLitePersistence(tmp_path / "runs.sqlite")
    store1 = RunStore(persistence=p1)
    run = store1.create("lot1", tmp_path)
    # НЕ обновляем — это эмуляция падения процесса в pending.

    p2 = SQLitePersistence(tmp_path / "runs.sqlite")
    store2 = RunStore(persistence=p2)
    restored = store2.get(run.run_id)
    assert restored is not None
    assert restored.status == "complete"  # принудительно (orphan handling)
    assert restored.phase == "error"
    assert "orphaned by restart" in (restored.error or "")


def test_app_with_persistence_db(tmp_path):
    """create_app(persistence_db=...) подключает SQLite-store."""
    db = tmp_path / "runs.sqlite"
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(settings=settings, mock_llm_text="x", persistence_db=db)
    client = TestClient(app)
    # Простой smoke: запустить + проверить что snapshot сохранён.
    workspace = _populated_workspace(tmp_path)
    response = client.post(
        "/lots/test_001/run",
        json={"workspace_path": str(workspace)},
    )
    assert response.status_code == 202
    p = SQLitePersistence(db)
    snaps = p.load_all()
    assert len(snaps) >= 1
    assert snaps[0].lot_id == "test_001"


# ─────────────────────────────────────────────────────────────────────────────
#  SSE streaming
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sse_client(tmp_path):
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(
        settings=settings,
        mock_llm_text="report\n<!-- MARP_START -->\n# Slide",
    )
    return TestClient(app)


def test_sse_emits_phase_and_done(sse_client, tmp_path):
    workspace = _populated_workspace(tmp_path)
    start = sse_client.post(
        "/lots/test_001/run",
        json={"workspace_path": str(workspace)},
    )
    assert start.status_code == 202
    run_id = start.json()["run_id"]

    with sse_client.stream("GET", f"/lots/test_001/stream/{run_id}") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = []
        for chunk in response.iter_text():
            events.append(chunk)
            if "event: done" in chunk:
                break
        body = "".join(events)
    assert "event: phase" in body
    assert "event: done" in body
    assert "done" in body  # final phase value


def test_sse_emits_error_for_unknown_run(sse_client):
    with sse_client.stream("GET", "/lots/x/stream/nonexistent") as response:
        body = "".join(response.iter_text())
    assert "event: error" in body
    assert "не найден" in body


# ─────────────────────────────────────────────────────────────────────────────
#  Artifacts via GLOB (survives restart)
# ─────────────────────────────────────────────────────────────────────────────

def test_artifacts_endpoint_uses_glob_not_inmemory_result(tmp_path):
    """После рестарта (in-memory result=None) /artifacts всё ещё работает через GLOB."""
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(settings=settings, mock_llm_text="r\n<!-- MARP_START -->\n# S",
                     persistence_db=p._db_path)
    client = TestClient(app)
    workspace = _populated_workspace(tmp_path)

    start = client.post(
        "/lots/test_001/run",
        json={"workspace_path": str(workspace)},
    )
    assert start.status_code == 202

    # Эмуляция рестарта: новый app + persistence из той же БД.
    app2 = create_app(settings=settings, mock_llm_text="r", persistence_db=p._db_path)
    client2 = TestClient(app2)
    response = client2.get("/lots/test_001/artifacts")
    assert response.status_code == 200
    a = response.json()
    assert a["memorandum"] is not None
    assert a["final_report"] is not None  # файл на диске пережил рестарт


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _populated_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    memo = root / "Memorandum"
    data = memo / "_data"
    incoming = memo / "incoming"
    for d in (memo, data, incoming):
        d.mkdir(exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "lot_id": "test_001",
        "generated_at": "2026-05-30T12:00:00+00:00",
        "target_scenario": {"was": "a", "trigger": "b", "to_plan": "c"},
        "egrn": {"tables": {}},
        "graph_ref": "graph.html",
        "documents_dates": [],
        "facts_index": [],
        "conflicts": [],
        "missing_layers": [],
    }
    (data / "enrich_test_001.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (incoming / "market_analysis.txt").write_text("market", encoding="utf-8")
    return root
