"""SQLite GrantStore (cycle 15, M2) — persistence для RBAC грантов.

Реализует `lot_orchestrator_web.rbac.GrantStore` Protocol поверх отдельной
sqlite-БД (`access.sqlite`), НЕ ekcelo.sqlite.

Архитектурное решение (ADR-001 + cycle 15 M2 reasoning):
- ЕГРН/ЭТП данные хранятся в ekcelo.sqlite (§1..§6 + §6 ЭТП-профиль).
- Access-данные — отдельный файл `access.sqlite` (миграция
  `schema/migrations/access/0001_access_grants.sql`).
- Bundle export физически не может вытащить гранты — они в другой БД.
- Multi-tenant сценарий: shared ekcelo + per-tenant access — работает «даром».

Конфигурация:
- `EKCELO_ACCESS_DB` env (path к access.sqlite)
- ИЛИ `create_app(access_db=Path(...))` явно

См. также:
- `lot_orchestrator_web/rbac.py` (cycle 15 M1 ядро + InMemoryGrantStore).
- `obsidian/Architecture/cycle-15-rbac.md` (M1+M2 снимок).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from lot_orchestrator_web.rbac import (
    Action,
    Grant,
    Resource,
    ResourceType,
)


_REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION = _REPO_ROOT / "schema" / "migrations" / "access" / "0001_access_grants.sql"

_FALLBACK_DDL = """
CREATE TABLE IF NOT EXISTS access_grants (
    grant_id        TEXT PRIMARY KEY,
    subject_sub     TEXT NOT NULL,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     TEXT NOT NULL,
    granted_by      TEXT NOT NULL,
    revocable       INTEGER NOT NULL DEFAULT 1,
    expires_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_access_grants_lookup
    ON access_grants(subject_sub, action, resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_access_grants_subject
    ON access_grants(subject_sub);
"""


class SQLiteGrantStore:
    """RBAC GrantStore с sqlite-persistence в access.sqlite.

    Удовлетворяет `rbac.GrantStore` Protocol (duck-typing). Lazy-инициализация
    схемы: при первом обращении применяет миграцию (если файл не существует
    или схема пустая).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            if _MIGRATION.is_file():
                conn.executescript(_MIGRATION.read_text(encoding="utf-8"))
            else:
                conn.executescript(_FALLBACK_DDL)
            conn.commit()
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────
    #  GrantStore protocol
    # ─────────────────────────────────────────────────────────────────────

    def add(self, grant: Grant) -> str:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO access_grants(grant_id, subject_sub, action, "
                "resource_type, resource_id, granted_by, revocable, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    grant.grant_id,
                    grant.subject_sub,
                    grant.action.value,
                    grant.resource.type.value,
                    grant.resource.id,
                    grant.granted_by,
                    1 if grant.revocable else 0,
                    grant.expires_at.isoformat() if grant.expires_at else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return grant.grant_id

    def revoke(self, grant_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT revocable FROM access_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
            if row is None:
                return False
            if not row["revocable"]:
                return False
            conn.execute(
                "DELETE FROM access_grants WHERE grant_id = ?",
                (grant_id,),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def find(
        self,
        subject_sub: str,
        action: Action,
        resource: Resource,
    ) -> Grant | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM access_grants WHERE subject_sub = ? "
                "AND action = ? AND resource_type = ? AND resource_id = ? "
                "LIMIT 1",
                (subject_sub, action.value, resource.type.value, resource.id),
            ).fetchone()
        finally:
            conn.close()
        return _row_to_grant(row) if row else None

    def list_for_subject(self, subject_sub: str) -> list[Grant]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM access_grants WHERE subject_sub = ? "
                "ORDER BY created_at",
                (subject_sub,),
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_grant(r) for r in rows]

    def get(self, grant_id: str) -> Grant | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM access_grants WHERE grant_id = ? LIMIT 1",
                (grant_id,),
            ).fetchone()
        finally:
            conn.close()
        return _row_to_grant(row) if row else None


def _row_to_grant(row: sqlite3.Row) -> Grant:
    expires_at = None
    if row["expires_at"]:
        expires_at = datetime.fromisoformat(row["expires_at"])
    return Grant(
        subject_sub=row["subject_sub"],
        action=Action(row["action"]),
        resource=Resource(
            ResourceType(row["resource_type"]),
            row["resource_id"],
        ),
        granted_by=row["granted_by"],
        revocable=bool(row["revocable"]),
        expires_at=expires_at,
        grant_id=row["grant_id"],
    )
