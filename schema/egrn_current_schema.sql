-- =============================================
-- EKCELO — EGRN Parser Current Schema
-- Актуальная структура БД парсера ЕГРН (v1.10+)
-- Единый источник правды для Python + Frontend
-- Дата: 2026-05-12
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