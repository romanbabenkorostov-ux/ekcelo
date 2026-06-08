-- Migration 0002 — Bundle storage sidecar table
-- Part of P0.3 sub-stage C3.1.
-- Хранит метаданные импортированных Bundle'ов для реверс-экспорта (GET
-- /bundles/{id}/download). KMZ-файлы лежат на ФС в `<bundles_dir>/<bundle_id>.kmz`
-- — ссылка в `kmz_path`. См. `obsidian/Architecture/p0-viewmodel.md` (C3).
--
-- bundle_id = sha256(canonical-manifest-json), стабилен для одного манифеста;
-- идемпотентный import → одинаковый bundle_id → нет дубликата.

CREATE TABLE IF NOT EXISTS bundles (
    bundle_id            TEXT PRIMARY KEY,             -- sha256(manifest_canonical_json) hex
    bundle_version       TEXT NOT NULL,                -- из manifest
    contracts_version    TEXT NOT NULL,                -- из manifest
    kmz_contract_version TEXT NOT NULL,                -- из manifest
    kind                 TEXT NOT NULL CHECK (kind IN ('object','lot')),
    primary_cad_number   TEXT,                         -- из manifest
    manifest_json        TEXT NOT NULL,                -- полный manifest (для fmt=manifest и fmt=zip)
    kmz_path             TEXT,                         -- относительный путь к KMZ внутри bundles_dir
    kmz_sha256           TEXT,                         -- проверка целостности при отдаче
    kmz_bytes            INTEGER,
    imported_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bundles_imported_at ON bundles(imported_at);
CREATE INDEX IF NOT EXISTS idx_bundles_kind ON bundles(kind);
