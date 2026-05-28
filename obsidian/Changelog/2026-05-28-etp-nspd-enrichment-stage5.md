# 2026-05-28 — ЭТП-экспортёр Stage 5: NSPD-enrichment

## Итог
Закрыты 3 последних §10 SPEC гэпа из data-плоскости: `building.building_type`,
`building.year_built`, `legal.use_type_permitted`. NSPD-данные пишутся в
`object_etp_profile` через gap-fill (никогда не перезаписывают ручной ввод
экономиста).

## Артефакты
- `parser/exporters/etp/nspd_enricher.py` — `merge_nspd_into_profile(conn, cad, nspd_data)` + `enrich_from_directory(conn, dir)` + нормализаторы (`wall_material`, `year`, `permitted_uses`).
- `parser/exporters/etp/nspd_enrich_cli.py` — CLI `python -m parser.exporters.etp.nspd_enrich_cli --db ... --nspd <dir> [--dry-run]`.
- `parser/exporters/etp/build_lot_context.py` — `_build_building` читает `building_type`/`year_built` из `building_extra`; `_build_legal` читает `objects.permitted_use` с overlay от `legal_extra.use_type_permitted`.
- `parser/tests/test_nspd_enricher.py` — 34 теста (нормализаторы + gap-fill семантика + dir-парсер + CLI).
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы», «Использование» (Stage 5 CLI), «Гэпы» (все 4 закрыты).

## Поведение
- Принимаются NSPD-данные из вывода `parser/scripts/01_parsing_nspd_v8.py` (формат `session_export_*.json` или одиночные `<cad>.json` или массив).
- Маппинг NSPD → ЭТП-профиль:
  - `wall_material` → `building_extra.building_type` (нормализован к шаблонной форме: «кирпич» → «кирпичное»).
  - `year_built` (или `year_used` как fallback) → `building_extra.year_built` (int, 1700..2100).
  - `permitted_uses` (list или string) → `legal_extra.use_type_permitted` (joined `"; "`).
- **Никогда не перезаписывает существующие значения** — gap-fill only. Ручной ввод экономиста (`source='osv'`/`'manual'`) в приоритете.
- При создании новой записи: `source='nspd'`, `confidence=0.8` (среднее доверие).

## Тесты (34/34 pass)
- 7 нормализаторов (`wall_material` known/unknown/empty, `year` valid/invalid, `permitted_uses` list/string).
- 7 `merge_nspd_into_profile` (create new, skip existing fields, all-filled skip, year_used fallback, permitted_uses, no-actionable-fields, FK error).
- 5 `enrich_from_directory` (per-file, array format, objects wrapper, invalid JSON skip, FK errors recorded).
- 4 CLI (writes, dry-run, missing db, missing dir).

Регрессия: `test_build_lot_context` 15/15 pass — новое чтение `permitted_use` не сломало старые проверки.

**Полный прогон ЭТП-набора: 145/145 pass** (111 предыдущих + 34 новых).

## Закрытые §10 SPEC гэпы (итого)
| Гэп | Закрыто в | Источник |
|---|---|---|
| Компонентный адрес | PR #61 | `address_parser.py` |
| `encumbrance.influence` | PR #61 | `encumbrance_mapper.py` (17 типов) |
| ETL ОСВ → БД | PR #62 | `etl_osv.py` |
| Stage 4b export JSON | PR #64 | `export_json.py` |
| `building.building_type` | этот PR | NSPD `wall_material` |
| `building.year_built` | этот PR | NSPD `year_built`/`year_used` |
| `legal.use_type_permitted` | этот PR | `objects.permitted_use` + NSPD `permitted_uses` |

## Что осталось
- ETL EXIF UserComment → БД (автозаполнение из фото).
- Auto-export hook (cron / git hook).
- Jinja-grammar refactor.
- viewer Phase 1b editor `admin/etp-profile/<cad_number>` (viewer-team).

## Связи
- PR #62 (Stage 4 ETL), #64 (Stage 4b export JSON) — merged.
- SPEC §10.
- Существующий NSPD-парсер: `parser/scripts/01_parsing_nspd_v8.py` (v8.5).
- `obsidian/Architecture/etp-exporter.md` — обзор системы.
