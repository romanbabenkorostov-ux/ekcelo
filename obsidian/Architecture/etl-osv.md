# ETL: survey-лист экономиста → БД (write-API контракт)

> Stage 4 ЭТП-экспортёра. Импорт YAML survey-листа экономиста в таблицы
> `object_etp_profile`, `lots`, `lot_items` (миграция 0001).
>
> Источник: `parser/exporters/etp/etl_osv.py` (модуль) + `etl_osv_cli.py` (CLI).
> Шаблон: `parser/exporters/etp/templates/osv_template.yaml`.
>
> Этот документ — контракт write-API для viewer-team и интеграторов.

## Назначение

Закрыть SPEC §7: «Источник правды для гэп-полей — survey-лист экономиста».
Без этого слоя viewer работает на read-only фикстуре; со Stage 4 — viewer
может переключить fetch на production-данные (экспорт из БД, идентичный формат).

## YAML формат

### Top-level

```yaml
schema_version: "1.0"           # обязательно, текущая версия — "1.0"
default_source: osv             # default для записей без явного source
default_confidence: 1.0         # default для записей без явной confidence
profiles: [...]                 # массив профилей (опц.)
lots:     [...]                 # массив лотов (опц.)
```

### `profiles[]` — UPSERT в `object_etp_profile`

```yaml
profiles:
  - cad_number: "61:44:0050706:31"   # обязательно; FK к objects
    source: osv                      # необязательно (default_source)
    confidence: 1.0                  # необязательно (default_confidence)

    # 6 JSON-секций, все опциональные. Если не указано — поле = NULL.
    location_extra: { landmark, transport_access, environment_short }
    building_extra: { renovation_year, wear_degree, engineering{}, amenities[] }
    layout:         { layout_type, rooms_count, ceiling_height_m, finish_level, finish_state, windows, entry_group, current_condition_comment }
    legal_extra:    { use_type_fact, zoning, special_restrictions[] }
    risks:          { technical_risks[], legal_risks[], location_risks[], other_risks[] }
    extras:         { equipment[], furniture, advantages[], notes }
```

### `lots[]` — UPSERT в `lots` + полная замена `lot_items`

```yaml
lots:
  - lot_id: "lot:pirushin:001"     # обязательно; [A-Za-z0-9_:/-]+, ≤256
    name: "Имущественный комплекс …"  # обязательно
    platform_targets: [torgi.gov.ru, sberbank-ast.ru]   # опц., JSON array
    procedure_type: "приватизации"     # опц., свободный текст
    deal_type: sale                    # опц.: sale | lease | other | null
    primary_cad_number: "61:44:0050706:31"  # опц., FK
    notes_md: "…"                      # опц., Markdown
    items:
      - { cad_number: "61:44:0050706:31", role: room, ord: 1 }
      - { cad_number: "61:44:0050706:7",  role: land, ord: 2 }
```

`role` ∈ `building | land | room | equipment | structure`.
`ord` — порядок (целое, по умолчанию 1).

## Валидация (выбрасывается `ValueError`)

| Проверка | Сообщение содержит |
|---|---|
| `default_source` ∉ enum | `default_source` |
| `default_confidence` ∉ [0,1] | `default_confidence` |
| `profiles[].cad_number` отсутствует | `cad_number` |
| Дубликат `cad_number` в `profiles[]` | `Duplicate profile` |
| `profiles[].source` ∉ enum | `source` |
| `profiles[].confidence` ∉ [0,1] | `confidence` |
| `lots[].lot_id` не матчит `[A-Za-z0-9_:/-]+` или >256 | `lot_id` |
| Дубликат `lot_id` | `Duplicate lot_id` |
| `lots[].name` пустое | `name` |
| `lots[].deal_type` ∉ enum (и не null) | `deal_type` |
| `lots[].items[].role` ∉ enum | `role` |

## Apply-семантика (`apply_osv(conn, doc, *, dry_run=False)`)

- **Транзакционно:** либо все записи документа применяются, либо ни одной (rollback на любой ошибке, в т.ч. FK).
- **`profiles[]`:** UPSERT по `cad_number`. При update полностью перезаписываются все JSON-колонки + `source` + `confidence`; `updated_at` обновляется на `now()`.
- **`lots[]`:** UPSERT по `lot_id`. При update перезаписываются все скаляры лота; `created_at` не меняется.
- **`lot_items` лота:** **полная замена** при каждом импорте (`DELETE FROM lot_items WHERE lot_id=? + INSERT`). Это даёт экономисту возможность перетасовывать состав лота без stale-rows.
- **FK к `objects`:** все `cad_number` должны существовать в `objects` (СCHEMA-инвариант миграции 0001). Если нет — `IntegrityError` + rollback всей транзакции.

## ApplyReport

```python
@dataclass
class ApplyReport:
    profiles_inserted: int = 0
    profiles_updated:  int = 0
    lots_inserted:     int = 0
    lots_updated:      int = 0
    lot_items_inserted: int = 0
    lot_items_deleted:  int = 0
    dry_run: bool = False
```

Используется для логирования / CI-проверок.

## Использование

### CLI

```bash
python -m parser.exporters.etp.etl_osv_cli \
    --yaml path/to/survey.yaml \
    --db   path/to/ekcelo.sqlite \
    [--dry-run]
```

Exit codes: `0` — успех; `2` — yaml/db не найден; `3` — yaml не валиден.

Output (stdout):
```
[APPLIED] profiles: +1/~0  lots: +1/~0  lot_items: +2/-0
```

### Python

```python
import sqlite3
from parser.exporters.etp import load_osv, apply_osv

conn = sqlite3.connect("ekcelo.sqlite")
conn.execute("PRAGMA foreign_keys = ON")
doc = load_osv("survey.yaml")
report = apply_osv(conn, doc)             # commits on success
# или dry_run=True — валидация без записи
```

## Контракт с viewer-team

После запуска ETL viewer должен переключить fetch с фикстуры на новый JSON-путь.
**Параметр контракта:** структура `object_etp_profile` строк после ETL **байт-в-байт** совпадает с записями фикстуры `parser/tests/fixtures/etp/object_etp_profile_sample.json` (массив `object_etp_profile[]`).

Экспортный путь для viewer (план Stage 4b — `etl_export_json.py`):
```
out/etp/<project>/object_etp_profile.json  # тот же формат, что фикстура
```

`CONTRACT_KMZ.md` 2.12.0 не затрагивается (§3 UI/UX-домен).

## Расширение / совместимость

- **Schema bump** (`schema_version: "1.0" → "1.1"`): добавление новых JSON-секций или новых ключей внутри секций — без bump'а (forward-compat: парсер игнорирует неизвестные ключи). Изменение валидации, удаление поля — bump.
- **Новые `source`:** требует расширения CHECK-constraint в миграции БД (отдельный миграционный PR) **и** enum в `etl_osv.py`.
- **Несколько входных файлов:** на данном этапе по одному. Будет нужно объединять — сделаем `merge_osv(docs: list[OsvDocument])` с разрешением конфликтов «последний выигрывает по cad_number».

## Связанные документы

- `obsidian/Architecture/etp-exporter.md` — обзор всей системы.
- `obsidian/Database/etp-tables.md` — структура таблиц.
- `obsidian/Decisions/ADR-001-etp-profile-extension.md` — обоснование схемы.
- `docs/etp_export/SPEC_etp_export.md` §3, §5, §7.
- `parser/tests/test_etl_osv.py` — 18 тестов покрытия валидации и apply-семантики.
- `parser/exporters/etp/templates/osv_template.yaml` — рабочий пример.
