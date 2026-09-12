-- =============================================
-- 0007 — Ручные контуры, разрешение конфликтов и раскладка участка (§9)
-- ADR-008 (obsidian/Decisions/ADR-008-manual-contours-and-conflicts.md).
-- Код: egrn_parser/parsers/manual_contours.py, xml_geometry.py.
-- =============================================
-- ЗАДАЧА. У части объектов контура нет вовсе: кадастровые инженеры до них ещё
-- не дошли, а работать с объектом надо уже сейчас. Экономист обводит участок
-- примерно — по снимку, по забору, по словам собственника. Потом приходит
-- выписка ЕГРН с настоящим контуром.
--
-- ЧТО ЗДЕСЬ НЕЛЬЗЯ СДЕЛАТЬ И ПОЧЕМУ. Соблазн — положить ручной контур в
-- `egrn_contour` со `source='manual'` и потом молча перезаписать выпиской.
-- Так делать нельзя по двум причинам, и обе дорогие:
--
--   1. §8 объявлен ЧАСТЬЮ СЛЕПКА ЕГРН: он воспроизводится из выписок целиком.
--      Ручная обводка из выписки не воспроизводится никогда — попав туда, она
--      ломает базовый инвариант проекта (CLAUDE.md §3, ADR-001), и пересобрать
--      слепок с нуля становится нельзя.
--   2. Молчаливая замена скрывает событие, которое человек обязан увидеть.
--      Ручной контур мог быть согласован с заказчиком, лечь в акт, уехать в
--      отчёт. «Появился уточнённый контур» — это решение, а не техническая
--      деталь: иногда исходный оставляют намеренно.
--
-- РЕШЕНИЕ. Ручные контуры живут своей таблицей (не-ЕГРН слой, как §6 и §7, с
-- `confidence`), а встреча ручного контура с выпиской ЗАПИСЫВАЕТСЯ отдельной
-- строкой конфликта и ждёт решения человека: оставить исходный или заменить на
-- уточнённый. До решения оба контура существуют одновременно, и представление
-- `v_object_contour_current` честно говорит, какой считается текущим.

PRAGMA foreign_keys = ON;

-- ── §9.1 Раскладка участка ──────────────────────────────────────────────────
-- Один кадастровый номер — не обязательно один контур:
--   ЗУ  — обычный участок, один контур;
--   МКУ — многоконтурный участок: несколько контуров, все под одним КН;
--   ЕЗП — единое землепользование: каждый контур сам объект учёта и несёт
--         СВОЙ кадастровый номер обособленного участка (`contour_cad`).
-- Различие не косметическое: у ЕЗП площадь складывается из площадей
-- обособленных участков, каждый из которых можно продать отдельно, а у МКУ
-- контуры неотделимы. Отчёт, который их путает, врёт о предмете сделки.
ALTER TABLE egrn_contour ADD COLUMN land_layout TEXT;

-- ── §9.2 Ручной (примерный) контур ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS manual_contour (
    manual_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number     TEXT NOT NULL,
    contour_no     INTEGER NOT NULL DEFAULT 1,

    geom_geojson   TEXT NOT NULL,             -- Polygon, WGS-84, lon/lat
    crs            TEXT NOT NULL DEFAULT 'EPSG:4326',
    area_computed_sqm REAL,                   -- по координатам, на сфере
    centroid_lon   REAL,
    centroid_lat   REAL,

    -- Чем обводили: 'kml' (Google Earth, Яндекс.Конструктор), 'geojson',
    -- 'nspd' (подложка публичной карты), 'manual'. Строкой, не справочником:
    -- список источников растёт, а CHECK пришлось бы менять миграцией.
    source         TEXT NOT NULL DEFAULT 'kml',
    source_file    TEXT,
    author         TEXT,                      -- кто обвёл; для спора через год
    note           TEXT,                      -- «по забору», «со слов арендатора»

    -- Уверенность обводки: 0.3 — «пальцем по карте», 0.8 — по свежему снимку с
    -- ясными границами. Поле есть именно здесь и намеренно отсутствует в §8:
    -- у выписки Росреестра не уверенность, а заявленная погрешность съёмки.
    confidence     REAL NOT NULL DEFAULT 0.5
                   CHECK (confidence >= 0.0 AND confidence <= 1.0),

    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),

    -- Контур отозван: обводку признали негодной либо заменили выпиской.
    -- Строка НЕ удаляется — на неё мог ссылаться уже подписанный акт.
    retired_at     TEXT,
    retired_reason TEXT
);

-- Идемпотентность повторной загрузки того же файла: (КН, номер контура).
-- Повторный импорт обновляет геометрию, а не плодит копии.
CREATE UNIQUE INDEX IF NOT EXISTS ux_manual_contour_key
    ON manual_contour(cad_number, contour_no);
CREATE INDEX IF NOT EXISTS idx_manual_contour_live
    ON manual_contour(cad_number) WHERE retired_at IS NULL;

-- ── §9.3 Конфликт «ручной контур ↔ контур из выписки» ───────────────────────
-- Строка появляется в момент, когда на объект с живым ручным контуром
-- записывается контур из выписки. Она НЕ решает конфликт — она делает его
-- видимым и ждёт человека.
CREATE TABLE IF NOT EXISTS contour_conflict (
    conflict_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number     TEXT NOT NULL,

    manual_id      INTEGER REFERENCES manual_contour(manual_id),
    egrn_contour_id INTEGER REFERENCES egrn_contour(contour_id),

    -- Площади обоих контуров на момент обнаружения: по ним человек решает, не
    -- глядя в карту. Расхождение в разы — обводка была не про тот объект.
    manual_area_sqm REAL,
    egrn_area_sqm   REAL,

    detected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    source_extract_number TEXT,

    -- 'pending'      — обнаружен, решения нет; текущим остаётся РУЧНОЙ контур.
    --                  Умолчание именно такое: молча подменить контур, который
    --                  уже мог уйти в акт, хуже, чем показать расхождение.
    -- 'use_egrn'     — заменить на уточнённый; ручной уходит в retired.
    -- 'keep_manual'  — оставить исходный; контур из выписки остаётся в §8
    --                  (слепок ЕГРН не трогаем), но текущим не считается.
    resolution     TEXT NOT NULL DEFAULT 'pending'
                   CHECK (resolution IN ('pending', 'use_egrn', 'keep_manual')),
    resolved_at    TEXT,
    resolved_by    TEXT,
    resolution_note TEXT
);

-- Один открытый конфликт на объект: повторный разбор той же выписки не должен
-- плодить строки, а новая выписка по уже решённому объекту — заводит новую.
CREATE UNIQUE INDEX IF NOT EXISTS ux_contour_conflict_open
    ON contour_conflict(cad_number) WHERE resolution = 'pending';
CREATE INDEX IF NOT EXISTS idx_contour_conflict_cad
    ON contour_conflict(cad_number, detected_at);

-- ── §9.4 Какой контур считать текущим ───────────────────────────────────────
-- Единственное место, отвечающее на этот вопрос. Логика словами:
--   • есть контур ЕГРН и (ручного нет ИЛИ конфликт решён как 'use_egrn'
--     ИЛИ ручной отозван) → текущий из выписки;
--   • иначе есть живой ручной → текущий ручной (в том числе пока конфликт
--     висит в 'pending' — см. §9.3 про умолчание);
--   • иначе объект без геометрии.
CREATE VIEW IF NOT EXISTS v_object_contour_current AS
    SELECT e.cad_number,
           'egrn'                AS contour_source,
           e.contour_no,
           e.geom_geojson,
           e.area_computed_sqm,
           e.accuracy_m,
           NULL                  AS confidence,
           e.land_layout,
           e.source_extract_number,
           e.extract_date
      FROM egrn_contour e
     WHERE e.kind = 'parcel'
       AND NOT EXISTS (
           SELECT 1 FROM manual_contour m
            WHERE m.cad_number = e.cad_number AND m.retired_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM contour_conflict c
                   WHERE c.cad_number = e.cad_number AND c.resolution = 'use_egrn'))
    UNION ALL
    SELECT m.cad_number,
           'manual'              AS contour_source,
           m.contour_no,
           m.geom_geojson,
           m.area_computed_sqm,
           NULL                  AS accuracy_m,
           m.confidence,
           NULL                  AS land_layout,
           NULL                  AS source_extract_number,
           NULL                  AS extract_date
      FROM manual_contour m
     WHERE m.retired_at IS NULL
       AND NOT EXISTS (
           SELECT 1 FROM contour_conflict c
            WHERE c.cad_number = m.cad_number AND c.resolution = 'use_egrn');

-- ── §9.5 Что требует решения человека ───────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_contour_conflicts_open AS
    SELECT c.conflict_id, c.cad_number, c.manual_area_sqm, c.egrn_area_sqm,
           ROUND(c.egrn_area_sqm - c.manual_area_sqm, 1) AS delta_sqm,
           c.detected_at, c.source_extract_number,
           m.author, m.note, m.confidence, m.source AS manual_source
      FROM contour_conflict c
      LEFT JOIN manual_contour m ON m.manual_id = c.manual_id
     WHERE c.resolution = 'pending'
     ORDER BY c.detected_at DESC;
