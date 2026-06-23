-- =============================================
-- Migration 0003 — Geo entities (§7, не-ЕГРН слой)
-- =============================================
-- Геосущность = именованная точка/контур, к которой привязываются активы
-- (objects, lots). Контур и точка эволюционируют во времени; одна сущность
-- может иметь и контур, и точку, и несколько из них (история).
--
-- M:N привязка: один актив может ссылаться на несколько geo (роли: primary,
-- access_point, reference); связь сама исторична (актив «переехал»).
--
-- Bitemporal:
--   valid_from / valid_to — «когда было в реальности» (закрытый интервал слева,
--     открытый справа; valid_to=NULL = «по сей день»).
--   recorded_at — «когда мы узнали» (для аудита/ретро-анализа).
--
-- Не-ЕГРН (ADR-001 + ADR-002): не восстанавливается из выписок; поля source
-- + confidence как в §6 (object_etp_profile). При пересоздании БД из ЕГРН
-- §7 НЕ затрагивается.
--
-- Источник правды:
--   obsidian/Database/geo-entities-7.md (схема + ER)
--   obsidian/Decisions/ADR-002-geo-entities.md (rationale)
-- =============================================

PRAGMA foreign_keys = ON;

-- =============================================
-- §7.1 Реестр гео-сущностей
-- =============================================
CREATE TABLE IF NOT EXISTS geo_entity (
    geo_uuid     TEXT PRIMARY KEY,          -- UUIDv4 строкой ("550e8400-...")
    name         TEXT NOT NULL,             -- "Поле №3", "Корпус А"
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',  -- manual|kmz|nspd|llm|exif
    confidence   REAL NOT NULL DEFAULT 1.0,
    CHECK (confidence >= 0 AND confidence <= 1)
);

-- =============================================
-- §7.2 История контуров (полигонов) — GeoJSON Geometry
-- =============================================
CREATE TABLE IF NOT EXISTS geo_entity_contour (
    contour_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_uuid     TEXT NOT NULL REFERENCES geo_entity(geo_uuid) ON DELETE CASCADE,
    geometry     TEXT NOT NULL,             -- GeoJSON: {"type":"Polygon","coordinates":[...]}
    valid_from   TEXT NOT NULL,             -- ISO date "YYYY-MM-DD" или ISO datetime
    valid_to     TEXT,                      -- NULL = по сей день
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',
    confidence   REAL NOT NULL DEFAULT 1.0,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (confidence >= 0 AND confidence <= 1)
);
CREATE INDEX IF NOT EXISTS idx_geo_contour_uuid
    ON geo_entity_contour(geo_uuid, valid_from);

-- =============================================
-- §7.3 История точек
-- =============================================
CREATE TABLE IF NOT EXISTS geo_entity_point (
    point_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_uuid     TEXT NOT NULL REFERENCES geo_entity(geo_uuid) ON DELETE CASCADE,
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',
    confidence   REAL NOT NULL DEFAULT 1.0,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (lat BETWEEN -90 AND 90),
    CHECK (lon BETWEEN -180 AND 180),
    CHECK (confidence >= 0 AND confidence <= 1)
);
CREATE INDEX IF NOT EXISTS idx_geo_point_uuid
    ON geo_entity_point(geo_uuid, valid_from);

-- =============================================
-- §7.4 Привязка активов к гео-сущностям (M:N + история)
-- =============================================
-- asset_type ∈ {'object','lot','oks','room','land','bu','equipment'}
-- asset_id = cad_number / lot_id / bu_id / equipment_id
-- role     = 'primary' | 'access_point' | 'reference' | …
CREATE TABLE IF NOT EXISTS asset_geo_link (
    link_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type   TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    geo_uuid     TEXT NOT NULL REFERENCES geo_entity(geo_uuid) ON DELETE RESTRICT,
    role         TEXT NOT NULL DEFAULT 'primary',
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
-- Один актив в одну роль может ссылаться на одну geo в один valid_from.
CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_geo_unique
    ON asset_geo_link(asset_type, asset_id, geo_uuid, role, valid_from);
-- Быстрый lookup «что у этого актива сейчас».
CREATE INDEX IF NOT EXISTS idx_asset_geo_lookup
    ON asset_geo_link(asset_type, asset_id, valid_from);
