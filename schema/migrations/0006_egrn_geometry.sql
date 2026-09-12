-- =============================================
-- 0006 — Геометрия из XML-выписок ЕГРН (§8)
-- ADR-007 (obsidian/Decisions/ADR-007-msk-to-wgs84.md).
-- Парсер: egrn_parser/parsers/xml_geometry.py (извлечение),
--         egrn_parser/parsers/xml_geometry_db.py (запись).
-- =============================================
-- ЧЕМ ЭТОТ СЛОЙ ОТЛИЧАЕТСЯ ОТ ВСЕГО ОСТАЛЬНОГО ГЕО В БАЗЕ.
--
-- §7 (geo_entity, ADR-002) — не-ЕГРН слой: ручная обводка, KMZ, НСПД, LLM. Он
-- живёт своей жизнью, имеет source+confidence и при пересоздании БД из выписок
-- НЕ восстанавливается.
--
-- §8 — ровно наоборот: это СЛЕПОК ЕГРН (CLAUDE.md §3, ADR-001 §1..§5). Каждая
-- строка здесь выведена из XML-выписки, подписанной ЭП Роскадастра, и при
-- пересоздании БД из тех же выписок воспроизводится побайтово. Поэтому
-- confidence тут нет: у документа Росреестра нет «уверенности», у него есть
-- заявленная погрешность съёмки (`accuracy_m`), и это другая величина.
--
-- Слои намеренно не сливаются в одну таблицу: смешать «что сказал Росреестр» и
-- «что мы сами обвели по снимку» — значит потерять возможность пересобрать
-- слепок ЕГРН с нуля, а это базовый инвариант проекта.
--
-- ПОЧЕМУ КОНТУР — СТРОКА, А НЕ ПОЛЕ MULTIPOLYGON. У многоконтурного участка
-- контуры различаются номером (`number_pp`), у ЕЗП — собственными кадастровыми
-- номерами, у частей (ЧЗУ) — номером части и мнемоникой зоны. Свёрнутые в один
-- MultiPolygon, все эти признаки теряются, а именно они и нужны: в KML каждый
-- контур становится отдельным Placemark со своей подписью.
--
-- ПОЧЕМУ ЧЗУ ЛЕЖАТ ЗДЕСЬ ЖЕ, А НЕ ОТДЕЛЬНОЙ ТАБЛИЦЕЙ. Структура строки у части
-- и у контура участка совпадает полностью (кольца, площадь, точность,
-- источник); различает их `kind`. Вторая таблица с теми же колонками означала
-- бы два места правки на каждое изменение формата. Но складывать их площади
-- нельзя ни при каких условиях: ЧЗУ лежит ВНУТРИ участка (охранная зона ЛЭП,
-- водоохранная полоса), и сумма даёт площадь лота больше фактической. Отсюда
-- жёсткое правило: всякая агрегация площади фильтрует по `kind='parcel'` —
-- для этого и заведено представление `v_egrn_parcel_contour`.
-- =============================================

PRAGMA foreign_keys = ON;

-- ── §8.1 Контур объекта по данным выписки ───────────────────────────────────
CREATE TABLE IF NOT EXISTS egrn_contour (
    contour_id        INTEGER PRIMARY KEY AUTOINCREMENT,

    -- КН объекта, ИЗ ВЫПИСКИ НА КОТОРЫЙ взят контур. Для ЧЗУ это КН участка,
    -- а не номер зоны: часть не является самостоятельным объектом учёта.
    cad_number        TEXT NOT NULL,

    -- 'parcel' — контур самого участка; 'part' — контур части (ЧЗУ).
    -- См. преамбулу: складывать их площади нельзя.
    kind              TEXT NOT NULL CHECK (kind IN ('parcel', 'part')),

    -- Порядковый номер контура в пределах (cad_number, kind, part_number).
    -- У однконтурного участка равен 1; у многоконтурного и ЕЗП — 1..N.
    contour_no        INTEGER NOT NULL,

    -- Кадастровый номер обособленного участка — заполнен только у ЕЗП,
    -- где каждый контур сам является объектом учёта (ADR-005).
    contour_cad       TEXT,

    -- Часть участка: номер («1», «2») и мнемоника зоны («26:29-6.395-ЧЗУ1»).
    -- По мнемонике строка связывается с object_restrictions.registry_number —
    -- так у ограничения появляется геометрия, а у контура смысл.
    part_number       TEXT,
    part_mnemonic     TEXT,

    -- GeoJSON Geometry (Polygon) в WGS-84, координаты lon,lat. Внешнее кольцо
    -- первым, далее дырки — как их отдаёт выписка: другого признака
    -- «внешнее/внутреннее» в XML нет, значим порядок spatial_element.
    geom_geojson      TEXT NOT NULL,
    crs               TEXT NOT NULL DEFAULT 'EPSG:4326',

    -- Площадь, вычисленная по координатам в метрах МСК (до пересчёта), и
    -- площадь, заявленная в той же выписке. Хранятся ОБЕ намеренно: их
    -- расхождение — единственная проверка, которую парсер может выполнить без
    -- внешних источников, и она ловит неверные параметры зоны МСК. Стереть
    -- одну из них — значит лишить базу возможности себя перепроверить.
    area_computed_sqm REAL,
    area_declared_sqm REAL,

    -- Заявленная погрешность положения точек (delta_geopoint): 0.1 м у свежей
    -- съёмки, 2.5 м у пересчёта из старых материалов. Это характеристика
    -- документа, а не наша оценка — потому не confidence.
    accuracy_m        REAL,

    -- Исходная система координат как её написал Росреестр («МСК-26 от СК-95,
    -- зона 1») и ключ зоны в реестре msk.MSK_ZONES («мск-26-з1»). Написание
    -- sk_id не нормировано и гуляет между выписками, поэтому хранится и то и
    -- другое: строка — чтобы было видно первоисточник, ключ — чтобы искать.
    sk_id             TEXT,
    msk_zone          TEXT,

    centroid_lon      REAL,
    centroid_lat      REAL,

    -- 'egrn_xml' сейчас; поле оставлено строкой на случай 'egrn_pdf'.
    source            TEXT NOT NULL DEFAULT 'egrn_xml',
    -- Номер выписки (КУВИ-001/...) и имя файла — чтобы через год ответить на
    -- вопрос «откуда эта граница» не догадкой, а ссылкой на документ.
    source_extract_number TEXT,
    source_file       TEXT,
    extract_date      TEXT,
    captured_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Идемпотентность повторного разбора той же выписки. Ключ вынесен в
-- ВЫРАЖЕНИЕ-индекс, а не в табличный UNIQUE, по конкретной причине: у контуров
-- участка `part_number` равен NULL, а в SQLite NULL не равен NULL — табличный
-- UNIQUE их не склеил бы, и каждая повторная загрузка той же выписки плодила бы
-- дубли контуров. COALESCE(part_number,'') снимает это.
CREATE UNIQUE INDEX IF NOT EXISTS ux_egrn_contour_key
    ON egrn_contour(cad_number, kind, COALESCE(part_number, ''), contour_no);

CREATE INDEX IF NOT EXISTS idx_egrn_contour_cad
    ON egrn_contour(cad_number, kind);
CREATE INDEX IF NOT EXISTS idx_egrn_contour_part
    ON egrn_contour(part_mnemonic) WHERE part_mnemonic IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_egrn_contour_child
    ON egrn_contour(contour_cad) WHERE contour_cad IS NOT NULL;

-- ── §8.2 Контуры самого участка ─────────────────────────────────────────────
-- Представление существует ровно затем, чтобы «SUM(area)» нельзя было написать
-- случайно по всей таблице и получить площадь лота с двойным учётом ЧЗУ.
CREATE VIEW IF NOT EXISTS v_egrn_parcel_contour AS
    SELECT contour_id, cad_number, contour_no, contour_cad, geom_geojson,
           area_computed_sqm, area_declared_sqm, accuracy_m, sk_id, msk_zone,
           centroid_lon, centroid_lat, source, source_extract_number,
           source_file, extract_date, captured_at
      FROM egrn_contour
     WHERE kind = 'parcel';

-- ── §8.3 Сводка по объекту ──────────────────────────────────────────────────
-- Что показывать в карточке и чем гейтить экспорт в KML: сходится ли площадь
-- по контурам с заявленной. Допуск (1% либо 1 м²) повторяет
-- xml_geometry.AREA_TOLERANCE_* — при изменении менять оба места.
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
