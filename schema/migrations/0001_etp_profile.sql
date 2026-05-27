-- =============================================
-- Migration 0001 — ETP Profile
-- =============================================
-- Добавляет три таблицы для экспорта объектов сюрвея в ЭТП:
--   object_etp_profile  — гэп-поля для развёрнутого описания лота
--   lots                — группа КН = единица экспорта в ЭТП
--   lot_items           — many-to-many лот ↔ КН
--
-- ВАЖНО: это слой «НЕ-ЕГРН» (см. ADR-001). Поля заполняются ОСВ-листом
-- экономиста, парсером EXIF фото, NSPD или LLM. Принцип CLAUDE.md §3
-- переформулирован: «БД = слепок ЕГРН + ЭТП-профиль».
--
-- Источник правды формата:
--   docs/etp_export/SPEC_etp_export.md §3, §5
--   obsidian/Decisions/ADR-001-etp-profile-extension.md
--   docs/CORRESPONDENCE/025, 026
--
-- Связь с CONTRACT_KMZ.md: НЕ затрагивается (§3 UI/UX-домен).
-- lots.lot_id формат совместим с graph_node_id из CONTRACT_KMZ §6 —
-- позволяет viewer Phase 2 overlay переиспользовать S5-инфраструктуру.
-- =============================================

PRAGMA foreign_keys = ON;

-- =============================================
-- object_etp_profile
-- =============================================
-- Хранит гэп-поля для одного КН. JSON-колонки позволяют расширять
-- структуру без новых миграций (SPEC §5 решение).
CREATE TABLE IF NOT EXISTS object_etp_profile (
    cad_number      TEXT PRIMARY KEY
                        REFERENCES objects(cad_number) ON DELETE CASCADE,
    location_extra  TEXT,                        -- JSON: {landmark, transport_access, environment_short}
    building_extra  TEXT,                        -- JSON: {renovation_year, wear_degree, engineering{}, amenities[]}
    layout          TEXT,                        -- JSON: {layout_type, ceiling_height_m, finish_level, finish_state, windows, entry_group, current_condition_comment}
    legal_extra     TEXT,                        -- JSON: {use_type_fact, zoning, special_restrictions[]}
    risks           TEXT,                        -- JSON: {technical_risks[], legal_risks[], location_risks[], other_risks[]}
    extras          TEXT,                        -- JSON: {furniture, advantages[], notes}
    source          TEXT NOT NULL
                        CHECK (source IN ('osv', 'exif', 'manual', 'nspd', 'llm')),
    confidence      REAL NOT NULL
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- =============================================
-- lots
-- =============================================
-- Лот = единица экспорта в ЭТП. Группа КН с общим описанием, процедурой
-- и платформами-получателями.
--
-- lots.lot_id формат: [A-Za-z0-9_:/-]+, длина 1..256.
-- Совместим с graph_node_id из CONTRACT_KMZ.md §6 — viewer Phase 2 overlay
-- (бейдж лота на маркере объекта + цвет границы по lot_id) переиспользует
-- S5 group-overlay инфраструктуру без bump'а контракта (CORRESPONDENCE/026).
-- Рекомендуемый шаблон: lot:<project_slug>:<NNN>  (напр. lot:pirushin:001).
CREATE TABLE IF NOT EXISTS lots (
    lot_id            TEXT PRIMARY KEY
                        CHECK (
                            length(lot_id) BETWEEN 1 AND 256
                            AND lot_id NOT GLOB '*[^A-Za-z0-9_:/-]*'
                        ),
    name              TEXT NOT NULL,
    platform_targets  TEXT,                       -- JSON array: ["torgi.gov.ru", "roseltorg.ru", "sberbank-ast.ru"]
    procedure_type    TEXT,                       -- "приватизации" | "реализации имущества должника..." | "коммерческая продажа"
    deal_type         TEXT
                        CHECK (deal_type IS NULL OR deal_type IN ('sale', 'lease', 'other')),
    primary_cad_number TEXT
                        REFERENCES objects(cad_number) ON DELETE SET NULL,
    notes_md          TEXT,                       -- ручные пометки экономиста
    created_at        TEXT DEFAULT (datetime('now'))
);

-- =============================================
-- lot_items
-- =============================================
-- Many-to-many: какие КН входят в лот и в каких ролях.
CREATE TABLE IF NOT EXISTS lot_items (
    lot_id      TEXT NOT NULL
                    REFERENCES lots(lot_id) ON DELETE CASCADE,
    cad_number  TEXT NOT NULL
                    REFERENCES objects(cad_number) ON DELETE CASCADE,
    role        TEXT NOT NULL
                    CHECK (role IN ('building', 'land', 'room', 'equipment', 'structure')),
    ord         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (lot_id, cad_number)
);

-- =============================================
-- Индексы
-- =============================================
CREATE INDEX IF NOT EXISTS idx_etp_profile_source ON object_etp_profile(source);
CREATE INDEX IF NOT EXISTS idx_lots_primary ON lots(primary_cad_number);
CREATE INDEX IF NOT EXISTS idx_lot_items_cad ON lot_items(cad_number);
