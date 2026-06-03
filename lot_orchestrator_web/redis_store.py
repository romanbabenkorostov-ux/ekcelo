"""Redis-backed RunStore для multi-worker production deploy (cycle 9).

Архитектура:
- Hash `ekcelo:run:<run_id>` — состояние одного run'а (status/phase/warnings/...).
- Set `ekcelo:lots:<lot_id>` — run_id'ы для лота (для latest_for_lot).
- Pub/Sub channel `ekcelo:events:<run_id>` — phase changes (для SSE).
- SQLite (если задана) — durable snapshot mirror.

Запуск:
    pip install -e ".[orchestrator-redis]"
    REDIS_URL=redis://localhost:6379/0 uvicorn ... --workers 4
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

from lot_orchestrator.state_machine import OrchestrationResult

from lot_orchestrator_web.persistence import (
    RunSnapshot,
    SQLitePersistence,
)


_KEY_RUN = "ekcelo:run:{run_id}"
_KEY_LOT_RUNS = "ekcelo:lot_runs:{lot_id}"
_CHANNEL_EVENTS = "ekcelo:events:{run_id}"


class RedisLike(Protocol):
    """Минимальный интерфейс Redis-клиента (для тестов через fakeredis)."""

    def hset(self, name: str, mapping: dict, **kwargs) -> Any: ...
    def hgetall(self, name: str) -> dict: ...
    def sadd(self, name: str, *values: str) -> Any: ...
    def smembers(self, name: str) -> set: ...
    def publish(self, channel: str, message: str) -> Any: ...
    def pubsub(self) -> Any: ...
    def delete(self, *names: str) -> Any: ...
    def scan_iter(self, match: str | None = None) -> Iterator[bytes]: ...


@dataclass
class Run:
    """Aware Run: данные хранятся в Redis, поля — lazy-проперти."""

    run_id: str
    lot_id: str
    workspace_path: Path
    status: str = "pending"
    phase: str = "validating"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error: str | None = None
    result: OrchestrationResult | None = None  # In-process only.


class RedisRunStore:
    """Multi-worker run store через Redis hash + pub/sub.

    Опционально пишет snapshot в SQLite для durable восстановления при потере Redis.
    """

    def __init__(
        self,
        redis_client: RedisLike,
        *,
        persistence: SQLitePersistence | None = None,
    ):
        self._redis = redis_client
        self._persistence = persistence
        self._in_process_results: dict[str, OrchestrationResult] = {}
        self._lock = threading.Lock()
        if persistence is not None:
            self._restore_from_persistence()

    # ── Public API (совместим с lot_orchestrator_web.store.RunStore) ───

    def create(self, lot_id: str, workspace_path: Path) -> Run:
        run_id = uuid.uuid4().hex
        run = Run(run_id=run_id, lot_id=lot_id, workspace_path=workspace_path)
        self._write(run)
        self._redis.sadd(_KEY_LOT_RUNS.format(lot_id=lot_id), run_id)
        self._persist(run)
        self._publish(run)
        return run

    def get(self, run_id: str) -> Run | None:
        data = self._redis.hgetall(_KEY_RUN.format(run_id=run_id))
        if not data:
            return None
        return self._from_hash(data, run_id=run_id)

    def latest_for_lot(self, lot_id: str) -> Run | None:
        run_ids = self._redis.smembers(_KEY_LOT_RUNS.format(lot_id=lot_id))
        runs: list[Run] = []
        for rid in run_ids:
            rid_str = rid.decode() if isinstance(rid, bytes) else rid
            r = self.get(rid_str)
            if r is not None:
                runs.append(r)
        if not runs:
            return None
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[0]

    def update(self, run_id: str, **changes) -> None:
        run = self.get(run_id)
        if run is None:
            return
        # In-process result (нельзя сериализовать) — храним отдельно.
        if "result" in changes:
            popped_result = changes.pop("result")
            with self._lock:
                if popped_result is None:
                    self._in_process_results.pop(run_id, None)
                else:
                    self._in_process_results[run_id] = popped_result
            # Извлекаем phase/warnings/errors из result в hash.
            if popped_result is not None:
                changes.setdefault("phase", popped_result.phase.value)
                changes.setdefault("warnings", list(popped_result.warnings))
                changes.setdefault("errors", list(popped_result.errors))

        for k, v in changes.items():
            setattr(run, k, v)
        if run.status == "complete" and run.finished_at is None:
            run.finished_at = datetime.now(timezone.utc)
        self._write(run)
        self._persist(run)
        self._publish(run)

    def phase(self, run: Run) -> str:
        """Совместимость с in-memory RunStore API."""
        return run.phase

    def subscribe_events(self, run_id: str):
        """Возвращает pub/sub-подписку на phase-events для run_id.

        Использование:
            ps = store.subscribe_events(run_id)
            for msg in ps.listen():
                if msg["type"] == "message":
                    data = json.loads(msg["data"])
        """
        ps = self._redis.pubsub()
        ps.subscribe(_CHANNEL_EVENTS.format(run_id=run_id))
        return ps

    # ── Internals ───────────────────────────────────────────────────────

    def _write(self, run: Run) -> None:
        mapping = {
            "run_id": run.run_id,
            "lot_id": run.lot_id,
            "workspace_path": str(run.workspace_path),
            "status": run.status,
            "phase": run.phase,
            "warnings": json.dumps(run.warnings, ensure_ascii=False),
            "errors": json.dumps(run.errors, ensure_ascii=False),
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else "",
            "error": run.error or "",
        }
        self._redis.hset(_KEY_RUN.format(run_id=run.run_id), mapping=mapping)

    def _from_hash(self, data: dict, *, run_id: str) -> Run:
        def _get(key: str, default: str = "") -> str:
            v = data.get(key) or data.get(key.encode())
            if isinstance(v, bytes):
                v = v.decode()
            return v if v is not None else default

        run = Run(
            run_id=run_id,
            lot_id=_get("lot_id"),
            workspace_path=Path(_get("workspace_path")),
            status=_get("status", "pending"),
            phase=_get("phase", "validating"),
            warnings=json.loads(_get("warnings", "[]") or "[]"),
            errors=json.loads(_get("errors", "[]") or "[]"),
            started_at=datetime.fromisoformat(_get("started_at")),
            finished_at=datetime.fromisoformat(_get("finished_at"))
            if _get("finished_at")
            else None,
            error=_get("error") or None,
            result=self._in_process_results.get(run_id),
        )
        return run

    def _persist(self, run: Run) -> None:
        if self._persistence is None:
            return
        snap = RunSnapshot(
            run_id=run.run_id,
            lot_id=run.lot_id,
            workspace_path=str(run.workspace_path),
            status=run.status,
            phase=run.phase,
            warnings=run.warnings,
            errors=run.errors,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
        )
        self._persistence.save(snap)

    def _publish(self, run: Run) -> None:
        msg = {
            "run_id": run.run_id,
            "status": run.status,
            "phase": run.phase,
            "warnings": run.warnings,
            "errors": run.errors,
        }
        self._redis.publish(
            _CHANNEL_EVENTS.format(run_id=run.run_id),
            json.dumps(msg, ensure_ascii=False),
        )

    def _restore_from_persistence(self) -> None:
        """На старте подтягиваем completed-snapshot'ы в Redis (если их там нет).

        Незавершённые (running/pending) помечаются orphaned — процесс мог упасть.
        """
        assert self._persistence is not None
        for snap in self._persistence.load_all():
            key = _KEY_RUN.format(run_id=snap.run_id)
            if self._redis.hgetall(key):
                continue  # Уже есть в Redis — не трогаем (мог быть рестарт одного worker'а).
            status = snap.status if snap.status == "complete" else "complete"
            phase = snap.phase if snap.status == "complete" else "error"
            error = "" if snap.status == "complete" else "orphaned by restart"
            mapping = {
                "run_id": snap.run_id,
                "lot_id": snap.lot_id,
                "workspace_path": snap.workspace_path,
                "status": status,
                "phase": phase,
                "warnings": json.dumps(snap.warnings, ensure_ascii=False),
                "errors": json.dumps(snap.errors, ensure_ascii=False),
                "started_at": snap.started_at,
                "finished_at": snap.finished_at or "",
                "error": error,
            }
            self._redis.hset(key, mapping=mapping)
            self._redis.sadd(_KEY_LOT_RUNS.format(lot_id=snap.lot_id), snap.run_id)


def make_redis_client(redis_url: str) -> RedisLike:
    """Создаёт Redis-клиент с дефолтными настройками для ekcelo."""
    import redis  # lazy: чтобы тесты с fakeredis не требовали redis-py
    return redis.Redis.from_url(redis_url, decode_responses=False)
