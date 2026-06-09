# ADR-006 (proposed): Агро-слой — поля (agro_parcel), сезонность, урожай и обработки

**Статус:** Proposed · **Дата:** 2026-06-08 · **Автор:** parser-team
**Связанные:** [[ADR-005-zu-ezp-mku-contours-and-tech]] (уточняет §D), [[ADR-001-etp-profile-extension]]
**Развилки (ответы заказчика, 2026-06-08):** agro_parcel отдельной сущностью;
время = сезон-снимок + год закладки; хранение = события + JSON-атрибуты;
объём итерации = только проект (ADR+spec).

## Контекст

Технологическая (агрономическая) часть лота богаче, чем «свойство на контур»
(ADR-005 §D). Требования заказчика:

- Поля/участки экономиста (**уч.519, уч.714**) **не совпадают** с кадастровыми
  контурами; у поля могут быть вложенные контуры, может не быть контуров, а
  границы/посадки **меняются каждый сезон**.
- Культуры **однолетние и многолетние** (виноград с **годом закладки**), напр.
  «Виноград уч.519 "Одесский Чёрный" 2021 г. — 4,06 га», «уч.714 "Мерло" 2022 г.
  — 11,39 га».
- Нужно вести **урожай по сортам, срокам сбора** (разная кислотность/сахар),
  **обработки** с количеством разных **действующих веществ** в разные даты,
  **по полям**. Множество отслеживаемых признаков с **группировкой**.

Это §6 (не-ЕГРН, ADR-001): источник — техкарта/ОСВ экономиста, EXIF, NSPD, LLM;
поля `source`+`confidence`; при пересоздании БД из выписок НЕ восстанавливается.

## Решение (предложение)

### A. `agro_parcel` — поле как самостоятельная единица (сезонная)

Независимо от кадастра; своя нумерация (уч.519). Снимок на сезон.

```sql
CREATE TABLE agro_parcel (
    parcel_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_code   TEXT NOT NULL,         -- «уч.519» (нумерация экономиста)
    season_year   INTEGER NOT NULL,      -- сезон-снимок (граница/посадка года)
    crop          TEXT,                  -- культура (виноград)
    variety       TEXT,                  -- сорт («Одесский Чёрный»)
    lifecycle     TEXT CHECK (lifecycle IN ('annual','perennial')),
    planting_year INTEGER,               -- год закладки (для многолетних)
    area_ha       REAL,                  -- площадь, га (4.06)
    -- мягкая привязка к земле (может отсутствовать / меняться):
    land_cad      TEXT,                  -- КН родителя (ЗУ/ЕЗП/МКУ), опц.
    contour_no    INTEGER,               -- № контура (ADR-005 land_contours), опц.
    geom_geojson  TEXT,                  -- геометрия поля сезона, опц.
    lot_id        TEXT,                  -- принадлежность лоту, опц.
    attrs         TEXT,                  -- JSON: прочие признаки поля
    source        TEXT NOT NULL CHECK (source IN ('osv','techcard','exif','manual','nspd','llm')),
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    updated_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(parcel_code, season_year)
);
```

«Контуры меняются каждый сезон» → новая строка на `(parcel_code, season_year)`.
Многолетник (виноград) — `lifecycle='perennial'`, `planting_year=2021`, при этом
строки на каждый сезон с актуальной площадью/состоянием.

### B. Время

- **season_year** — основной разрез снимков и агрегаций (урожай по годам).
- **planting_year** — отдельно для многолетних (возраст насаждений).
- valid_from/valid_to НЕ вводим (отклонено в пользу простоты, см. ответы).

### C. События + гибкие атрибуты (JSON)

Единый лог событий поля; тип + дата + сезон + произвольные показатели в JSON.

```sql
CREATE TABLE agro_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id   INTEGER NOT NULL REFERENCES agro_parcel(parcel_id),
    season_year INTEGER NOT NULL,
    event_type  TEXT NOT NULL,        -- harvest | treatment | observation | phenology
    event_date  TEXT,                 -- дата (сбор/обработка/замер)
    attrs       TEXT NOT NULL,        -- JSON: показатели события (см. ниже)
    source      TEXT NOT NULL,
    confidence  REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_agro_event_parcel ON agro_event(parcel_id, season_year);
CREATE INDEX idx_agro_event_type   ON agro_event(event_type, event_date);
```

Профили `attrs` по типам (валидируются JSON-схемой, не колонками):
- **harvest:** `{variety, volume_kg, acidity_g_l, sugar_brix, grade, pass_no}`
  (несколько сборов = несколько событий, разная кислотность → отдельные записи).
- **treatment:** `{kind, preparation, active_substances:[{name, rate, unit}],
  target, machinery}` (разные действующие вещества и нормы по датам).
- **observation/phenology:** `{phase, note, measures:{...}}`.

**Словарь признаков для группировки** — чтобы «заложить множество отслеживаемых
признаков с группировкой» без миграций:

```sql
CREATE TABLE agro_attribute_dict (
    attr_key     TEXT PRIMARY KEY,     -- 'acidity_g_l','active_substance','variety'…
    label        TEXT NOT NULL,
    unit         TEXT,
    value_type   TEXT,                 -- number|text|date|enum
    groupable     INTEGER NOT NULL DEFAULT 1,
    json_path    TEXT                  -- где лежит в attrs (напр. '$.active_substances[*].name')
);
```

### D. Группировки и техсхема лота (агрегаты-вьюхи)

Поверх `agro_parcel`/`agro_event` — представления (логический слой, как граф):
- **Урожай лота по сортам/сезонам:** Σ `harvest.volume_kg` group by `variety`,
  `season_year` (+ по `parcel_code`/полю).
- **Сроки сбора и кислотность:** harvest-события по `event_date`, `acidity_g_l`.
- **Пестицидная нагрузка:** разворот `active_substances[]` → Σ `rate` group by
  `active_substance`, `event_date`/период, поле.
- **Техсхема лота:** `agro_parcel` за `season_year` лота → «виноград: Одесский
  Чёрный 4.06 га (уч.519, закладка 2021), Мерло 11.39 га (уч.714, закладка 2022)».

Группировка управляется `agro_attribute_dict` (любой `groupable` признак —
ось группировки в отчёте/ViewModel).

### E. Связь с землёй (ADR-005)

`agro_parcel.land_cad`/`contour_no` — **мягкая** ссылка (может отсутствовать или
меняться по сезонам). Это уточняет ADR-005 §D: вместо жёсткого
`contour_tech_profile` (на контур) — независимый агро-слой, привязка опциональна.

## Источник данных и ingest

- Первичный — **техкарта/ОСВ экономиста** (Excel/таблица): уч., сорт, год закладки,
  га, обработки, сборы. Парсер техкарты → `agro_parcel` + `agro_event`
  (`source='techcard'|'osv'`). EXIF фото поля, NSPD-контур, LLM — gap-fill.
- Идемпотентность: `UNIQUE(parcel_code, season_year)`; события — по
  (parcel, type, date, ключевой attr).

## Что делать заказчику (next, твои шаги)

1. **Подтвердить модель** A–E (или поправить названия полей под свою практику).
2. **Дать 1 образец техкарты/ОСВ** (обезличенный) в `fixtures/agro/` — по нему
   напишу парсер техкарты и golden-тест (как делали для ЕГРЮЛ/PDF).
3. **Список отслеживаемых признаков** (стартовый `agro_attribute_dict`): какие
   показатели сбора (кислотность, сахар, °Brix?), какие действующие вещества/нормы,
   какие фенофазы — чтобы зафиксировать словарь и единицы.
4. Указать **единицы**: урожай (кг/т/ц), площадь (га), нормы (л/га, кг/га).
5. Решить **привязку к лоту**: поля задаются на лот напрямую или через землю
   (КН/контур) лота.

## Альтернативы (rejected)

- **contour_tech_profile на кадастровый контур (ADR-005 §D).** Не учитывает
  несовпадение полей и контуров и сезонную смену границ. Заменено `agro_parcel`.
- **Фиксированные колонки harvest/treatment.** Новые признаки = миграции;
  выбран events+JSON + словарь (расширяемо).
- **Темпоральные valid_from/valid_to.** Сложнее агрегаций по годам; выбран
  сезон-снимок.

## Последствия

- ✅ Поля независимы от кадастра, сезонность и многолетники учтены.
- ✅ Любой признак отслеживается и группируется без миграций (events+JSON+словарь).
- ✅ Урожай/обработки/кислотность — по сортам, датам, полям; техсхема лота = агрегат.
- ⚠️ JSON-attrs требуют JSON-схем профилей и валидации при ingest.
- ⚠️ Агро-слой §6 — не из ЕГРН; источник техкарты/ОСВ нужно стандартизировать.
- ⚠️ Реализация — отдельная итерация (эта = только проект); согласовать с
  граф-схемой соседнего чата (`contracts/db`).

## Уточнения v2 (2026-06-08, по обратной связи заказчика)

### F. Эффективное датирование (вместо чистого сезон-снимка)

«У сезона нет жёсткой даты начала; параметры существуют/устанавливаются/
заканчиваются/становятся известными с некоторой даты.» → у строк
`agro_parcel`/`agro_event` добавляем датировку **периода действия и знания**:

```sql
ALTER TABLE agro_parcel ADD valid_from   TEXT;   -- с какой даты параметр действует
ALTER TABLE agro_parcel ADD valid_to     TEXT;   -- по какую (NULL = открыт)
ALTER TABLE agro_parcel ADD known_from   TEXT;   -- с какой даты стало известно
```
`season_year` остаётся осью агрегаций; `valid_from/valid_to/known_from` —
точное датирование (для midseason-изменений и «узнали задним числом»). Гибрид
сезон-снимок + интервалы (это уточняет ответ «сезон-снимок»).

### G. Основные средства (техника) из ОСВ — `fixed_asset`

`agro_event` (обработка/сбор) может выполняться **техникой из ОСВ**. Заводим
реестр ОС, наполняемый парсером ОСВ:

```sql
CREATE TABLE fixed_asset (
    asset_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,        -- Субконто (напр. «FANCY, Насос FZ 32-200…»)
    account      TEXT,                 -- счёт ОСВ: 01.01 (ОС), 01.08 (ОКС без прав)…
    cost         REAL,                 -- стоимость (сальдо)
    qty          REAL,
    on_cadastre  INTEGER NOT NULL DEFAULT 1,  -- 0 для 01.08 (ОКС, права не оформлены)
    cad_number   TEXT,                 -- если ОКС поставлен на кадастр
    osv_period   TEXT,                 -- период ОСВ
    source       TEXT NOT NULL DEFAULT 'osv',
    source_file  TEXT,
    content_hash TEXT,
    UNIQUE(name, account, osv_period)
);
ALTER TABLE agro_event ADD asset_id INTEGER REFERENCES fixed_asset(asset_id);
```

**ОКС на счёте 01.08** — объекты, права собственности на которые ещё не
оформлены (не на кадастровом учёте): `on_cadastre=0`, `cad_number=NULL`. Это мост
к ADR-005: такой ОКС — кандидат на постановку на учёт; при оформлении заполняется
`cad_number` и связывается с `building_objects`.

### H. Словарь признаков (стартовый, не пересекается с другими)

`agro_attribute_dict` стартово: `crop` (культура), `variety` (сорт / название
сорта), `planting_date`/`planting_year` (дата/год закладки/посева),
`seeding_rate` (норма высева, ед/га). Остальное (кислотность, сахар,
действующие вещества) — уже в профилях событий §C.

### I. Цикл культуры через сезоны + план/факт (уточняет B и F) — DECIDED (2026-06-08)

Обратная связь заказчика (2026-06-08): **«озимая пшеница засеивается в одном
сезоне, а собирается в следующем; яровая — в одном. При бороновании осенью под
одну культуру может измениться влагообеспеченность и плановая культура весной
следующего года.»**

Два следствия, которые ломают чистый `season_year`:

1. **Цикл культуры пересекает календарные годы.** Озимая: сев осенью года N →
   уборка лето N+1 (агро-сезон «N/N+1»). Яровая: сев весной N → уборка осень N
   (год N). `season_year` сам по себе не отличает «сев 2024» от «уборка 2025» в
   одном цикле. Нужен **цикл** с `sow_date`/`harvest_date` и видом
   `winter|spring|perennial`; агрегации урожая идут по **сезону уборки**, а
   операции (сев, боронование) — по своим датам внутри цикла.

2. **План ≠ факт во времени.** Плановая культура задаётся осенью (под зябь/
   боронование), но к весне может смениться (влагообеспеченность). Это ровно
   случай §F: назначение культуры — это запись со `status (plan|fact)` и
   датировкой `valid_from`/`known_from`. Осенняя строка `status='plan'`
   `valid_from=осень N`; при пересмотре весной — новая строка `status='fact'`
   `valid_from=весна N+1`, старая закрывается `valid_to`. Историю «что
   планировали → что посеяли» видно без перезаписи.

**Решения заказчика (2026-06-08):** (а) **отдельная сущность `agro_crop_cycle`**
(sow→harvest), события ссылаются на `cycle_id`; (б) **`season_year` = год уборки
(N+1)** — ось агрегаций урожая; (в) **план/факт — отдельными строками**
`crop_status (plan|fact)` + датировка §F (без перезаписи).

```sql
CREATE TABLE agro_crop_cycle (
    cycle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id     INTEGER NOT NULL REFERENCES agro_parcel(parcel_id),
    cycle_kind    TEXT NOT NULL CHECK (cycle_kind IN ('winter','spring','perennial')),
    crop          TEXT,                  -- культура цикла (озимая пшеница)
    variety       TEXT,                  -- сорт
    sow_date      TEXT,                  -- дата сева (озимая → год N)
    harvest_date  TEXT,                  -- плановая/фактич. уборка (озимая → N+1)
    season_year   INTEGER NOT NULL,      -- ГОД УБОРКИ (ось агрегаций урожая)
    agro_season   TEXT,                  -- человекочит. метка «2024/2025» | «2025»
    crop_status   TEXT NOT NULL CHECK (crop_status IN ('plan','fact')),
    -- датировка §F (план→факт без перезаписи):
    valid_from    TEXT,                  -- с какой даты назначение действует
    valid_to      TEXT,                  -- по какую (NULL = открыт)
    known_from    TEXT,                  -- с какой даты стало известно
    source        TEXT NOT NULL CHECK (source IN ('osv','techcard','exif','manual','nspd','llm')),
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_cycle_parcel ON agro_crop_cycle(parcel_id, season_year);
CREATE INDEX idx_cycle_status ON agro_crop_cycle(crop_status, valid_from);

ALTER TABLE agro_event ADD cycle_id INTEGER REFERENCES agro_crop_cycle(cycle_id);
```

**Следствия для модели:**
- `crop`/`variety`/`lifecycle`/`planting_year` **переезжают** из `agro_parcel` в
  `agro_crop_cycle` (parcel = геометрия/площадь/код поля по сезону; cycle = что и
  когда на нём растёт). Многолетник (виноград): `cycle_kind='perennial'`,
  `sow_date`=год закладки, один длинный цикл с сезонными `agro_event`-сборами.
- **Озимая (пример):** строка `crop_status='plan'` (`sow_date=2024-10`,
  `season_year=2025`, `valid_from=2024-09`); при смене культуры весной — новая
  строка `crop_status='fact'` (`valid_from=2025-03`), у плановой `valid_to=2025-03`.
  Боронование осенью — `agro_event(cycle_id=plan-строка, event_type='treatment',
  event_date=2024-10)`.
- **Урожай:** Σ `harvest` group by `season_year` (= год уборки) — озимая и яровая
  одного года уборки складываются корректно. `sow_date` фиксирует трансграничность,
  `agro_season` — человекочитаемая метка цикла.

## Что реализуемо сейчас vs заблокировано

- ✅ **`fixed_asset` + парсер ОСВ** — образец ОСВ есть (`fixtures/agro/`/реальный).
  Реализуется сразу: ОСВ.xlsx → `fixed_asset` (счета, техника, 01.08-ОКС).
- ⏳ **`agro_parcel`/`agro_event` ingest** — нужен образец **техкарты** (его нет).
  Схема спроектирована; наполнение — по получении образца техкарты.

## Дальнейшие шаги (план реализации)
1. ✅ Миграция `0003_fixed_assets.sql` + парсер ОСВ → `fixed_asset` (счета 01.x,
   01.08-ОКС). `osv_assets.py` + тест.
2. ✅ Миграция `0005_agro_layer.sql` (agro_parcel/**agro_crop_cycle** (§I)/
   agro_event/agro_attribute_dict + датирование F, связь `asset_id`/`cycle_id`).
3. ⏳ **ТЕХДОЛГ — парсер техкарты** → `agro_parcel`+`agro_crop_cycle`+`agro_event`
   (заблокирован: нужен обезличенный образец техкарты в `fixtures/agro/`).
   Заглушка `agro_techcard.py` + ТЗ `fixtures/agro/TZ_techcard.md`.
4. ✅ JSON-профили `attrs` + валидатор (`agro_event_profiles.py`,
   `validate_event_attrs`: harvest/treatment/observation/phenology/sowing).
5. ⏳ Вьюхи-агрегаты (урожай по сортам/датам/полям, пест. нагрузка, техсхема лота)
   — **после п.3** (нужны данные техкарты).
6. ◻️ Связь с ADR-005 (`land_cad`/`contour_no`; ОКС 01.08 → постановка на учёт).

См. сводный план остатка: `obsidian/Architecture/roadmap-land-agro-graph.md`.
