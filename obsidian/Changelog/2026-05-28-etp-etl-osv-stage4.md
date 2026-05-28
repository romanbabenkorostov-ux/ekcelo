# 2026-05-28 — ЭТП-экспортёр Stage 4: ETL ОСВ YAML → БД

## Итог
Закрыт SPEC §7. Экономист может теперь импортировать survey-лист в YAML в БД одной командой; viewer переключится на production-источник после Stage 4b (JSON-экспорт).

## Артефакты
- `parser/exporters/etp/etl_osv.py` — `load_osv(path) → OsvDocument` + `apply_osv(conn, doc, *, dry_run) → ApplyReport`.
- `parser/exporters/etp/etl_osv_cli.py` — CLI `python -m parser.exporters.etp.etl_osv_cli --yaml <path> --db <path> [--dry-run]`.
- `parser/exporters/etp/templates/osv_template.yaml` — заполненный пример с case A.
- `parser/tests/test_etl_osv.py` — 18 тестов.
- `obsidian/Architecture/etl-osv.md` — **write-API контракт** для viewer-team и интеграторов.
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы», «Использование», «Гэпы».

## Контракт YAML

```yaml
schema_version: "1.0"
default_source: osv
default_confidence: 1.0

profiles:
  - cad_number: "..."
    location_extra: {...}
    building_extra: {renovation_year, wear_degree, engineering{}, amenities[]}
    layout: {...}
    legal_extra: {...}
    risks: {...}
    extras: {...}

lots:
  - lot_id: "lot:slug:NNN"
    name: "..."
    platform_targets: [...]
    procedure_type: "..."
    deal_type: sale|lease|other|null
    primary_cad_number: "..."
    notes_md: "..."
    items: [{cad_number, role, ord}]
```

## Поведение
- **Транзакционно:** rollback всей транзакции при любой ошибке (включая FK).
- **`profiles[]`:** UPSERT по `cad_number`; обновление перезаписывает все JSON-секции + source + confidence.
- **`lots[]`:** UPSERT по `lot_id`; обновление перезаписывает скаляры.
- **`lot_items` лота:** полная замена (DELETE+INSERT) — позволяет перетасовывать состав без stale-rows.
- **`--dry-run`:** валидация + report без записи.
- **Валидация:** source/deal_type/role/`lot_id` charset/confidence range/дубликаты.

## Тесты (18/18 pass)
- 10 load-validation (unknown source/confidence/lot_id charset/lot_id длина/duplicates/role/deal_type/empty yaml/template).
- 8 apply (insert/update profile, insert lot+items, replace items on lot update, dry-run, rollback on FK, default source+confidence, end-to-end template).

Полный прогон ЭТП-набора: **98/98 pass** (12 schema + 15 build_lot_context + 18 render + 9 cli integration + 12 address + 14 encumbrance + 18 etl).

## Следующий шаг
- **Stage 4b:** `etl_export_json.py` — экспорт `object_etp_profile` в JSON-формат фикстуры для viewer (replaces read-only фикстуру в production).
- **NSPD-enrichment:** building_type, year_built, use_type_permitted.
- **EXIF UserComment → БД** — автозаполнение из фото.

## Связи
- SPEC §3, §5, §7.
- ADR-001 + миграция 0001 (#48, #54).
- CORRESPONDENCE/025+026: Stage 4 разблокирует viewer переключение fetch на новый JSON-путь.
