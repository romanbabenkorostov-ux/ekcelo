# БД: таблицы ЭТП-профиля

> Подробная схема трёх таблиц, добавленных миграцией `schema/migrations/0001_etp_profile.sql`.

Этот документ — справочник по полям. Архитектурный обзор: `obsidian/Architecture/etp-exporter.md`. Решение: `obsidian/Decisions/ADR-001-etp-profile-extension.md`.

## Принцип

«БД = слепок ЕГРН + ЭТП-профиль» (`CLAUDE.md` §3). Эти три таблицы — **не-ЕГРН** слой. При пересоздании БД из выписок ЕГРН **не восстанавливаются**.

---

## `object_etp_profile`

Гэп-поля развёрнутого описания на ЭТП. Заполняется ОСВ-листом экономиста, парсером EXIF фото, NSPD или LLM.

```sql
CREATE TABLE object_etp_profile (
  cad_number      TEXT PRIMARY KEY REFERENCES objects(cad_number) ON DELETE CASCADE,
  location_extra  TEXT,                        -- JSON
  building_extra  TEXT,                        -- JSON
  layout          TEXT,                        -- JSON
  legal_extra     TEXT,                        -- JSON
  risks           TEXT,                        -- JSON
  extras          TEXT,                        -- JSON
  source          TEXT NOT NULL CHECK (source IN ('osv','exif','manual','nspd','llm')),
  confidence      REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
  updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_etp_profile_source ON object_etp_profile(source);
```

### JSON-колонки

| Колонка | Поля внутри | Из чего собирается |
|---|---|---|
| `location_extra` | `landmark`, `transport_access`, `environment_short` | ОСВ-лист + EXIF notes |
| `building_extra` | `renovation_year`, `wear_degree`, `engineering{electricity, water, sewerage, heating, gas, telecom}`, `amenities[]` | ОСВ + NSPD |
| `layout` | `layout_type`, `rooms_count`, `ceiling_height_m`, `finish_level`, `finish_state`, `windows`, `entry_group`, `current_condition_comment` | ОСВ + EXIF photos |
| `legal_extra` | `use_type_fact`, `zoning`, `special_restrictions[]` | NSPD + ОСВ |
| `risks` | `technical_risks[]`, `legal_risks[]`, `location_risks[]`, `other_risks[]` | ОСВ + автоэкстракт из `documents.json` (план) |
| `extras` | `equipment[]`, `furniture`, `advantages[]`, `notes` | ОСВ + EXIF UserComment notes |

### `source` / `confidence`

`source` показывает происхождение всей записи:

| Значение | Источник | confidence | Приоритет |
|---|---|---|---|
| `osv` | ОСВ-лист экономиста | `1.0` | высший |
| `manual` | Ручная правка через будущий редактор `admin/etp-profile/<cad>` | `1.0` | равен `osv` |
| `nspd` | NSPD-enrichment | `0.5..0.9` | средний |
| `exif` | Парсер EXIF UserComment из фото объекта | `0.6..0.9` | средний |
| `llm` | LLM-suggest (Gemini и т.п.) | `< 0.5` обычно | низший |

**Гранулярность:** на текущей фазе `source/confidence` — одна пара на всю запись. Если потребуется per-field маркировка (в одной записи `landmark` ручной, а `wear_degree` из LLM), нужен будет вложенный формат `{value, source, confidence}` — отдельный bump схемы.

### Visual conventions у viewer (Phase 1)

| confidence | Бейдж | Текст приглушён? |
|---|---|---|
| `1.0` | зелёный | нет |
| `0.5..0.99` | жёлтый | нет |
| `< 0.5` | оранжевый | **да** (`opacity:0.55`) |

---

## `lots`

Лот = единица экспорта в ЭТП. Группа КН с общими процедурой, описанием и набором платформ.

```sql
CREATE TABLE lots (
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
CREATE INDEX idx_lots_primary ON lots(primary_cad_number);
```

### Поля

| Поле | Тип | Примеры |
|---|---|---|
| `lot_id` | `[A-Za-z0-9_:/-]+`, ≤256 | `lot:pirushin:001`, `lot:sosna-rocha:042` |
| `name` | свободный текст | «Имущественный комплекс «Пирушин-Центр»: офис + участок» |
| `platform_targets` | JSON array | `["torgi.gov.ru", "sberbank-ast.ru"]` |
| `procedure_type` | строка | «реализации имущества должника в рамках дела о банкротстве», «приватизации», «коммерческая продажа» |
| `deal_type` | enum | `sale` \| `lease` \| `other` \| `NULL` |
| `primary_cad_number` | FK на `objects` | КН-анкер для `identity`-секции описания. SET NULL при удалении объекта (сохраняем `notes_md`). |
| `notes_md` | Markdown | Ручные пометки экономиста — высший приоритет при бэкапах. |

### Формат `lot_id`

Совместим с `graph_node_id` из `CONTRACT_KMZ §6` (`[A-Za-z0-9_:/-]+`, ≤256). Это позволяет viewer Phase 2 переиспользовать S5 group-overlay инфру без bump'а контракта (см. CORRESPONDENCE/026 🕸 заметку).

Рекомендуемый шаблон: `lot:<project_slug>:<NNN>`. Альтернативно: `lot_<project_slug>_<NNN>` (тоже валиден).

### Каскады

- `DELETE FROM lots WHERE lot_id = ?` → cascade удаление всех `lot_items` этого лота.
- `DELETE FROM objects WHERE cad_number = ?` → если объект был `primary_cad_number` лота, поле обнуляется (лот сохраняется, можно реассайнить).

---

## `lot_items`

Many-to-many лот ↔ КН с ролью КН в лоте.

```sql
CREATE TABLE lot_items (
  lot_id      TEXT NOT NULL REFERENCES lots(lot_id) ON DELETE CASCADE,
  cad_number  TEXT NOT NULL REFERENCES objects(cad_number) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('building','land','room','equipment','structure')),
  ord         INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (lot_id, cad_number)
);
CREATE INDEX idx_lot_items_cad ON lot_items(cad_number);
```

### Поля

| Поле | Назначение |
|---|---|
| `lot_id` | FK → `lots.lot_id` |
| `cad_number` | FK → `objects.cad_number` |
| `role` | Семантическая роль КН в составе лота (для отображения в `extras.notes`, и для будущего overlay в viewer Phase 2). |
| `ord` | Порядок отображения. По умолчанию 1. |

### Использование в `build_lot_context`

Для лота с >1 КН ctx строится для `primary_cad_number` (или `target_cad_number`, если передан). Остальные КН перечисляются в `extras.notes`:

```text
В состав лота также входят: 61:44:0050706:7 (land); 61:44:0050706:42 (equipment).
```

---

## Контракт совместимости

- **Schema version**: контролируется через миграции (`schema/migrations/0NNN_*.sql`). Текущая — `0001`.
- **CONTRACT_KMZ.md**: НЕ затрагивается. ЭТП-профиль живёт в БД и в виде fetch-фикстуры для viewer; в KMZ wire-формате ничего нет.
- **Фикстура**: `parser/tests/fixtures/etp/object_etp_profile_sample.json` (`$schema_version: "1.0"`). Bump при breaking-изменениях; аддитивные расширения JSON-колонок — без bump'а.

## Verification

Все CHECK-constraint'ы и FK-каскады покрыты `parser/tests/test_etp_profile_schema.py` (12/12 pass на момент миграции). Тест также грузит реальную фикстуру в `:memory:` БД для smoke-проверки.
