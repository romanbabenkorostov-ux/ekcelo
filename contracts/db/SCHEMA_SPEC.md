# C2 — SCHEMA_SPEC (табличная БД EKCELO, объединённая)

> Каноника C2. Источник истины — этот файл + `contracts/db/models.py` (SQLAlchemy).
> `schema/egrn_current_schema.sql` остаётся как ЕГРН-DDL §1–§6 и становится
> подмножеством этой схемы (генерируется/мигрируется через Alembic).
> Версия: **0.2** · Дата: 2026-06-04 · Согласовать с C1 (KMZ), C4 (ViewModel), C5 (Lot).
> Статус: **реализовано** — ORM (`models.py` §7–§12, `models_egrn.py` §1–§6), миграции
> Alembic `0001..0003`, импортёр Block-2 (`import_block2.py`), граф-эмиттер
> (`graph_emit.py`), сид `relation_types` — проверено на SQLite (см. §10).

## 0. Принципы (зафиксированы ответами 1–24)

1. **Слоистость, а не замена (ответ 1, ADR-001).** §1–§5 = слепок ЕГРН — остаются как
   высокодоверенный источник. Граф знаний (Entity/Relation/Assertion/Evidence) ложится
   **сверху**: ЕГРН-факты проецируются в `evidences(source='EGRN', weight=1.0)`. БД
   пересоздаётся из выписок → §1–§5 и производные от них Assertions восстанавливаются;
   §6 (ЭТП) и ручные Assertions — нет.
2. **Логический граф (ответ 2).** Узлы/рёбра — таблицы (`entities`, `relations`),
   graph.html и ViewModel C4 рендерят их как есть. Отдельный движок (Neo4j) не вводим;
   обход — рекурсивные CTE / вьюхи. Узлы **выводимы из табличной модели**.
3. **Идентичность (ответы 3,4).** Внутренний PK — `UUID` (`Uuid` SQLAlchemy: native на
   PG, CHAR(32) на SQLite). Натуральные ключи — `cad_number` (unique), `inn/ogrn/kpp`
   (атрибуты с историей). `graph_node_id TEXT` — стабильный человекочитаемый адрес узла
   (паттерн C1 `^[A-Za-z0-9_:/-]{1,256}$`; UUID ему удовлетворяет).
4. **Битемпоральность везде (ответ 14).** Изменяемые таблицы фактов и `relations`/
   `assertions` несут `valid_from/valid_to` (реальное время) + `recorded_at/superseded_at`
   (системное). Справочники — без. Лот тянет срез по `as_of_date`.
5. **Домены связей (ответ 5).** `relations.domain ∈ {legal, tech, spatial, accounting, commercial}`
   + 1:1 расширения. Запрещено смешивать ownership и topology в одном ребре (правило из
   `разделение графовых доменов.md` §15).
6. **Провенанс (ответы 16,19,20).** Истина вероятностная: `assertions.confidence_score`
   пересчитывается из `evidences`. Competing assertions хранятся все; активная = max(confidence),
   tie-break `recorded_at`; ручной override асесора помечается.
7. **Переносимость (SQLite↔PG).** JSON = `JSON().with_variant(JSONB,'postgresql')`
   (JSON1 на SQLite). Геометрия — переносимый WKT/GeoJSON + `srid`; PostGIS — опц. на PG.
8. **ADR-P03.** `innogrn.db`(checko) / `nma.db`(ФИПС) — отдельные БД. Связь — таблица-мост
   `subject_external_ref` по ИНН/ОГРН. НЕ уплощаем.

---

## 1. Карта секций

| § | Слой | Статус | Таблицы |
|---|------|--------|---------|
| 1–5 | **ЕГРН-слепок** | ✅ ORM `models_egrn.py` / mig `0002` | `objects`, `entity_registry`*, `rights`, `extracts`, `object_restrictions` |
| 6 | **ЭТП-профиль** | ✅ ORM `models_egrn.py` / mig `0002` | `object_etp_profile`, `lots`, `lot_items` |
| 7 | **Граф знаний** | ✅ ORM `models.py` / mig `0001` | `entities`, `relations`, `legal_relation`, `tech_relation`, `spatial_relation`, `accounting_relation`, `assertions`, `evidences` |
| 8 | **Геометрия** | ✅ mig `0001` | `geometries` |
| 9 | **Технологический** | ✅ mig `0001` | `devices`, `flow_events` |
| 10 | **Субъекты+** | ✅ mig `0001` (надстройка над `entity_registry`) | `subjects`, `subject_names`, `subject_kpp`, `bank_accounts`, `ip_status_periods`, `subject_external_ref` |
| 11 | **Коммерческий** | ✅ mig `0001` | `lot_snapshots`, `orders`, `contracts`, `invoices`, `upd_documents` |
| 12 | **Документы** | ✅ mig `0001` | `documents`, `doc_links` |

\* `entity_registry` сохраняется ради совместимости §3 `rights.right_holder_inn`; `subjects`
— его надстройка (1:1 по `inn`), куда переезжают тип/НДС/история. Миграция — мягкая.

---

## 2. §7 Граф знаний (ядро)

### 2.1 `entities` — реестр узлов (логический граф)
Тонкий слой адресации: любой объект системы, попадающий в граф, имеет строку здесь.

| поле | тип | назначение |
|------|-----|-----------|
| `id` | UUID PK | внутренний |
| `graph_node_id` | TEXT UNIQUE | C1-адрес узла (`land:61:44:..:31`, `subj:inn:6164...`, UUID и т.п.) |
| `kind` | ENUM `entity_kind` | land/building/room/structure/ons/bu/equipment/device/**accessory**/right/encumbrance/beneficiary_legal/beneficiary_person/state_body/level/doc/lot/order/business_asset/flow_node/demarcation_point |
| `ref_table` | TEXT | на какую таблицу-владельца ссылается (`objects`,`subjects`,`devices`,`documents`,…) |
| `ref_pk` | TEXT | PK строки-владельца (cad_number / uuid / inn) |
| `label` | TEXT | отображаемое имя |
| `cad_number` | TEXT NULL | денорм. якорь (для объектов) |

`kind` — надмножество `viewmodel.schema.json#/$defs/graphNode.kind` (добавлены
`device, state_body, flow_node, demarcation_point, business_asset, lot, order`). Согласовать C4.

### 2.2 `relations` — рёбра (базовая, битемпоральная)

| поле | тип | назначение |
|------|-----|-----------|
| `id` | UUID PK | |
| `from_entity_id` | UUID FK→entities | |
| `to_entity_id` | UUID FK→entities | |
| `relation_type_id` | INT FK→relation_types | справочник |
| `domain` | ENUM `relation_domain` | legal/tech/spatial/accounting/commercial |
| `valid_from`,`valid_to` | DATE NULL | реальное время (Since/Until) |
| `recorded_at` | TIMESTAMP | системное (KnownSince) |
| `superseded_at` | TIMESTAMP NULL | системное (KnownUntil) |
| `meta` | JSON | прочее |

`relation_types(id, code, name, domain, category)` — справочник. `category ∈ {right, encumbrance,
restriction, **corporate**, topology, flow, accounting, commercial}` (ответ 6: права и обременения не
смешиваем на уровне типа). `corporate` (домен `legal`) — бенефициарные цепочки `CONTROLS/FOUNDER_OF/
MANAGES/BRANCH_OF` (решение от 2026-06-04, см. `PARSER_VOCAB_MAP.md §3`). Стартовый сид всех типов —
`relation_types_seed.py` (30 кодов, все рёбра парсеров замаплены).

**Коды (стартовые):**
- legal/right: `OWNS, LEASES, OPERATES(*гос), SERVITUDE, GRATUITOUS_USE`
- legal/encumbrance: `MORTGAGED_BY, ARRESTED_BY`
- legal/restriction: `RESTRICTED_BY` (СЗЗ, ВОЗ, ОКН)
- spatial/topology: `LOCATED_ON, INSIDE, INTERSECTS, ADJACENT_TO`
- tech/flow: `MOVED_TO, FEEDS, TRANSFORMS_TO, CONNECTED_TO`
- accounting: `ON_BALANCE_OF, LEASED_IN_BALANCE, CAPITALIZED_BY`
- commercial: `INCLUDED_IN_LOT, SUBJECT_OF_ORDER, GROUPS(БА)`
- doc-связи: `ESTABLISHES`(правоустан.), `EVIDENCES`, `DEPICTS`(фото)
- subject-связи: `FOUNDER_OF, MANAGES, BRANCH_OF`

### 2.3 Доменные расширения (1:1 к `relations`)
- `legal_relation(relation_id PK FK, legal_document_id, registration_number, registry_source, right_type_code)`
- `tech_relation(relation_id PK, material_type_in, material_type_out, max_throughput, conversion_ratio, loss_factor)` — ответ 10
- `spatial_relation(relation_id PK, spatial_operator, geometry_id)`
- `accounting_relation(relation_id PK, subject_id, account_number, accounting_basis, osv_document_id)` — ответ 6: `ON_BALANCE_OF`/`LEASED_IN_BALANCE`, отделено от legal-`OWNS`/`LEASES`. Допускается `legal_owner ≠ balance_holder`.

### 2.4 `assertions` / `evidences` (вероятностная истина, ответы 16,19,20)
- `assertions(id, relation_id FK, confidence_score FLOAT, status ENUM{active,superseded,disputed,rejected}, asserted_by, asserted_at, valid_from/to, recorded_at/superseded_at)`
- `evidences(id, assertion_id FK, source_type ENUM, document_id FK→documents NULL, weight FLOAT, extracted_data JSON)`

**Шкала весов (ответ 19, поправка):**
```
EGRN = 1.0   COURT_DECISION = 1.0   OSV = 0.8   NSPD = 0.6   EXIF = 0.5   SURVEY_MANUAL = 0.3
EGRUL / EGRIP  → НЕ доказывают OWNS объекта; питают атрибуты Subject и FOUNDER_OF/MANAGES.
```
`confidence_score = f(weights)` (рекоменд. `1 - Π(1 - wᵢ)` по согласным, минус штраф за конфликт).

---

## 3. §8 Геометрия (ответ 12)

`geometries(id, entity_id FK→entities, cad_number NULL, geometry_type{POINT,LINESTRING,POLYGON,MULTIPOLYGON},
coordinates_wkt TEXT, geojson JSON, bbox JSON{minx,miny,maxx,maxy}, original_srid INT, srid INT default 4326,
source_type, confidence, valid_from/to, recorded_at/superseded_at)`

- **МСК-61 → WGS-84(4326)** обязательно для KMZ (C1). `original_srid` хранит исходную СК выписки.
- В графе геометрия НЕ лежит — только `geometries.bbox` для быстрого поиска (правило §15 вложения).

---

## 4. §9 Технологический слой (ответы 7–10 описания)

- `devices(id, entity_id, device_type{scale,flowmeter,level_sensor,tracker}, serial, located_entity_id FK→entities, geo_point JSON, valid_from/to, recorded_at/superseded_at)` — КИП как ОС.
- `flow_events(id, relation_id FK→relations[tech], device_id FK→devices NULL, document_id NULL, timestamp, quantity, unit, event_type{DISCRETE,CONTINUOUS,CORRECTION}, details JSON)`.
- **Telemetry (сырьё) — вне проекта** (TSDB). В граф попадают только `flow_events`-агрегаты.
- `max_capacity` — JSON-свойство узла-накопителя в `entities.meta` или отд. колонка `devices`;
  `current_level` **НЕ хранится** — считается из `flow_events` (поправка A5).

---

## 5. §10 Субъекты (ответы 4,15,18)

- `subjects(id UUID, subject_type ENUM{INDIVIDUAL,LEGAL_ENTITY,INDIVIDUAL_ENTREPRENEUR,STATE_BODY},
  inn UNIQUE NULL, ogrn NULL, name_current, vat_mode{OSNO,USN,USN_VAT}, vat_rate, vat_exemption_reason)`.
  **Роли (бенефициар/асесор/админ) — НЕ тип** (поправка A2); роль — через C6/`relations`/отд. таблицу ролей.
- `subject_names(subject_id, name_full, name_short, valid_from, valid_to)` — ЮЛ меняет имя при 1 ИНН.
- `kpp` — множественный: `subject_kpp(subject_id, kpp, is_main, valid_from, valid_to)` (обособленные подразделения).
- `bank_accounts(id, subject_id, bank_name, bik(9), corr_account(20), settlement_account(20), opened_at, closed_at NULL)` — нормализовано (для УПД).
- `ip_status_periods(id, subject_id, ogrnip, registered_at, terminated_at NULL)` — статус ИП может повторяться.
- `subject_external_ref(subject_id, external_db{innogrn,nma}, external_key{inn/ogrn})` — мост ADR-P03.

ИНН: ЮЛ=10, ФЛ/ИП=12; ОГРН=13, ОГРНИП=15 — валидация по `subject_type`.

---

## 6. §11 Коммерческий слой (ответы 16,17,18)

- **Живой лот** — существующие `lots`/`lot_items` (§6) + `lots.as_of_date`, `include_json`, `exclude_json` (C5).
- `lot_snapshots(id, lot_id, snapshot_at, frozen_data JSON, xsd_version, reason{contract_signed,invoice_issued})` —
  неизменяемый слепок состава. **Печатные формы / УПД-XML / сюрвей-презы — только из снапшота** (ответ 16).
- `orders(id, lot_id, customer_subject_id, assessor_subject_id, status, created_at)`.
- `contracts(id, order_id, number, date, executor_subject_id, customer_subject_id, tz_json, lot_snapshot_id, body_url)`.
- `invoices(id, contract_id, number, date, amount, vat_amount, status)`.
- `upd_documents(id, contract_id, number, date, status{1,2}, xml_url, xsd_version, validated_bool)` —
  **правило (ответ 18):** `supplier.vat_mode='USN_VAT' ⇒ status=1`. Реформа УСН-2025 (доход >60 млн ₽ → НДС 5/7/20) учтена в `vat_rate`.

---

## 7. §12 Документы и классификатор (ответы 21–23)

- `documents(id, doc_type, number, issue_date, issuer, file_url, content_hash, srid NULL, classifier_json, source_type, confidence, parsed_at)`.
  Document = одновременно строка здесь и узел `entities(kind='doc')`.
- `doc_links(id, document_id, target_entity_id, target_table, target_field, relation_code{ESTABLISHES,EVIDENCES,DEPICTS}, source_type, confidence)` —
  материализует «документ → какие сущности/поля обогащает». Полная карта — `DOC_CLASSIFIER_SPEC.md`.

---

## 8. DIFF к `schema/egrn_current_schema.sql` (что нового)

**Новые таблицы:** `entities, relation_types, relations, legal_relation, tech_relation, spatial_relation,
accounting_relation, assertions, evidences, geometries, devices, flow_events, subjects, subject_names,
subject_kpp, bank_accounts, ip_status_periods, subject_external_ref, lot_snapshots, orders, contracts,
invoices, upd_documents, documents, doc_links`.

**Новые поля к существующим:**
- `objects`: `+ parent_cad_number, + quarter_cad_number, + inventory_number, + conditional_number, + cadastral_value, + okato, + kladr, + fias_guid, + status_egrn` (всё есть в ЕГРН-XML, сейчас теряется).
- `objects` (помещение): `+ floor, + floor_type` (есть `location_in_build/level` в XML).
- `rights`: `+ valid_from, valid_to, recorded_at, superseded_at` (битемпоральность), `+ basis_document_id`.
- `lots`: `+ as_of_date, + include_json, + exclude_json` (C5; сейчас нет).
- `entity_registry`: надстройка `subjects` (тип/НДС/история выносятся туда).

**Поля документов, которых нет в схеме, но их парсят/использует graph/KMZ** (из хендоффа + XML):
`old_numbers(инвентарный/условный)`, `parent/quarter cad`, `okato/kladr/fias`, `cadastral_value`,
`floor/level z`, `permitted_use[]`, `purpose code/value`, `right_holder.email/mailing`, контуры WKT (МСК-61),
`structure.json`: BU→уровни→оборудование+высоты z, EXIF gps фото, ОСВ счета `01.01/01.03/01.К`.

---

## 9. Маппинг 4 характеристик EKCELO (C4) → таблицы

| Характеристика | ViewModel facet | Источник в схеме |
|----------------|-----------------|------------------|
| ЧТО (physical) | `physical` | `objects` + `object_etp_profile` + `devices` |
| ЧЬЁ (ownership) | `ownership` | `relations[legal]` + `assertions/evidences` + `subjects` |
| ГДЕ (geo) | `geo` | `geometries` (WKT/bbox, 4326) |
| КОГДА (temporal) | `temporal` | битемпоральные поля + `extracts.extract_date` + `lots.as_of_date` |

---

## 10. Реализация (что собрано и проверено)

| Артефакт | Файл | Статус |
|----------|------|--------|
| ORM §7–§12 | `contracts/db/models.py` | ✅ (+`EntityKind.accessory`) |
| ORM §1–§6 | `contracts/db/models_egrn.py` | ✅ порт `egrn_current_schema.sql` |
| Сид типов рёбер | `contracts/db/relation_types_seed.py` | ✅ 30 кодов |
| Миграции | `contracts/db/migrations/0001..0003` | ✅ upgrade/downgrade на SQLite |
| Импорт Block-2 | `contracts/db/import_block2.py` | ✅ + pytest |
| Граф-эмиттер | `contracts/db/graph_emit.py` | ✅ + pytest |
| Сверка с парсерами | `contracts/db/PARSER_VOCAB_MAP.md` | ✅ |

`0001` = §7–§12 (25 таблиц); `0002` = §1–§6 (8 таблиц); `0003` = enum `accessory`
(PG `ALTER TYPE`, SQLite no-op). Полный стек: **33 таблицы**.

## 11. Проекция лота в KMZ/сюрвей-презу (через снапшот)

Единица компоновки `.kmz` — **`LotSnapshot`** (неизменяемый слепок §11), не «живой»
лот. Алгоритм проекции `LotSnapshot → подграф → KMZ`:

1. **Подграф лота.** Из `frozen_data` берём `entities`, входящие в лот, + инцидентные
   `relations` (на дату снапшота: `valid_from ≤ as_of < valid_to AND superseded_at IS NULL`).
2. **Названия узлов.** `entity.label`; для объектов — имя + КН; геометрия — из
   `geometries` (WKT/GeoJSON, МСК-61 → 4326 для KMZ, C1).
3. **Значения связей в подписи рёбер.** В KMZ `ExtendedData` / label ребра выносятся
   `relations.meta` (доля, № права, `since/until`) **и `confidence`** активного assertion.
   Подпись = «`<роль>` · `<значение>` · `conf=<…>`».
4. **Обезличивание третьих сторон (экспортный слой, C6).** В хранилище субъект реален
   (ИНН/имя). На выгрузке наружу `beneficiary_*` третьих сторон заменяются **ролью из
   ребра** (`relation_types.code` → роль: `OWNS`→Собственник, `LEASES`→Арендатор,
   `SERVITUDE`→Сервитуарий, `MORTGAGED_BY`→Залогодержатель, `CONTROLS`→Контролирующее лицо).
   Владелец лота себя видит; обезличивание контекстно по роли получателя.
5. **Документы — на дату.** Узел `doc` подписывается `тип + issue_date`; ребро,
   которое документ `ESTABLISHES`, имеет `valid_from = issue_date`.

Реализация — отдельный композер `lot_to_kmz.py` (роль-подмена + подписи рёбер поверх
`graph_emit`); план — этап 2 (см. `c2-roadmap-next.md`).
