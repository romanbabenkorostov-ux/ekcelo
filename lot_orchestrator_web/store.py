"""In-memory store: run_id → OrchestrationResult (orchestrator_spec.md §5)."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from lot_orchestrator.state_machine import OrchestrationResult, Phase


RunStatus = Literal["pending", "running", "complete"]


@dataclass
class Run:
    run_id: str
    lot_id: str
    workspace_path: Path
    status: RunStatus = "pending"
    result: OrchestrationResult | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class RunStore:
    """Потокобезопасный in-memory словарь run_id → Run.

    Подходит для одно-процессного uvicorn'а. Multi-worker / persistence — cycle 6+.
    """

    def __init__(self):
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(self, lot_id: str, workspace_path: Path) -> Run:
        run_id = uuid.uuid4().hex
        run = Run(run_id=run_id, lot_id=lot_id, workspace_path=workspace_path)
        with self._lock:
            self._runs[run_id] = run
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

    def phase(self, run: Run) -> str:
        if run.result is not None:
            return run.result.phase.value
        return run.status


_singleton: RunStore | None = None


def get_store() -> RunStore:
    """Dependency-injection точка для FastAPI."""
    global _singleton
    if _singleton is None:
        _singleton = RunStore()
    return _singleton


def reset_store_for_tests() -> None:
    """Только для тестов — пересоздаёт singleton."""
    global _singleton
    _singleton = RunStore()
