-- =============================================
-- EKCELO — Current DB Schema
-- БД = слепок ЕГРН + ЭТП-профиль (см. CLAUDE.md §3, ADR-001)
--   §1..§5 — слепок ЕГРН (объекты, права, выписки, ограничения)
--   §6     — ЭТП-профиль (не-ЕГРН слой, не восстанавливается из выписок)
-- Единый источник правды для Python + Frontend.
-- Дата: 2026-05-27
-- Миграции: schema/migrations/
-- =============================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- =============================================
-- 1. Основные объекты недвижимости
-- =============================================
CREATE TABLE IF NOT EXISTS objects (
    cad_number          TEXT PRIMARY KEY,
    object_type         TEXT NOT NULL,           -- land | building | construction | flat | room
    address             TEXT,
    area                REAL,                     -- площадь м²
    category            TEXT,                     -- категория земель
    permitted_use       TEXT,                     -- разрешённое использование (текст)
    purpose             TEXT,                     -- назначение
    floors              INTEGER,                  -- этажность (для ОКС)
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- =============================================
-- 2. Реестр правообладателей
-- =============================================
CREATE TABLE IF NOT EXISTS entity_registry (
    inn                 TEXT PRIMARY KEY,
    name_full           TEXT NOT NULL,
    name_short          TEXT,
    ogrn                TEXT,
    entity_type         TEXT,                     -- ЮЛ | ИП | ФЛ | Гос
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- =============================================
-- 3. Права и доли
-- =============================================
CREATE TABLE IF NOT EXISTS rights (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number          TEXT NOT NULL REFERENCES objects(cad_number) ON DELETE CASCADE,
    right_type          TEXT NOT NULL,            -- ownership, lease, etc.
    right_holder_inn    TEXT REFERENCES entity_registry(inn),
    share_numerator     INTEGER,
    share_denominator   INTEGER,
    registration_number TEXT,
    registration_date   TEXT,
    source_extract_id   INTEGER,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- =============================================
-- 4. История выписок
-- =============================================
CREATE TABLE IF NOT EXISTS extracts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    extract_number      TEXT,
    cad_number          TEXT NOT NULL REFERENCES objects(cad_number),
    extract_date        TEXT NOT NULL,
    document_type       TEXT,
    raw_json            TEXT,                     -- оригинальная выписка (при необходимости)
    parsed_at           TEXT DEFAULT (datetime('now')),
    parser_version      TEXT
);

-- =============================================
-- 5. Дополнительные сущности (ограничения, обременения и т.д.)
-- =============================================
CREATE TABLE IF NOT EXISTS object_restrictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number          TEXT NOT NULL REFERENCES objects(cad_number),
    restrict_type       TEXT,                     -- czuit_zone, okn_territory и т.д.
    description         TEXT,
    registry_number     TEXT,
    valid_from          TEXT,
    valid_to            TEXT,
    basis_doc           TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- Индексы для производительности
CREATE INDEX idx_objects_type ON objects(object_type);
CREATE INDEX idx_rights_cad ON rights(cad_number);
CREATE INDEX idx_rights_inn ON rights(right_holder_inn);
CREATE INDEX idx_extracts_cad_date ON extracts(cad_number, extract_date);
CREATE INDEX idx_restrictions_cad ON object_restrictions(cad_number);

-- =============================================
-- 6. ЭТП-профиль (НЕ-ЕГРН слой; см. ADR-001, CLAUDE.md §3)
-- =============================================
-- Гэп-поля для развёрнутого описания лота на ЭТП.
-- Заполняется ОСВ-листом экономиста, EXIF фото, NSPD, LLM.
-- При пересоздании БД из выписок ЭТП-профиль НЕ восстанавливается.
-- Полная спецификация: docs/etp_export/SPEC_etp_export.md §3, §5.
CREATE TABLE IF NOT EXISTS object_etp_profile (
    cad_number      TEXT PRIMARY KEY REFERENCES objects(cad_number) ON DELETE CASCADE,
    location_extra  TEXT,                        -- JSON: {landmark, transport_access, environment_short}
    building_extra  TEXT,                        -- JSON: {renovation_year, wear_degree, engineering{}, amenities[]}
    layout          TEXT,                        -- JSON: {layout_type, ceiling_height_m, finish_level, finish_state, windows, entry_group, current_condition_comment}
    legal_extra     TEXT,                        -- JSON: {use_type_fact, zoning, special_restrictions[]}
    risks           TEXT,                        -- JSON: {technical_risks[], legal_risks[], location_risks[], other_risks[]}
    extras          TEXT,                        -- JSON: {furniture, advantages[], notes}
    source          TEXT NOT NULL CHECK (source IN ('osv','exif','manual','nspd','llm')),
    confidence      REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- lots.lot_id формат: [A-Za-z0-9_:/-]+, длина 1..256.
-- Совместимо с CONTRACT_KMZ.md §6 graph_node_id → viewer Phase 2 overlay
-- переиспользует S5-инфру (CORRESPONDENCE/026).
CREATE TABLE IF NOT EXISTS lots (
    lot_id              TEXT PRIMARY KEY CHECK (
                            length(lot_id) BETWEEN 1 AND 256
                            AND lot_id NOT GLOB '*[^A-Za-z0-9_:/-]*'
                        ),
    name                TEXT NOT NULL,
    platform_targets    TEXT,                    -- JSON array
    procedure_type      TEXT,
    deal_type           TEXT CHECK (deal_type IS NULL OR deal_type IN ('sale','lease','other')),
    primary_cad_number  TEXT REFERENCES objects(cad_number) ON DELETE SET NULL,
    notes_md            TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lot_items (
    lot_id      TEXT NOT NULL REFERENCES lots(lot_id) ON DELETE CASCADE,
    cad_number  TEXT NOT NULL REFERENCES objects(cad_number) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('building','land','room','equipment','structure')),
    ord         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (lot_id, cad_number)
);

CREATE INDEX idx_etp_profile_source ON object_etp_profile(source);
CREATE INDEX idx_lots_primary ON lots(primary_cad_number);
CREATE INDEX idx_lot_items_cad ON lot_items(cad_number);
-- =============================================================================
-- §7 GEO ENTITIES (не-ЕГРН, ADR-002, mirror migration 0003)
-- =============================================================================
-- Геосущность (точка/контур) — отдельная сущность, к которой M:N привязываются
-- активы. История во времени (bitemporal: valid_from/to + recorded_at). При
-- пересоздании БД из выписок ЕГРН §7 НЕ восстанавливается (как и §6).
-- Полные комментарии и rationale — в obsidian/Database/geo-entities-7.md.

CREATE TABLE IF NOT EXISTS geo_entity (
    geo_uuid     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',
    confidence   REAL NOT NULL DEFAULT 1.0,
    CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE TABLE IF NOT EXISTS geo_entity_contour (
    contour_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_uuid     TEXT NOT NULL REFERENCES geo_entity(geo_uuid) ON DELETE CASCADE,
    geometry     TEXT NOT NULL,
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source       TEXT NOT NULL DEFAULT 'manual',
    confidence   REAL NOT NULL DEFAULT 1.0,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (confidence >= 0 AND confidence <= 1)
);
CREATE INDEX IF NOT EXISTS idx_geo_contour_uuid
    ON geo_entity_contour(geo_uuid, valid_from);

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
CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_geo_unique
    ON asset_geo_link(asset_type, asset_id, geo_uuid, role, valid_from);
CREATE INDEX IF NOT EXISTS idx_asset_geo_lookup
    ON asset_geo_link(asset_type, asset_id, valid_from);

-- =============================================================================
-- §8 ГЕОМЕТРИЯ ИЗ ВЫПИСОК ЕГРН (ADR-007, mirror migration 0006)
-- =============================================================================
-- В отличие от §6 и §7, этот слой — ЧАСТЬ СЛЕПКА ЕГРН: каждая строка выведена
-- из XML-выписки, подписанной ЭП Роскадастра, и при пересоздании БД из тех же
-- выписок воспроизводится. Поэтому здесь нет `confidence`: у документа
-- Росреестра есть заявленная погрешность съёмки (`accuracy_m`) — это другая
-- величина, чем наша уверенность в собственной обводке.
-- Полные комментарии и rationale — schema/migrations/0006_egrn_geometry.sql
-- и obsidian/Database/egrn-geometry-8.md.
--
-- ГЛАВНОЕ ПРАВИЛО ЧТЕНИЯ: контуры участка (`kind='parcel'`) и контуры его
-- частей — ЧЗУ (`kind='part'`) — лежат в одной таблице, но их площади НЕЛЬЗЯ
-- складывать: ЧЗУ находится ВНУТРИ участка. Любая агрегация идёт через
-- `v_egrn_parcel_contour`.

CREATE TABLE IF NOT EXISTS egrn_contour (
    contour_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number        TEXT NOT NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('parcel', 'part')),
    contour_no        INTEGER NOT NULL,
    contour_cad       TEXT,                    -- заполнен только у ЕЗП
    part_number       TEXT,
    part_mnemonic     TEXT,                    -- «26:29-6.395-ЧЗУ1»
    geom_geojson      TEXT NOT NULL,           -- GeoJSON Polygon, lon/lat
    crs               TEXT NOT NULL DEFAULT 'EPSG:4326',
    area_computed_sqm REAL,                    -- по координатам, в метрах МСК
    area_declared_sqm REAL,                    -- из той же выписки
    accuracy_m        REAL,                    -- delta_geopoint выписки
    sk_id             TEXT,                    -- «МСК-26 от СК-95, зона 1»
    msk_zone          TEXT,                    -- ключ msk.MSK_ZONES
    centroid_lon      REAL,
    centroid_lat      REAL,
    source            TEXT NOT NULL DEFAULT 'egrn_xml',
    source_extract_number TEXT,                -- КУВИ-001/...
    source_file       TEXT,
    extract_date      TEXT,
    captured_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ключ идемпотентности вынесен в выражение-индекс: у контуров участка
-- `part_number` равен NULL, а в SQLite NULL <> NULL, и табличный UNIQUE
-- плодил бы дубли при каждой повторной загрузке той же выписки.
CREATE UNIQUE INDEX IF NOT EXISTS ux_egrn_contour_key
    ON egrn_contour(cad_number, kind, COALESCE(part_number, ''), contour_no);
CREATE INDEX IF NOT EXISTS idx_egrn_contour_cad
    ON egrn_contour(cad_number, kind);
CREATE INDEX IF NOT EXISTS idx_egrn_contour_part
    ON egrn_contour(part_mnemonic) WHERE part_mnemonic IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_egrn_contour_child
    ON egrn_contour(contour_cad) WHERE contour_cad IS NOT NULL;

CREATE VIEW IF NOT EXISTS v_egrn_parcel_contour AS
    SELECT contour_id, cad_number, contour_no, contour_cad, geom_geojson,
           area_computed_sqm, area_declared_sqm, accuracy_m, sk_id, msk_zone,
           centroid_lon, centroid_lat, source, source_extract_number,
           source_file, extract_date, captured_at
      FROM egrn_contour
     WHERE kind = 'parcel';

CREATE VIEW IF NOT EXISTS v_egrn_geometry_summary AS
    SELECT cad_number,
           COUNT(*)                          AS contours,
           SUM(area_computed_sqm)            AS area_computed_sqm,
           MAX(area_declared_sqm)            AS area_declared_sqm,
           MAX(accuracy_m)                   AS accuracy_m,
           MAX(msk_zone)                     AS msk_zone,
           MAX(source_extract_number)        AS source_extract_number,
           MAX(extract_date)                 AS extract_date,
           CASE WHEN MAX(area_declared_sqm) IS NULL THEN NULL
                WHEN ABS(SUM(area_computed_sqm) - MAX(area_declared_sqm))
                     <= MAX(1.0, MAX(area_declared_sqm) * 0.01) THEN 1
                ELSE 0 END                   AS area_check_ok
      FROM egrn_contour
     WHERE kind = 'parcel'
     GROUP BY cad_number;
