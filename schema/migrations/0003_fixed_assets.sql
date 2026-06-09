-- =============================================
-- 0003 — Реестр основных средств (ОС/техника) из ОСВ
-- ADR-006 §G. Источник: оборотно-сальдовая ведомость (1С), счета 01.x.
-- Счёт 01.08 — ОКС, права не оформлены (НЕ на кадастровом учёте) → on_cadastre=0.
-- Парсер: egrn_parser/parsers/osv_assets.py
-- =============================================

CREATE TABLE IF NOT EXISTS fixed_asset (
    asset_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    account      TEXT,                       -- 01.01 (ОС), 01.08 (ОКС без прав) …
    cost         REAL,                       -- суммарная стоимость (сальдо)
    qty          REAL,
    units        INTEGER,                    -- число строк ОСВ (единиц) по позиции
    on_cadastre  INTEGER NOT NULL DEFAULT 1, -- 0 для 01.08 (права не оформлены)
    cad_number   TEXT,                       -- если ОКС поставлен на кадастр
    osv_period   TEXT,                       -- период ОСВ (напр. '2025')
    source       TEXT NOT NULL DEFAULT 'osv',
    source_file  TEXT,
    content_hash TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, account, osv_period)
);
CREATE INDEX IF NOT EXISTS idx_fixed_asset_account   ON fixed_asset(account);
CREATE INDEX IF NOT EXISTS idx_fixed_asset_oncad     ON fixed_asset(on_cadastre);
