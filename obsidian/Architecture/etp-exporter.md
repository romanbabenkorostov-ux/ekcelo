# Архитектура: ЭТП-экспортёр

> Экспорт объектов сюрвея в карточки лотов российских ЭТП
> (`torgi.gov.ru`, `roseltorg.ru`, `sberbank-ast.ru`).

## Назначение

Превратить данные парсера ЕГРН + ручные правки экономиста + EXIF фото в **карточку лота** на ЭТП с развёрнутым текстовым описанием, соответствующим требованиям отчёта оценщика.

Целевая аудитория документа: parser-team, viewer-team, экономист (для понимания пайплайна).

## Слои системы

```
                ┌─────────────────────────────────────────────┐
                │                  ИСТОЧНИКИ                  │
                └─────────────────────────────────────────────┘
   ЕГРН-выписки    ОСВ/survey-лист      Фото (EXIF)      NSPD/LLM
        │              │                    │                │
        ▼              ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  Парсер (parser/)                                            │
│   • egrn_parser/parsers/xml_parser.py, pdf_parser.py         │
│   • Запись в БД (миграция 0001 = ЭТП-профиль)                │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  БД (SQLite)                                                 │
│   ЕГРН-слой:    objects / rights / entity_registry /         │
│                  extracts / object_restrictions              │
│   ЭТП-профиль:  object_etp_profile / lots / lot_items        │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Экспортёр (parser/exporters/etp/)                           │
│   build_lot_context()  →  ctx dict (SPEC §3)                 │
│   render_lot_description() →  текст для ЭТП (Jinja)          │
│   [CLI / PDF-appendix — Stage 3]                             │
└─────────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
   ┌─────────────┐              ┌─────────────────┐
   │   Viewer    │              │  Артефакты лота │
   │ (info-card  │              │  *.json + *.txt │
   │  read-only) │              │  + *.pdf (3+)   │
   └─────────────┘              └─────────────────┘
```

## Компоненты

### 1. БД (миграция `schema/migrations/0001_etp_profile.sql`)

Три таблицы, явный «не-ЕГРН» слой:

| Таблица | Назначение | Ключ |
|---|---|---|
| `object_etp_profile` | Гэп-поля развёрнутого описания. JSON-колонки: `location_extra`, `building_extra`, `layout`, `legal_extra`, `risks`, `extras`. Метаданные: `source` ∈ {osv\|exif\|manual\|nspd\|llm}, `confidence` ∈ [0,1]. | `cad_number` (FK → `objects`) |
| `lots` | Лот = единица экспорта (группа КН). `procedure_type`, `deal_type`, `platform_targets[]`, `primary_cad_number`, `notes_md`. | `lot_id` (`[A-Za-z0-9_:/-]+`, ≤256, совместимо с `graph_node_id` из CONTRACT_KMZ §6) |
| `lot_items` | Many-to-many лот ↔ КН с `role` ∈ {building\|land\|room\|equipment\|structure} и `ord`. | `(lot_id, cad_number)` |

Подробности по полям: `obsidian/Database/etp-tables.md`. Архитектурное решение: `obsidian/Decisions/ADR-001-etp-profile-extension.md`.

### 2. `build_lot_context(conn, lot_id, ...)` → `ctx: dict`

Файл: `parser/exporters/etp/build_lot_context.py`.

**Что делает:** читает БД и собирает ctx-словарь, совместимый с `docs/etp_export/SPEC_etp_export.md` §3.

**Сигнатура:**

```python
def build_lot_context(
    conn: sqlite3.Connection,
    lot_id: str,
    *,
    platform: str = "torgi.gov.ru",
    platform_mode: str = "short",
    target_cad_number: str | None = None,
) -> dict
```

**Структура ctx (9 ключей):**

- `meta` — `{platform, platform_mode, object_type, deal_type, procedure_type, locale}`
- `identity` — `{title, purpose, area_total_sqm, area_land_sqm, floor, floors_total, cadastral_number}`
- `location` — `{region, municipality, ..., room, address_raw, landmark, transport_access, environment_short}`
- `building` — `{building_type, floors_total, year_built, renovation_year, wear_degree, engineering{}, amenities[]}` или `{}` для земли
- `layout_and_condition` — `{layout_type, rooms_count, ceiling_height_m, finish_level, ...}` или `{}` при отсутствии данных
- `legal` — `{right_type, right_holder, basis_type, encumbrances[], use_type_fact, use_type_permitted, zoning, special_restrictions[]}`
- `risks` — `{technical_risks[], legal_risks[], location_risks[], other_risks[]}`
- `extras` — `{equipment[], furniture, advantages[], notes}` (для multi-cad лотов notes автоматически перечисляет остальные КН)
- `generated_text` — `{short, full, version}` (плейсхолдер для кэширования)

**Особенности:**

- Multi-cad лоты: ctx строится для `primary_cad_number`; остальные КН попадают в `extras.notes`.
- Земельные участки: `building` и `layout_and_condition` пустые, `area_land_sqm` заполнен.
- Profile отсутствует или JSON-поле `null` → соответствующая секция ctx пуста (graceful fallback).

### 3. `render_lot_description(ctx)` → `str`

Файл: `parser/exporters/etp/text_render.py`.

**Что делает:** рендерит ctx через Jinja-шаблон с автодиспатчем на платформу.

**Шаблон:** `parser/exporters/etp/templates/torgi_long_description.j2` (473 строки, импорт из `docs/etp_export/05_jinja_шаблон_все_платформы.md` + локальное расширение `full_address` с фолбэком на `address_raw`).

**Платформенные ветви в шаблоне:**

| Платформа | Тон | Особенности |
|---|---|---|
| `torgi.gov.ru` | Официальный, сжатый | Канон-формат. Short = 3 абзаца, full = 6 абзацев. |
| `roseltorg.ru` | Разговорно-развёрнутый | Больше про район и выводы. |
| `sberbank-ast.ru` | Оценочно-процедурный | Акцент на «предмет торгов», банкротство/приватизация (берётся из `lots.procedure_type`). |

**Особенности:**

- `ChainableUndefined`: цепочки `ctx.X.Y.Z` на отсутствующих словарях молча → undefined, шаблон не падает.
- Whitespace-нормализация: 3+ переносов → 2; trailing-spaces убраны; результат заканчивается одним `\n`.
- Неизвестная platform/mode → `ValueError`.

### 4. Шаблон-источник истины

`docs/etp_export/05_jinja_шаблон_все_платформы.md` — спецификация шаблона. `parser/exporters/etp/templates/torgi_long_description.j2` — engineering-копия. Изменения в шаблоне должны идти в обе версии (spec-first, как с `CONTRACT_KMZ`).

### 5. Viewer (Phase 1, read-only)

Файл: `viewer/index.html`.

Карточка объекта подгружает фикстуру `parser/tests/fixtures/etp/object_etp_profile_sample.json` и рендерит блок «ЭТП-профиль» с бейджем `source` / `confidence`:

| confidence | Бейдж | Текст |
|---|---|---|
| `1.0` (osv/manual) | зелёный | нормальный |
| `0.5..0.99` (nspd/exif) | жёлтый | нормальный |
| `< 0.5` (любой) | оранжевый | приглушённый (`opacity:0.55`) |

Подзаголовок «— ЕГРН —» появляется только если для КН существует ЭТП-профиль.

Phase 2 (overlay лотов на карте через S5 group-overlay) — отложена до подтверждённого спроса.

## Этапы (state on 2026-05-28)

| Этап | Что | Статус | PR |
|---|---|---|---|
| SPEC | `docs/etp_export/SPEC_etp_export.md` + материалы 00..05 | done | #41 |
| ADR-001 | Решение по расширению БД | done · Accepted | #48 |
| 025 + 026 | Согласование с viewer-team (5 вопросов) | done · 5/5 ack | #50, #60 |
| Fixture | `tests/fixtures/etp/object_etp_profile_sample.json` | done | #53 |
| DDL | Миграция 0001 + CHECK-constraint'ы + 12 тестов | done | #54 |
| Stage 1 | `build_lot_context` + 15 тестов | done | #55 |
| viewer Phase 1 | Read-only рендер + бейджи | done | #56 |
| Stage 2 | `render_lot_description` + 8 golden | done | #57 |
| Docs (Architecture + Database) | obsidian/* справочник | done | #58 |
| Stage 3 | CLI + Markdown-приложение + integration test | done | #59 |
| address_parser + encumbrance_mapper | Закрыты 2 из 4 §10 гэпов | done | #61 |
| **Stage 4: ETL ОСВ → БД** | Импорт YAML survey-листа экономиста | done | этот PR |
| NSPD-enrichment | building_type / year_built / use_type_permitted | план | — |
| ETL EXIF → БД | Парсер UserComment для гэп-полей | план | — |
| Stage 4b: export JSON для viewer | Замена фикстуры на production-источник | done | этот PR |
| viewer Phase 2 | Overlay лотов на карте | YAGNI | — |
| viewer Editor | `admin/etp-profile/<cad>` UI | план viewer-team | — |

## Использование (текущее API)

### Python

```python
import sqlite3
from parser.exporters.etp import build_lot_context, render_lot_description

conn = sqlite3.connect("path/to/ekcelo.sqlite")
ctx = build_lot_context(
    conn,
    lot_id="lot:pirushin:001",
    platform="sberbank-ast.ru",
    platform_mode="full",
)
text = render_lot_description(ctx)
print(text)
```

### Регенерация golden-файлов (после осознанных изменений шаблона)

```bash
cd <repo-root>
python3 parser/scripts/dev/gen_etp_golden.py
```

После регенерации запустить `pytest parser/tests/test_text_render.py -v` и закоммитить новые goldens.

### CLI: экспорт лота в файлы

```bash
python -m parser.exporters.etp.cli \
    --lot lot:pirushin:001 \
    --platforms torgi.gov.ru,sberbank-ast.ru \
    --modes short,full \
    --db path/to/ekcelo.sqlite \
    --out out/etp/
```

### CLI: импорт ОСВ survey-листа в БД (Stage 4)

```bash
python -m parser.exporters.etp.etl_osv_cli \
    --yaml path/to/survey.yaml \
    --db   path/to/ekcelo.sqlite \
    [--dry-run]
```

Контракт YAML: `obsidian/Architecture/etl-osv.md`.

### CLI: экспорт БД в JSON для viewer (Stage 4b)

```bash
# Глобально → parser/exports/etp/object_etp_profile.json
python -m parser.exporters.etp.export_json_cli --db path/to/ekcelo.sqlite

# Project-фильтр → parser/exports/etp/<slug>/object_etp_profile.json
python -m parser.exporters.etp.export_json_cli --db ... --project pirushin
```

Файл коммитится в репо; viewer на GitHub Pages fetch'ит его (формат
байт-в-байт совпадает с `parser/tests/fixtures/etp/object_etp_profile_sample.json`).

Подробности и workflow: `parser/exports/etp/EXPORT_NOTES.md`.

### Полный пайплайн «экономист → ЭТП»

```
1. Экономист правит YAML  ──▶  parser/inbox/etp/<date>-<slug>.yml
                                      │
                                      ▼
2. parser-A: etl_osv_cli   ──▶  object_etp_profile / lots / lot_items в БД
                                      │
                                      ▼
3. parser-A: export_json_cli ─▶  parser/exports/etp/[<slug>/]object_etp_profile.json
                                      │
                                      ├──▶ viewer fetch (admin/etp-profile/<cad>)
                                      ▼
4. parser-A: cli (Stage 3) ──▶  out/etp/<lot>/description.{short,full}.txt
                                                + lot_appendix.md
                                      │
                                      ▼
5. Оператор загружает на ЭТП.
```

## Гэпы и ограничения

Документированы в SPEC §10. На 2026-05-28 закрыты:
- Структура БД (миграция 0001).
- Маркировка `source`/`confidence` (обязательные NOT NULL).
- Совместимость `lot_id` с `graph_node_id` (CHECK-constraint + Phase 2-готовность viewer).
- ✅ **Компонентный адрес** (`location.region/.../room`) — `address_parser.py`.
- ✅ **`legal.encumbrances[].influence`** — `encumbrance_mapper.py` (17 канонических типов).
- ✅ **Источник правды по гэп-полям** — ETL ОСВ YAML → `object_etp_profile` (Stage 4).

Открыто:
- **`building.building_type` / `year_built` / `legal.use_type_permitted`.** Нужен NSPD-enrichment.
- **EXIF UserComment → БД.** Автозаполнение из фото объекта.
- ✅ **Stage 4b: export JSON.** `parser/exporters/etp/export_json.py` пишет `parser/exports/etp/[<project>/]object_etp_profile.json` — viewer переключает fetch (`EXPORT_NOTES.md`).
- **Грамматические шероховатости шаблона** (импорт «как есть» из спеки). Рефакторинг — отдельный PR с обновлением `docs/etp_export/05_*.md` и регенерацией goldens.

## Связанные документы

- `docs/etp_export/SPEC_etp_export.md` — полная спецификация.
- `docs/etp_export/00..05_*.md` — материалы по структуре описания и Jinja-шаблонам.
- `obsidian/Decisions/ADR-001-etp-profile-extension.md` — обоснование расширения БД.
- `obsidian/Database/etp-tables.md` — детальная схема таблиц ЭТП-профиля.
- `docs/CORRESPONDENCE/025..026-*.md` — согласование с viewer-team.
- `parser/tests/fixtures/etp/FIXTURE_NOTES.md` — кейсы покрытия (A/B/C).
