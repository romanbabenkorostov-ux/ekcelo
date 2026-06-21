-- Migration 0001 (access.sqlite) — RBAC access_grants table
-- Cycle 15 M2.
--
-- ВНИМАНИЕ: эта миграция применяется к ОТДЕЛЬНОЙ access.sqlite (не к ekcelo.sqlite).
-- Разделение по ADR-001: ЕГРН/ЭТП-данные не смешиваются с auth-данными.
-- См. obsidian/Architecture/cycle-15-rbac.md (M2) и cycle-15-rbac.md (M1).
--
-- Пути:
-- - access_db: EKCELO_ACCESS_DB env ИЛИ create_app(access_db=Path(...))
-- - default: рядом с ekcelo.sqlite (если задан), иначе ./access.sqlite

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS access_grants (
    grant_id        TEXT PRIMARY KEY,                -- UUID
    subject_sub     TEXT NOT NULL,                    -- кому выдан
    action          TEXT NOT NULL,                    -- view|edit|input|export|delegate|share
    resource_type   TEXT NOT NULL CHECK (resource_type IN ('lot','object','bundle')),
    resource_id     TEXT NOT NULL,                    -- конкретный ресурс
    granted_by      TEXT NOT NULL,                    -- кто выдал
    revocable       INTEGER NOT NULL DEFAULT 1 CHECK (revocable IN (0,1)),
    expires_at      TEXT,                             -- ISO datetime UTC, NULL = бессрочно
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Поиск гранта по «кто+что+над чем» — горячий путь can()
CREATE INDEX IF NOT EXISTS idx_access_grants_lookup
    ON access_grants(subject_sub, action, resource_type, resource_id);

-- Список грантов субъекта (для UI/админки)
CREATE INDEX IF NOT EXISTS idx_access_grants_subject
    ON access_grants(subject_sub);
