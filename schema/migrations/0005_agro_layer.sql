-- =============================================
-- 0005 — Агро-слой: поля, циклы культур, события, словарь признаков
-- ADR-006 §A (agro_parcel), §I (agro_crop_cycle), §C (agro_event + словарь).
-- §6 (не-ЕГРН): источник — техкарта/ОСВ/EXIF/NSPD/LLM; при пересоздании БД из
-- выписок ЕГРН НЕ восстанавливается. Все строки несут source + confidence.
-- Парсеры: egrn_parser/parsers/{techcard,osv_assets}.py (техкарта — ожидается).
-- =============================================

-- ── §A. Поле как самостоятельная единица (снимок на сезон) ───────────────────
-- Геометрия/площадь/код поля экономиста (уч.519). Что и когда на нём растёт —
-- в agro_crop_cycle (§I). Мягкая привязка к земле (ADR-005) опциональна.
CREATE TABLE IF NOT EXISTS agro_parcel (
    parcel_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_code   TEXT NOT NULL,             -- «уч.519» (нумерация экономиста)
    season_year   INTEGER NOT NULL,          -- сезон-снимок границ/площади поля
    area_ha       REAL,                      -- площадь, га
    -- мягкая привязка к земле (может отсутствовать / меняться по сезонам):
    land_cad      TEXT,                      -- КН родителя (ЗУ/ЕЗП/МКУ), опц.
    contour_no    INTEGER,                   -- № контура (ADR-005 land_contours), опц.
    geom_geojson  TEXT,                      -- геометрия поля сезона, опц.
    lot_id        TEXT,                      -- принадлежность лоту, опц.
    attrs         TEXT,                      -- JSON: прочие признаки поля
    source        TEXT NOT NULL CHECK (source IN ('osv','techcard','exif','manual','nspd','llm','perechen')),
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    updated_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(parcel_code, season_year)
);
CREATE INDEX IF NOT EXISTS idx_agro_parcel_season ON agro_parcel(season_year);
CREATE INDEX IF NOT EXISTS idx_agro_parcel_land   ON agro_parcel(land_cad, contour_no);

-- ── §I. Цикл культуры (sow→harvest), пересекает сезоны; план/факт строками ────
-- Озимая: сев год N → уборка N+1; season_year = ГОД УБОРКИ (ось агрегаций урожая).
-- План≠факт: отдельные строки crop_status + датировка §F (valid_from/known_from).
CREATE TABLE IF NOT EXISTS agro_crop_cycle (
    cycle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id     INTEGER NOT NULL REFERENCES agro_parcel(parcel_id),
    cycle_kind    TEXT NOT NULL CHECK (cycle_kind IN ('winter','spring','perennial')),
    crop          TEXT,                      -- культура (озимая пшеница, виноград)
    variety       TEXT,                      -- сорт («Одесский Чёрный»)
    sow_date      TEXT,                      -- дата сева/закладки (озимая → год N)
    harvest_date  TEXT,                      -- плановая/фактич. уборка (озимая → N+1)
    season_year   INTEGER NOT NULL,          -- ГОД УБОРКИ
    agro_season   TEXT,                      -- человекочит. метка «2024/2025» | «2025»
    crop_status   TEXT NOT NULL CHECK (crop_status IN ('plan','fact')),
    -- датировка §F (план→факт без перезаписи истории):
    valid_from    TEXT,                      -- с какой даты назначение действует
    valid_to      TEXT,                      -- по какую (NULL = открыт)
    known_from    TEXT,                      -- с какой даты стало известно
    source        TEXT NOT NULL CHECK (source IN ('osv','techcard','exif','manual','nspd','llm','perechen')),
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cycle_parcel ON agro_crop_cycle(parcel_id, season_year);
CREATE INDEX IF NOT EXISTS idx_cycle_status ON agro_crop_cycle(crop_status, valid_from);

-- ── §C. Лог событий поля (harvest|treatment|observation|phenology|sowing) ─────
-- Показатели события — в JSON attrs (профили в ADR §C), не колонками.
-- asset_id (§G) — техника из ОСВ; cycle_id (§I) — привязка к циклу (план/факт).
CREATE TABLE IF NOT EXISTS agro_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id   INTEGER NOT NULL REFERENCES agro_parcel(parcel_id),
    cycle_id    INTEGER REFERENCES agro_crop_cycle(cycle_id),
    season_year INTEGER NOT NULL,            -- денормализованная ось отчётов
    event_type  TEXT NOT NULL,               -- harvest|treatment|observation|phenology|sowing
    event_date  TEXT,                        -- дата (сбор/обработка/замер/сев)
    asset_id    INTEGER REFERENCES fixed_asset(asset_id),  -- техника (§G), опц.
    attrs       TEXT NOT NULL,               -- JSON: показатели события (профиль по type)
    source      TEXT NOT NULL CHECK (source IN ('osv','techcard','exif','manual','nspd','llm','perechen')),
    confidence  REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agro_event_parcel ON agro_event(parcel_id, season_year);
CREATE INDEX IF NOT EXISTS idx_agro_event_cycle  ON agro_event(cycle_id);
CREATE INDEX IF NOT EXISTS idx_agro_event_type   ON agro_event(event_type, event_date);

-- ── §C/§H. Словарь отслеживаемых признаков (группировки без миграций) ─────────
CREATE TABLE IF NOT EXISTS agro_attribute_dict (
    attr_key    TEXT PRIMARY KEY,            -- 'acidity_g_l','active_substance','variety'…
    label       TEXT NOT NULL,
    unit        TEXT,
    value_type  TEXT,                        -- number|text|date|enum
    groupable   INTEGER NOT NULL DEFAULT 1,  -- 1 = ось группировки в отчётах
    json_path   TEXT                         -- где лежит в attrs ('$.active_substances[*].name')
);

-- §H. Стартовый словарь (не пересекается с профилями событий §C).
INSERT OR IGNORE INTO agro_attribute_dict (attr_key, label, unit, value_type, groupable, json_path) VALUES
    ('crop',          'Культура',          NULL,   'text',   1, NULL),
    ('variety',       'Сорт',              NULL,   'text',   1, NULL),
    ('planting_date', 'Дата закладки/сева', NULL,  'date',   0, NULL),
    ('planting_year', 'Год закладки/сева', NULL,   'number', 1, NULL),
    ('seeding_rate',  'Норма высева',      'ед/га', 'number', 0, NULL);
