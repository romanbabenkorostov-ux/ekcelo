-- ─────────────────────────────────────────────────────────────────────────────
-- db/schema.sql  —  полная схема БД egrn_parser v1.10
-- Исправления v1.10: пропущенные запятые перед object_restrictions,
-- удалено поле right_restrictions (перенесено в отдельные записи right_category='restriction')
-- ─────────────────────────────────────────────────────────────────────────────

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─────────────────────────────────────────────────────────────────────────────
-- АКТИВ: Level 0 — Земельные участки
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_objects (
    cad_number              TEXT PRIMARY KEY,
    inventory_number        TEXT,
    name                    TEXT,             -- «Земельный участок {кад.номер}, {площадь} кв.м»
    quarter_cad_number      TEXT,
    registration_date       TEXT,
    old_numbers             TEXT,             -- JSON: [{"type":"...","number":"..."}]
    address                 TEXT,
    cadastral_value         REAL,
    cadastral_value_date    TEXT,
    lifecycle_status        TEXT NOT NULL DEFAULT 'active',
    lifecycle_status_text   TEXT,
    deregistration_date     TEXT,
    permitted_uses          TEXT,             -- JSON
    area                    REAL,
    area_error              REAL,
    land_category           TEXT,
    nested_objects          TEXT,             -- JSON
    predecessor_cad_numbers TEXT,             -- JSON
    successor_cad_numbers   TEXT,             -- JSON
    transformation_type     TEXT,
    transformation_date     TEXT,
    transformation_basis    TEXT,
    object_restrictions     TEXT,             -- JSON: ст. 56 ЗК, ОКН, ЗОУИТ (ИСПРАВЛЕНА ЗАПЯТАЯ)
    is_primary              INTEGER NOT NULL DEFAULT 1,
    monitored               INTEGER NOT NULL DEFAULT 0,
    data_source             TEXT,
    source_file             TEXT,             -- Имена файлов источников через |
    enrichment_depth        INTEGER NOT NULL DEFAULT 0,
    enriched_at             TEXT,
    content_hash            TEXT,             -- SHA-256 нормализованного содержимого
    graph_node_id           TEXT GENERATED ALWAYS AS ('land_' || cad_number) VIRTUAL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_land_status    ON land_objects(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_land_monitored ON land_objects(monitored) WHERE monitored = 1;

-- ─────────────────────────────────────────────────────────────────────────────
-- АКТИВ: Level 1 — Здания, сооружения, помещения, ОНС
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS building_objects (
    cad_number              TEXT PRIMARY KEY,
    inventory_number        TEXT,
    object_type             TEXT NOT NULL,    -- 'building'|'room'|'structure'|'parking'|'ons'
    quarter_cad_number      TEXT,
    registration_date       TEXT,
    old_numbers             TEXT,             -- JSON
    address                 TEXT,
    cadastral_value         REAL,
    cadastral_value_date    TEXT,
    lifecycle_status        TEXT NOT NULL DEFAULT 'active',
    lifecycle_status_text   TEXT,
    deregistration_date     TEXT,
    permitted_uses          TEXT,             -- JSON; обычно NULL для ОКС
    area                    REAL,
    name                    TEXT,
    purpose                 TEXT,
    purpose_code            INTEGER,
    -- Этажность (v1.10):
    floors_total            INTEGER,          -- по выписке: всего этажей (включая подземные)
    floors_above_ground     INTEGER,          -- без подземных (или вычисляется)
    underground_floors      INTEGER,
    floors_inspection       TEXT,             -- по осмотру (вручную, не парсится)
    condition_inspection    TEXT,             -- состояние по осмотру (вручную, не парсится)
    -- Прочее:
    wall_material           TEXT,
    year_used               INTEGER,
    year_built              INTEGER,
    -- Связи:
    land_cad_numbers        TEXT,             -- JSON; для зданий — ЗУ-носители
    room_type               TEXT,             -- для помещений
    floor                   INTEGER,          -- для помещений
    plan_number             TEXT,             -- для помещений
    parent_cad_number       TEXT,             -- для помещений/ММ
    parent_object_class     TEXT,             -- 'land'|'building'|'structure'|'unknown'
    parent_floors_above_ground INTEGER,       -- подтянуто алгоритмом resolve_room_parent()
    parent_underground_floors  INTEGER,       -- подтянуто от родителя
    -- Сооружения:
    main_char_type          TEXT,
    main_value              REAL,
    main_unit               TEXT,
    -- Трансформации:
    predecessor_cad_numbers TEXT,
    successor_cad_numbers   TEXT,
    transformation_type     TEXT,
    transformation_date     TEXT,
    transformation_basis    TEXT,
    -- Ограничения объекта (актив) (ИСПРАВЛЕНА ЗАПЯТАЯ):
    object_restrictions     TEXT,             -- JSON
    -- Метаданные:
    is_primary              INTEGER NOT NULL DEFAULT 1,
    monitored               INTEGER NOT NULL DEFAULT 0,
    data_source             TEXT,
    source_file             TEXT,             -- Имена файлов через |
    enrichment_depth        INTEGER NOT NULL DEFAULT 0,
    enriched_at             TEXT,
    content_hash            TEXT,
    graph_node_id           TEXT GENERATED ALWAYS AS ('building_' || cad_number) VIRTUAL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bldg_type     ON building_objects(object_type);
CREATE INDEX IF NOT EXISTS idx_bldg_parent   ON building_objects(parent_cad_number) WHERE parent_cad_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bldg_status   ON building_objects(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_bldg_monitored ON building_objects(monitored) WHERE monitored = 1;

-- ─────────────────────────────────────────────────────────────────────────────
-- АКТИВ: Level 2 — Принадлежности и оборудование (из ОСВ)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accessories (
    accessory_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name               TEXT NOT NULL,
    inventory_number        TEXT,
    re_cad_number           TEXT,             -- кадастровый номер объекта-носителя
    re_object_class         TEXT,             -- 'land'|'building'
    cad_number_fragment     TEXT,             -- частичный кад. номер (":119")
    entity_name             TEXT,
    entity_inn              TEXT,
    period_from             TEXT,
    period_to               TEXT,
    account_code            TEXT,             -- '01.01'|'01.К'
    right_category          TEXT,             -- 'right'|'encumbrance'
    right_type              TEXT,             -- 'Собственность'|'Аренда'
    -- Геометрия точечная:
    lat                     REAL,
    lon                     REAL,
    -- Геометрия линейная (v1.10):
    lat2                    REAL,
    lon2                    REAL,
    geom_polyline           TEXT,             -- JSON: [[lat,lon], ...]
    -- Жизненный цикл:
    is_disposed             INTEGER DEFAULT 0,
    disposed_date           TEXT,
    -- Источник:
    source_file             TEXT,
    -- Block 2:
    graph_node_id           TEXT GENERATED ALWAYS AS ('acc_' || accessory_id) VIRTUAL,
    parsed_at               TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_inn, account_code, item_name, inventory_number, period_from)
);
CREATE INDEX IF NOT EXISTS idx_acc_re     ON accessories(re_cad_number);
CREATE INDEX IF NOT EXISTS idx_acc_entity ON accessories(entity_inn);
CREATE INDEX IF NOT EXISTS idx_acc_linear ON accessories(lat2, lon2) WHERE lat2 IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- АКТИВ: Level 3 — Бизнес-единицы
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS business_units (
    unit_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_name               TEXT NOT NULL,
    unit_type               TEXT,
    functional_description  TEXT,
    hierarchy_level         INTEGER NOT NULL DEFAULT 3,
    parent_object_class     TEXT,             -- 'land'|'building'
    parent_cad_number       TEXT,
    status                  TEXT NOT NULL DEFAULT 'own',  -- 'own'|'rent'|'sublease'
    owner_entity_id         INTEGER REFERENCES entity_registry(entity_id),
    tenant_entity_id        INTEGER REFERENCES entity_registry(entity_id),
    right_id                INTEGER REFERENCES rights(right_id),
    area_sqm                REAL,
    floors_occupied         TEXT,
    lat                     REAL,
    lon                     REAL,
    entity_inn              TEXT,             -- ИНН оперирующей организации (Fix 18)
    entity_kpp              TEXT,             -- КПП оперирующей организации (Fix 18)
    graph_node_id           TEXT GENERATED ALWAYS AS ('bu_' || unit_id) VIRTUAL,
    graph_parent_node_id    TEXT,
    graph_owner_entity_id   TEXT,
    data_source             TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(unit_name, parent_cad_number)
);
CREATE INDEX IF NOT EXISTS idx_bu_parent ON business_units(parent_cad_number);
CREATE INDEX IF NOT EXISTS idx_bu_owner  ON business_units(owner_entity_id);
CREATE INDEX IF NOT EXISTS idx_bu_tenant ON business_units(tenant_entity_id);
CREATE INDEX IF NOT EXISTS idx_bu_status ON business_units(status);

-- ─────────────────────────────────────────────────────────────────────────────
-- СТОИМОСТИ
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS valuations (
    valuation_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class            TEXT,
    cad_number              TEXT,
    accessory_id            INTEGER REFERENCES accessories(accessory_id),
    unit_id                 INTEGER REFERENCES business_units(unit_id),
    accessory_name          TEXT,
    inventory_number        TEXT,
    valuation_type          TEXT NOT NULL,
    amount                  REAL NOT NULL,
    vat_amount              REAL,
    currency                TEXT DEFAULT 'RUB',
    doc_date                TEXT,
    recorded_at             TEXT NOT NULL DEFAULT (datetime('now')),
    period_label            TEXT,
    source_file             TEXT,
    source_type             TEXT NOT NULL,
    source_extract_number   TEXT,
    notes                   TEXT
);
CREATE INDEX IF NOT EXISTS idx_val_cad  ON valuations(cad_number);
CREATE INDEX IF NOT EXISTS idx_val_type ON valuations(valuation_type);
CREATE INDEX IF NOT EXISTS idx_val_date ON valuations(doc_date);

-- ─────────────────────────────────────────────────────────────────────────────
-- ИСТОРИЯ: события объектов
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS object_events (
    event_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class            TEXT NOT NULL,
    cad_number              TEXT NOT NULL,
    event_seq               INTEGER NOT NULL,
    event_type              TEXT NOT NULL,
    event_date              TEXT,
    detected_at             TEXT NOT NULL DEFAULT (datetime('now')),
    predecessor_cad_numbers TEXT,
    successor_cad_numbers   TEXT,
    changed_fields          TEXT,            -- JSON: {"field": [old, new]}
    basis_doc_type          TEXT,
    basis_doc_number        TEXT,
    basis_doc_date          TEXT,
    cadastral_engineer      TEXT,
    source_extract_number   TEXT,
    source_format           TEXT,
    notes                   TEXT,
    UNIQUE(cad_number, event_seq)
);
CREATE INDEX IF NOT EXISTS idx_obj_events_cad  ON object_events(cad_number);
CREATE INDEX IF NOT EXISTS idx_obj_events_type ON object_events(event_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- ПАССИВ: Права, обременения, ограничения прав
-- right_category IN ('right', 'encumbrance', 'restriction')
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rights (
    right_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class                TEXT NOT NULL,
    object_key_type             TEXT NOT NULL,   -- 'cad_number'|'inventory_number'
    object_key_value            TEXT NOT NULL,
    right_category              TEXT NOT NULL,   -- 'right'|'encumbrance'|'restriction'
    right_type                  TEXT,
    right_type_code             TEXT,
    right_number                TEXT,
    right_date                  TEXT,
    right_end_date              TEXT,
    right_end_reason            TEXT,
    -- Для ограничений прав:
    restricting_right_id        INTEGER REFERENCES rights(right_id),
    restricting_right_number    TEXT,
    -- Преемственность:
    predecessor_right_number    TEXT,
    successor_right_number      TEXT,
    is_active                   INTEGER NOT NULL DEFAULT 1,
    -- Доли:
    share_numerator             INTEGER,
    share_denominator           INTEGER,
    -- Сроки:
    valid_from                  TEXT,
    valid_until                 TEXT,
    valid_duration_years        INTEGER,
    -- Бенефициар:
    beneficiary_name            TEXT,
    beneficiary_inn             TEXT,
    -- Документы-основания:
    basis                       TEXT,
    -- Аренда:
    lease_term_description      TEXT,
    lease_party_type            TEXT,
    lease_partial               INTEGER DEFAULT 0,
    lease_partial_measure_type  TEXT,
    lease_partial_qty           REAL,
    lease_partial_unit          TEXT,
    -- Сервитут:
    servitude_part_number       TEXT,
    servitude_is_public         INTEGER DEFAULT 0,
    -- Доп. атрибуты:
    personal_participation_req  INTEGER DEFAULT 0,
    claim_records               TEXT,
    -- Источник:
    source_right_category       TEXT,
    source_account_code         TEXT,
    source_extract_number       TEXT,
    source_format               TEXT,
    source_file                 TEXT,             -- Файл-источник (через | при обогащении)
    source_filename             TEXT,             -- имя файла-источника (Fix 29/32)
    -- Временные метки:
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rights_object     ON rights(object_class, object_key_type, object_key_value);
CREATE INDEX IF NOT EXISTS idx_rights_active     ON rights(is_active);
CREATE INDEX IF NOT EXISTS idx_rights_category   ON rights(right_category);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rights_number ON rights(right_number) WHERE right_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rights_restricting ON rights(restricting_right_id) WHERE restricting_right_id IS NOT NULL;
-- Индексы из Приложения B:
CREATE INDEX IF NOT EXISTS idx_rights_object_b   ON rights(object_key_value, is_active);
CREATE INDEX IF NOT EXISTS idx_rights_cat_active ON rights(right_category, is_active);

-- ─────────────────────────────────────────────────────────────────────────────
-- ИСТОРИЯ: события прав
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS right_events (
    event_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    right_id                  INTEGER REFERENCES rights(right_id),
    right_number              TEXT,
    event_seq                 INTEGER NOT NULL,
    event_type                TEXT NOT NULL,
    event_date                TEXT,
    detected_at               TEXT NOT NULL DEFAULT (datetime('now')),
    predecessor_right_number  TEXT,
    successor_right_number    TEXT,
    old_holder_name           TEXT,
    old_holder_inn            TEXT,
    new_holder_name           TEXT,
    new_holder_inn            TEXT,
    changed_fields            TEXT,
    basis_doc_type            TEXT,
    basis_doc_number          TEXT,
    basis_doc_date            TEXT,
    source_extract_number     TEXT,
    source_format             TEXT,
    notes                     TEXT,
    UNIQUE(right_number, event_seq)
);
CREATE INDEX IF NOT EXISTS idx_right_events_right ON right_events(right_number, event_seq);

-- ─────────────────────────────────────────────────────────────────────────────
-- Правообладатели
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS right_holders (
    holder_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    right_id         INTEGER NOT NULL REFERENCES rights(right_id) ON DELETE CASCADE,
    holder_type      TEXT NOT NULL,
    name             TEXT,
    inn              TEXT,
    ogrn             TEXT,
    email            TEXT,
    mailing_address  TEXT,
    entity_id        INTEGER REFERENCES entity_registry(entity_id),
    subject_uuid     TEXT,                   -- Fix 40f: UUID субъекта (для физлиц без ИНН)
    first_seen_file  TEXT                    -- Fix 40f: файл первого обнаружения субъекта
);
CREATE INDEX IF NOT EXISTS idx_right_holders_right ON right_holders(right_id);
CREATE INDEX IF NOT EXISTS idx_rights_holder        ON right_holders(inn);

-- ─────────────────────────────────────────────────────────────────────────────
-- Реестр юридических лиц
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entity_registry (
    entity_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    inn                 TEXT,
    ogrn                TEXT,
    entity_type         TEXT NOT NULL,   -- 'individual'|'legal_entity'|'public_entity'
    name_full           TEXT,
    name_short          TEXT,
    egrul_status        TEXT,
    reg_date            TEXT,
    liquidation_date    TEXT,
    legal_address       TEXT,
    okved_main          TEXT,
    kpp                 TEXT,
    egrul_enriched_at   TEXT,
    group_id            INTEGER REFERENCES company_groups(group_id),
    user_notes          TEXT,
    graph_node_id       TEXT GENERATED ALWAYS AS ('entity_' || COALESCE(inn, 'id' || entity_id)) VIRTUAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(inn)
);
CREATE INDEX IF NOT EXISTS idx_entity_inn   ON entity_registry(inn) WHERE inn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_group ON entity_registry(group_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Группы компаний
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS company_groups (
    group_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name              TEXT NOT NULL UNIQUE,
    group_type              TEXT,
    ultimate_owner          TEXT,
    notes                   TEXT,
    color_hex               TEXT,
    monitor_changes         INTEGER NOT NULL DEFAULT 1,
    monitor_interval_days   INTEGER DEFAULT 7,
    last_monitored_at       TEXT,
    is_group_ultimate       INTEGER NOT NULL DEFAULT 0,
    graph_node_id           TEXT GENERATED ALWAYS AS ('group_' || group_id) VIRTUAL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Цепочки владения
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ownership_chain (
    chain_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    child_entity_id   INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    parent_entity_id  INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    share_pct         REAL,
    source            TEXT NOT NULL,
    source_date       TEXT,
    notes             TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(child_entity_id, parent_entity_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- СЛУЖЕБНЫЕ ТАБЛИЦЫ
-- ─────────────────────────────────────────────────────────────────────────────

-- Реестр выписок
CREATE TABLE IF NOT EXISTS extracts (
    extract_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    extract_number    TEXT NOT NULL UNIQUE,
    extract_date      TEXT,
    object_class      TEXT,
    cad_number        TEXT,
    organ             TEXT,
    recipient         TEXT,
    source_format     TEXT NOT NULL,
    source_filename   TEXT,
    content_hash      TEXT,
    total_sheets      INTEGER,
    total_sections    INTEGER,
    extract_template  TEXT,
    schema_id         INTEGER REFERENCES schema_registry(schema_id),
    parsed_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_extracts_date ON extracts(extract_date);

-- Реестр схем XML
CREATE TABLE IF NOT EXISTS schema_registry (
    schema_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source           TEXT NOT NULL,
    schema_name      TEXT NOT NULL,
    schema_version   TEXT,
    schema_namespace TEXT,
    published_at     TEXT,
    effective_from   TEXT,
    effective_to     TEXT,
    source_url       TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    is_current       INTEGER NOT NULL DEFAULT 1,
    notes            TEXT,
    registered_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, schema_name, schema_version, content_hash)
);

-- Геометрия объектов
CREATE TABLE IF NOT EXISTS object_geometries (
    geom_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class   TEXT NOT NULL,
    cad_number     TEXT NOT NULL,
    geom_type      TEXT NOT NULL,
    geom_source    TEXT NOT NULL,
    geom_geojson   TEXT NOT NULL,
    geom_wkt       TEXT,
    crs            TEXT DEFAULT 'EPSG:4326',
    area_geom_sqm  REAL,
    obtained_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_current     INTEGER NOT NULL DEFAULT 1,
    UNIQUE(cad_number, geom_source)
);
CREATE INDEX IF NOT EXISTS idx_geometries_object ON object_geometries(cad_number);

-- События геометрии
CREATE TABLE IF NOT EXISTS geometry_events (
    event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class          TEXT NOT NULL,
    cad_number            TEXT NOT NULL,
    event_type            TEXT NOT NULL,
    event_date            TEXT,
    detected_at           TEXT NOT NULL DEFAULT (datetime('now')),
    old_area_sqm          REAL,
    new_area_sqm          REAL,
    area_delta_sqm        REAL,
    old_geojson           TEXT,
    new_geojson           TEXT,
    geom_source           TEXT,
    source_extract_number TEXT,
    notes                 TEXT
);

-- Лог обогащения
CREATE TABLE IF NOT EXISTS enrichment_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number          TEXT NOT NULL,
    source_cad_number   TEXT NOT NULL,
    data_source         TEXT NOT NULL,
    attempt_number      INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL,
    http_status_code    INTEGER,
    fields_obtained     TEXT,
    error_message       TEXT,
    requested_at        TEXT NOT NULL DEFAULT (datetime('now')),
    duration_ms         INTEGER
);

-- Связи объектов
CREATE TABLE IF NOT EXISTS linked_objects (
    link_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_cad_number   TEXT NOT NULL,
    primary_object_class TEXT NOT NULL,
    linked_cad_number    TEXT NOT NULL,
    linked_object_class  TEXT NOT NULL,
    link_type            TEXT NOT NULL,
    enrichment_depth     INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(primary_cad_number, linked_cad_number, link_type)
);

-- Лог мониторинга
CREATE TABLE IF NOT EXISTS monitoring_log (
    log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id          INTEGER REFERENCES company_groups(group_id),
    cad_number        TEXT NOT NULL,
    object_class      TEXT NOT NULL,
    check_at          TEXT NOT NULL DEFAULT (datetime('now')),
    status            TEXT NOT NULL,
    events_generated  INTEGER DEFAULT 0,
    changes_summary   TEXT,
    error_message     TEXT
);

-- Словарь кодов (только SQLite, не экспортируется в JSON/graph.json)
CREATE TABLE IF NOT EXISTS code_dictionary (
    dict_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT NOT NULL,
    code          TEXT NOT NULL,
    value_ru      TEXT NOT NULL,
    value_short   TEXT,
    description   TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    source        TEXT,
    UNIQUE(category, code)
);

-- Системные метаданные
CREATE TABLE IF NOT EXISTS system_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO system_meta VALUES ('egrn_parser_version', '1.10');
INSERT OR IGNORE INTO system_meta VALUES ('graph_json_version',  '1.1');
INSERT OR IGNORE INTO system_meta VALUES ('schema_version',      '1.10');
INSERT OR IGNORE INTO system_meta VALUES ('created_at',          datetime('now'));

-- Рекомендованные индексы (Приложение B ТЗ)
CREATE INDEX IF NOT EXISTS idx_object_events_obj  ON object_events(cad_number, event_seq);
CREATE INDEX IF NOT EXISTS idx_right_events_right ON right_events(right_number, event_seq);
CREATE INDEX IF NOT EXISTS idx_accessories_parent ON accessories(re_cad_number);
CREATE INDEX IF NOT EXISTS idx_business_units_par ON business_units(parent_cad_number);

-- Контакты проекта (Fix 14)
CREATE TABLE IF NOT EXISTS contacts (
    contact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role                TEXT NOT NULL,            -- 'Субподряд идентификации' / 'Подряд' / 'Заказ'
    customer_name       TEXT,                     -- Наименование заказчика
    customer_inn        TEXT,
    customer_kpp        TEXT,
    customer_contact    TEXT,                     -- Контактное лицо
    executor_name       TEXT,                     -- Наименование исполнителя
    executor_inn        TEXT,
    executor_kpp        TEXT,
    executor_contact    TEXT,
    contract_number     TEXT,
    contract_date       TEXT,
    act_date            TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Предзаполнение по умолчанию
INSERT OR IGNORE INTO contacts (contact_id, role, executor_contact)
    VALUES (1, 'Субподряд идентификации', 'Бабенко');
INSERT OR IGNORE INTO contacts (contact_id, role)
    VALUES (2, 'Подряд идентификации');
INSERT OR IGNORE INTO contacts (contact_id, role)
    VALUES (3, 'Заказ идентификации');

-- Фотоматериалы объектов (Fix 24)
CREATE TABLE IF NOT EXISTS photos (
    photo_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name       TEXT NOT NULL,
    folder_path     TEXT,
    latitude        REAL,
    longitude       REAL,
    bearing         REAL,             -- Угол съёмки
    altitude        REAL,             -- Высота
    taken_at        TEXT,             -- Дата съёмки (ISO)
    cad_number      TEXT,             -- Кадастровый номер объекта
    source_folder   TEXT,
    parsed_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_name, folder_path)
);
CREATE INDEX IF NOT EXISTS idx_photos_cad ON photos(cad_number);

-- ─────────────────────────────────────────────────────────────────────────────
-- SQL Views для воссоздания досье по кадастровому номеру объекта
-- egrn_parser v1.10 — Fix 37
-- ─────────────────────────────────────────────────────────────────────────────

-- View 1: Единая таблица объектов (ЗУ + ОКС в одном представлении)
CREATE VIEW IF NOT EXISTS v_all_objects AS
SELECT
    cad_number,
    'land'                          AS object_class,
    'Земельный участок'             AS object_type_ru,
    name,
    address,
    area,
    area_error,
    NULL                            AS purpose,
    NULL                            AS floors_total,
    NULL                            AS floors_above_ground,
    NULL                            AS underground_floors,
    NULL                            AS year_built,
    NULL                            AS year_used,
    land_category,
    permitted_uses,
    cadastral_value,
    cadastral_value_date,
    lifecycle_status,
    lifecycle_status_text,
    object_restrictions,
    data_source,
    content_hash,
    updated_at
FROM land_objects
UNION ALL
SELECT
    cad_number,
    'building'                      AS object_class,
    CASE object_type
        WHEN 'building'   THEN 'Здание'
        WHEN 'structure'  THEN 'Сооружение'
        WHEN 'room'       THEN 'Помещение'
        WHEN 'parking'    THEN 'Машино-место'
        WHEN 'ons'        THEN 'ОНС'
        WHEN 'complex'    THEN 'Комплекс'
        ELSE object_type
    END                             AS object_type_ru,
    name,
    address,
    area,
    NULL                            AS area_error,
    purpose,
    floors_total,
    floors_above_ground,
    underground_floors,
    year_built,
    year_used,
    NULL                            AS land_category,
    NULL                            AS permitted_uses,
    cadastral_value,
    cadastral_value_date,
    lifecycle_status,
    lifecycle_status_text,
    object_restrictions,
    data_source,
    content_hash,
    updated_at
FROM building_objects;

-- View 2: Права на объект с правообладателями
CREATE VIEW IF NOT EXISTS v_rights_full AS
SELECT
    r.right_id,
    r.object_key_value              AS cad_number,
    r.right_category,
    r.right_type,
    r.right_type_code,
    r.right_number,
    r.right_date,
    r.share_numerator,
    r.share_denominator,
    CASE
        WHEN r.share_numerator IS NOT NULL
        THEN CAST(r.share_numerator AS TEXT) || '/' || CAST(r.share_denominator AS TEXT)
        ELSE '1/1'
    END                             AS share_str,
    rh.holder_type,
    rh.name                         AS holder_name,
    rh.inn                          AS holder_inn,
    rh.ogrn                         AS holder_ogrn,
    r.beneficiary_name,
    r.beneficiary_inn,
    r.valid_from,
    r.valid_until,
    r.basis,
    r.is_active,
    r.source_extract_number,
    r.source_file
FROM rights r
LEFT JOIN right_holders rh ON rh.right_id = r.right_id;

-- View 3: Все договоры аренды (действующие и прошлые)
CREATE VIEW IF NOT EXISTS v_lease_contracts AS
SELECT
    r.right_number                  AS contract_number,
    r.object_key_value              AS cad_number,
    o.name                          AS object_name,
    o.address,
    o.area,
    rh.name                         AS lessee_name,
    rh.inn                          AS lessee_inn,
    r.right_date                    AS registration_date,
    r.valid_from                    AS lease_start,
    r.valid_until                   AS lease_end,
    r.valid_duration_years          AS duration_years,
    r.lease_term_description,
    r.basis,
    CASE
        WHEN r.valid_until IS NULL OR r.valid_until >= date('now')
        THEN 'Действует'
        ELSE 'Истёк'
    END                             AS status,
    r.source_file,
    r.source_extract_number
FROM rights r
LEFT JOIN right_holders rh ON rh.right_id = r.right_id
LEFT JOIN v_all_objects o  ON o.cad_number = r.object_key_value
WHERE r.right_category = 'encumbrance'
  AND r.right_type_code IN ('lease', 'lease_full', 'servitude')
ORDER BY r.valid_until DESC;

-- View 4: Полное досье по объекту
-- Используется: SELECT * FROM v_object_dossier WHERE cad_number = '90:25:020102:24'
CREATE VIEW IF NOT EXISTS v_object_dossier AS
SELECT
    o.cad_number,
    o.object_class,
    o.object_type_ru,
    o.name,
    o.address,
    o.area,
    o.area_error,
    o.purpose,
    o.floors_above_ground,
    o.underground_floors,
    o.year_built,
    o.land_category,
    o.permitted_uses,
    o.cadastral_value,
    o.lifecycle_status,
    o.lifecycle_status_text,
    -- Собственники (через GROUP_CONCAT)
    (SELECT GROUP_CONCAT(rh.name || COALESCE(' ИНН ' || rh.inn, ''), '; ')
     FROM rights r JOIN right_holders rh ON rh.right_id = r.right_id
     WHERE r.object_key_value = o.cad_number
       AND r.right_category = 'right' AND r.is_active = 1)
                                    AS owners,
    -- Аренды
    (SELECT GROUP_CONCAT(r.right_number, '; ')
     FROM rights r
     WHERE r.object_key_value = o.cad_number
       AND r.right_type_code IN ('lease','lease_full') AND r.is_active = 1)
                                    AS active_leases,
    -- Обременения
    (SELECT COUNT(*) FROM rights r
     WHERE r.object_key_value = o.cad_number AND r.right_category = 'encumbrance' AND r.is_active = 1)
                                    AS encumbrances_count,
    -- Запреты
    (SELECT COUNT(*) FROM rights r
     WHERE r.object_key_value = o.cad_number AND r.right_category = 'restriction' AND r.is_active = 1)
                                    AS restrictions_count,
    -- Ограничения объекта (ЗОУИТ/ОКН)
    (SELECT json_array_length(o2.object_restrictions)
     FROM land_objects o2 WHERE o2.cad_number = o.cad_number
     UNION ALL
     SELECT json_array_length(b.object_restrictions)
     FROM building_objects b WHERE b.cad_number = o.cad_number
     LIMIT 1)                       AS object_restrictions_count,
    -- Последняя выписка
    (SELECT e.extract_number || ' от ' || e.extract_date
     FROM extracts e WHERE e.cad_number = o.cad_number
     ORDER BY e.extract_date DESC LIMIT 1)
                                    AS last_extract,
    -- Балансовая стоимость
    (SELECT v.amount FROM valuations v
     WHERE v.cad_number = o.cad_number AND v.valuation_type = 'initial'
     ORDER BY v.doc_date DESC LIMIT 1)
                                    AS book_value_initial,
    (SELECT v.amount FROM valuations v
     WHERE v.cad_number = o.cad_number AND v.valuation_type = 'residual'
     ORDER BY v.doc_date DESC LIMIT 1)
                                    AS book_value_residual,
    o.object_restrictions           AS object_restrictions_json,
    o.updated_at
FROM v_all_objects o;

-- View 5: Ипотеки/Запреты (обременения без аренды)
CREATE VIEW IF NOT EXISTS v_pledges_prohibitions AS
SELECT
    r.right_number,
    r.object_key_value              AS cad_number,
    o.name                          AS object_name,
    o.address,
    r.right_type,
    r.right_date                    AS registration_date,
    r.valid_until                   AS valid_until,
    r.beneficiary_name,
    r.beneficiary_inn,
    r.basis,
    CASE r.right_category
        WHEN 'encumbrance' THEN 'Обременение'
        WHEN 'restriction' THEN 'Ограничение'
    END                             AS category_ru,
    r.source_file
FROM rights r
LEFT JOIN v_all_objects o ON o.cad_number = r.object_key_value
WHERE r.right_category IN ('encumbrance', 'restriction')
  AND r.right_type_code NOT IN ('lease', 'lease_full')
ORDER BY r.right_date DESC;
