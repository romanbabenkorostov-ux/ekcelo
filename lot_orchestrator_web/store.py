"""run_id → Run store с опциональным SQLite-persistence (cycle 5 + cycle 8)."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from lot_orchestrator.state_machine import OrchestrationResult

from lot_orchestrator_web.persistence import (
    RunSnapshot,
    SQLitePersistence,
    utc_now_iso,
)


RunStatus = Literal["pending", "running", "complete"]


@dataclass
class Run:
    run_id: str
    lot_id: str
    workspace_path: Path
    status: RunStatus = "pending"
    result: OrchestrationResult | None = None  # In-memory only; не сериализуется.
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    # Snapshot-поля — заполняются при load_all() после рестарта (когда result=None).
    restored_phase: str | None = None
    restored_warnings: list[str] = field(default_factory=list)
    restored_errors: list[str] = field(default_factory=list)

    @property
    def phase(self) -> str:
        if self.result is not None:
            return self.result.phase.value
        if self.restored_phase is not None:
            return self.restored_phase
        return self.status

    @property
    def warnings(self) -> list[str]:
        if self.result is not None:
            return list(self.result.warnings)
        return list(self.restored_warnings)

    @property
    def errors(self) -> list[str]:
        out: list[str] = []
        if self.error:
            out.append(self.error)
        if self.result is not None:
            out.extend(self.result.errors)
        else:
            out.extend(self.restored_errors)
        return out


class RunStore:
    """Threadsafe run-store с опциональным SQLite-persistence.

    Если `persistence` задан — каждое create/update сохраняется в SQLite.
    На старте store.load_persisted() поднимает completed-runs (running/pending
    помечаются как orphaned — процесс умер с незавершённой работой).
    """

    def __init__(self, persistence: SQLitePersistence | None = None):
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._persistence = persistence
        if persistence is not None:
            self._load_persisted()

    def create(self, lot_id: str, workspace_path: Path) -> Run:
        run_id = uuid.uuid4().hex
        run = Run(run_id=run_id, lot_id=lot_id, workspace_path=workspace_path)
        with self._lock:
            self._runs[run_id] = run
        self._persist(run)
        return run

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def latest_for_lot(self, lot_id: str) -> Run | None:
        with self._lock:
            runs = [r for r in self._runs.values() if r.lot_id == lot_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[0] if runs else None

    def update(self, run_id: str, **changes) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            for k, v in changes.items():
                setattr(run, k, v)
            if run.status == "complete" and run.finished_at is None:
                run.finished_at = datetime.now(timezone.utc)
        self._persist(run)

    # Обратная совместимость с прошлым API.
    def phase(self, run: Run) -> str:
        return run.phase

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

    def _load_persisted(self) -> None:
        assert self._persistence is not None
        for snap in self._persistence.load_all():
            run = Run(
                run_id=snap.run_id,
                lot_id=snap.lot_id,
                workspace_path=Path(snap.workspace_path),
                status=snap.status if snap.status == "complete" else "complete",
                error="orphaned by restart" if snap.status != "complete" else None,
                started_at=datetime.fromisoformat(snap.started_at),
                finished_at=datetime.fromisoformat(snap.finished_at)
                if snap.finished_at
                else None,
                restored_phase=snap.phase if snap.status == "complete" else "error",
                restored_warnings=snap.warnings,
                restored_errors=snap.errors,
            )
            self._runs[run.run_id] = run


_singleton: "RunStore | object" = None  # может быть RedisRunStore (duck-typed)


def get_store() -> RunStore:
    """Dependency-injection точка для FastAPI."""
    global _singleton
    if _singleton is None:
        _singleton = RunStore()
    return _singleton


def configure_store(persistence: SQLitePersistence | None) -> RunStore:
    """Пересоздаёт singleton с заданным persistence (на старте приложения)."""
    global _singleton
    _singleton = RunStore(persistence=persistence)
    return _singleton


def configure_redis_store(
    redis_client,
    *,
    persistence: SQLitePersistence | None = None,
):
    """Пересоздаёт singleton как RedisRunStore (multi-worker production)."""
    from lot_orchestrator_web.redis_store import RedisRunStore
    global _singleton
    _singleton = RedisRunStore(redis_client, persistence=persistence)
    return _singleton


def reset_store_for_tests() -> None:
    global _singleton
    _singleton = RunStore()
