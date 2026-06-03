"""RedisRunStore (cycle 9) — через fakeredis, без реального Redis-сервера."""
from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest

from lot_orchestrator_web.persistence import SQLitePersistence
from lot_orchestrator_web.redis_store import (
    RedisRunStore,
    _CHANNEL_EVENTS,
    _KEY_LOT_RUNS,
    _KEY_RUN,
)


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def redis_store(redis_client):
    return RedisRunStore(redis_client)


# ─────────────────────────────────────────────────────────────────────────────
#  Core API совместимость с in-memory RunStore
# ─────────────────────────────────────────────────────────────────────────────

def test_create_writes_to_redis(redis_store, redis_client, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    data = redis_client.hgetall(_KEY_RUN.format(run_id=run.run_id))
    assert data
    assert redis_client.smembers(_KEY_LOT_RUNS.format(lot_id="lot1")) == {run.run_id.encode()}


def test_get_returns_none_for_unknown(redis_store):
    assert redis_store.get("nonexistent") is None


def test_get_roundtrip(redis_store, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    fetched = redis_store.get(run.run_id)
    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.lot_id == "lot1"
    assert fetched.workspace_path == tmp_path
    assert fetched.status == "pending"
    assert fetched.phase == "validating"


def test_update_changes_status_and_phase(redis_store, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    redis_store.update(run.run_id, status="complete", phase="done")
    after = redis_store.get(run.run_id)
    assert after.status == "complete"
    assert after.phase == "done"
    assert after.finished_at is not None


def test_update_unknown_run_noop(redis_store):
    redis_store.update("nonexistent", status="complete")  # не падает


def test_latest_for_lot_picks_newest(redis_store, tmp_path):
    import time
    r1 = redis_store.create("lot1", tmp_path)
    time.sleep(0.01)
    r2 = redis_store.create("lot1", tmp_path)
    latest = redis_store.latest_for_lot("lot1")
    assert latest.run_id == r2.run_id


def test_latest_for_lot_none_when_no_runs(redis_store):
    assert redis_store.latest_for_lot("never_used") is None


def test_warnings_and_errors_serialized(redis_store, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    redis_store.update(
        run.run_id,
        warnings=["w1", "w2"],
        errors=["e1"],
        error="fatal",
    )
    after = redis_store.get(run.run_id)
    assert after.warnings == ["w1", "w2"]
    assert after.errors == ["e1"]
    assert after.error == "fatal"


# ─────────────────────────────────────────────────────────────────────────────
#  Pub/Sub
# ─────────────────────────────────────────────────────────────────────────────

def test_publish_on_create(redis_store, redis_client, tmp_path):
    ps = redis_client.pubsub()
    # Подписываемся ДО create через предсказуемый run_id невозможно,
    # поэтому проверяем через свежесозданный run.
    run = redis_store.create("lot1", tmp_path)
    ps.subscribe(_CHANNEL_EVENTS.format(run_id=run.run_id))
    # Эмитим повторно через update, чтобы поймать сообщение.
    redis_store.update(run.run_id, phase="context_injection")
    # Pull messages: первое — subscribe confirmation, второе — наш publish.
    messages = []
    while True:
        msg = ps.get_message(timeout=0.1)
        if msg is None:
            break
        messages.append(msg)
    payload_msgs = [m for m in messages if m.get("type") == "message"]
    assert payload_msgs
    data = json.loads(payload_msgs[0]["data"])
    assert data["phase"] == "context_injection"


def test_subscribe_events_yields_phase_changes(redis_store, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    ps = redis_store.subscribe_events(run.run_id)
    redis_store.update(run.run_id, phase="llm_running")
    messages = []
    for _ in range(5):
        m = ps.get_message(timeout=0.1)
        if m is None:
            break
        messages.append(m)
    payload = [m for m in messages if m.get("type") == "message"]
    assert payload
    assert json.loads(payload[0]["data"])["phase"] == "llm_running"


# ─────────────────────────────────────────────────────────────────────────────
#  Persistence integration
# ─────────────────────────────────────────────────────────────────────────────

def test_persistence_mirror(redis_client, tmp_path):
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    store = RedisRunStore(redis_client, persistence=p)
    run = store.create("lot1", tmp_path)
    store.update(run.run_id, status="complete", phase="done")
    snaps = p.load_all()
    assert len(snaps) == 1
    assert snaps[0].status == "complete"
    assert snaps[0].phase == "done"


def test_restore_from_persistence_into_empty_redis(tmp_path):
    """После рестарта Redis (потеря данных) snapshot восстанавливается из SQLite."""
    redis_client_1 = fakeredis.FakeRedis()
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    store_1 = RedisRunStore(redis_client_1, persistence=p)
    run = store_1.create("lot1", tmp_path)
    store_1.update(run.run_id, status="complete", phase="done")

    # Эмулируем рестарт Redis (пустой клиент) + тот же SQLite.
    redis_client_2 = fakeredis.FakeRedis()
    store_2 = RedisRunStore(redis_client_2, persistence=p)
    restored = store_2.get(run.run_id)
    assert restored is not None
    assert restored.status == "complete"
    assert restored.phase == "done"


def test_orphan_marking_after_crash(tmp_path):
    """Незавершённый run + рестарт Redis → orphaned."""
    redis_1 = fakeredis.FakeRedis()
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    store_1 = RedisRunStore(redis_1, persistence=p)
    run = store_1.create("lot1", tmp_path)
    # Не обновляем — эмуляция падения процесса в pending.

    redis_2 = fakeredis.FakeRedis()
    store_2 = RedisRunStore(redis_2, persistence=p)
    restored = store_2.get(run.run_id)
    assert restored.status == "complete"
    assert restored.phase == "error"
    assert "orphaned" in (restored.error or "")


def test_restore_does_not_clobber_existing_redis_state(tmp_path):
    """Если в Redis уже есть run — restore-from-SQLite его НЕ перезатирает."""
    redis_client_1 = fakeredis.FakeRedis()
    p = SQLitePersistence(tmp_path / "runs.sqlite")
    store_1 = RedisRunStore(redis_client_1, persistence=p)
    run = store_1.create("lot1", tmp_path)
    store_1.update(run.run_id, phase="llm_running", status="running")
    # SQLite видит running snapshot.

    # Второй worker подключился к тому же Redis — Redis уже содержит running запись.
    # restore_from_persistence не должен затереть текущий phase orphaned'ом.
    store_2 = RedisRunStore(redis_client_1, persistence=p)
    restored = store_2.get(run.run_id)
    assert restored.phase == "llm_running"  # как в Redis, не "error"
    assert restored.status == "running"


# ─────────────────────────────────────────────────────────────────────────────
#  In-process result storage (для OrchestrationResult который нельзя в Redis)
# ─────────────────────────────────────────────────────────────────────────────

def test_in_process_result_storage(redis_store, tmp_path):
    """Result сохраняется в локальном dict, phase/warnings/errors из него попадают в Redis."""
    from lot_orchestrator.state_machine import OrchestrationResult, Phase as P
    run = redis_store.create("lot1", tmp_path)
    fake_result = OrchestrationResult(phase=P.DONE, lot_id="lot1",
                                       warnings=["mock_warning"])
    redis_store.update(run.run_id, status="complete", result=fake_result)
    after = redis_store.get(run.run_id)
    assert after.result is fake_result
    assert after.phase == "done"
    assert "mock_warning" in after.warnings


def test_phase_helper_for_run(redis_store, tmp_path):
    run = redis_store.create("lot1", tmp_path)
    assert redis_store.phase(run) == "validating"
    redis_store.update(run.run_id, phase="done")
    assert redis_store.phase(redis_store.get(run.run_id)) == "done"
