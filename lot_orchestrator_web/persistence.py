"""SQLite-persistence для RunStore (cycle 8).

Сохраняет минимальный snapshot Run'а: фаза, warnings, errors, времена.
`OrchestrationResult` НЕ сериализуется — артефакты (final_report.md и т.д.)
живут на диске и подбираются GLOB'ом в /artifacts handler'е.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    lot_id          TEXT NOT NULL,
    workspace_path  TEXT NOT NULL,
    status          TEXT NOT NULL,
    phase           TEXT NOT NULL,
    warnings_json   TEXT NOT NULL DEFAULT '[]',
    errors_json     TEXT NOT NULL DEFAULT '[]',
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_lot_id ON runs(lot_id);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
"""


@dataclass
class RunSnapshot:
    run_id: str
    lot_id: str
    workspace_path: str
    status: str
    phase: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str | None = None


class SQLitePersistence:
    """Threadsafe SQLite snapshot store.

    Connection-per-call: SQLite разрешает многопоточный доступ если каждая
    операция использует отдельное соединение (sqlite3 в Python 3.11+ deny
    multi-thread sharing по умолчанию).
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def save(self, snap: RunSnapshot) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    "INSERT INTO runs(run_id, lot_id, workspace_path, status, phase, "
                    "warnings_json, errors_json, started_at, finished_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(run_id) DO UPDATE SET "
                    "status=excluded.status, phase=excluded.phase, "
                    "warnings_json=excluded.warnings_json, errors_json=excluded.errors_json, "
                    "finished_at=excluded.finished_at",
                    (
                        snap.run_id, snap.lot_id, snap.workspace_path,
                        snap.status, snap.phase,
                        json.dumps(snap.warnings, ensure_ascii=False),
                        json.dumps(snap.errors, ensure_ascii=False),
                        snap.started_at, snap.finished_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def load_all(self) -> list[RunSnapshot]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at"
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_snapshot(r) for r in rows]


def _row_to_snapshot(row: sqlite3.Row) -> RunSnapshot:
    return RunSnapshot(
        run_id=row["run_id"],
        lot_id=row["lot_id"],
        workspace_path=row["workspace_path"],
        status=row["status"],
        phase=row["phase"],
        warnings=json.loads(row["warnings_json"]),
        errors=json.loads(row["errors_json"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
