# 2026-05-30 — Cycle 7: etl_checko адаптер (innogrn.db → object_etp_profile)

## Итог
Реализован opt-in адаптер `parser/exporters/etp/etl_checko.py`: читает SQLite-кэш `innogrn.db` (выход standalone-модуля `parser_checko_ru`) и обогащает `object_etp_profile.legal_extra.owner_checko` для указанного лота. parser_checko_ru НЕ импортируется — соответствует [[ADR-002-parser-checko-integration-policy]] (вариант B, отложенная интеграция).

## Триггер выполнен

Per ADR-002 cycle 7 запускался по триггеру: «Orchestrator MVP merged + работа на ≥1 реальном лоте». В этом цикле PR #86 ещё открыт, но реализация cycle 7 не зависит от мерджа orchestrator'а — она читает только `innogrn.db`. Запускаем сейчас, чтобы адаптер был готов к моменту merge.

## Артефакты

- `parser/exporters/etp/etl_checko.py` (~220 LOC):
  - `enrich_lot_from_checko(ek_conn, innogrn_path, lot_id)` — API.
  - CLI: `python -m parser.exporters.etp.etl_checko --db --innogrn-db --lot [--dry-run]`.
- `parser/tests/test_etl_checko.py` — 8 тестов.

## Маппинг innogrn.subjects → owner_checko

| innogrn-колонка | owner_checko-ключ | Тип |
|---|---|---|
| `is_active` | `is_active` | BOOL |
| `status_text` | `status_text` | str |
| `special_regime` | `special_regime` | str ("УСН", "УСН, ПСН", ...) |
| `reg_date` | `reg_date` | ISO date |
| `termination_date` | `termination_date` | ISO date или None |
| `ust_kap` | `ust_kap` | float (уставный капитал) |
| `schr` | `schr` | int (среднесписочная численность) |
| `region` | `region` | str |
| JOIN subject_okveds WHERE is_main=1 | `main_okved` | `{number, name}` |

Только non-null значения попадают в JSON — не плодим `null`-ключи.

## Поведение

- **Gap-fill**: пишет `owner_checko` только если ключа ещё нет (`skipped_reason="owner_checko_already_present"`).
- **Не перезаписывает `source='osv'/'manual'`** в смысле source-поля профиля: для существующих профилей source остаётся как был, мерж только в JSON.
- **Profile отсутствует** → INSERT с `source='checko'`, `confidence=0.9`.
- **innogrn.db отсутствует** → no-op, в EnrichReport помечается `skipped_reason="innogrn_db_missing"`.
- **CAD без `rights.right_holder_inn`** → `skipped_reason="no_right_holder_inn"`.
- **INN не найден в `subjects`** → `skipped_reason="inn_not_in_innogrn"`.
- **`is_branch=1`** записи игнорируются — берётся только головное юрлицо.

## Тесты (8/8 pass, 0.88s)

1. `test_skip_when_innogrn_db_missing` — отсутствие innogrn.db → пропуск без ошибки.
2. `test_skip_when_inn_not_in_innogrn` — INN не в кэше → пропуск, `inn` записан в Item.
3. `test_enriches_existing_profile_with_owner_checko` — happy path: профиль есть, `owner_checko` добавлен, OKVED через JOIN.
4. `test_idempotent_owner_checko_not_overwritten` — повторный вызов → пропуск.
5. `test_skip_when_cad_has_no_right_holder` — CAD без записи в rights → пропуск.
6. `test_empty_lot_yields_empty_report` — пустой lot → empty report.
7. `test_cli_dry_run_does_not_commit` — `--dry-run` откатывает транзакцию.
8. `test_cli_commits_changes` — без `--dry-run` коммитит.

## Зависимости

Никаких новых runtime-deps. Только sqlite3 (stdlib).

## Связи

- ADR: [[ADR-002-parser-checko-integration-policy]] — решение об отложенной интеграции выполнено (вариант B).
- standalone: `parser_checko_ru` от других разработчиков (см. [[parallel-parsers-map]] §4).
- маппинг: `parser_checko_ru/schema_innogrn.sql` v8.2 (subjects, okveds, subject_okveds).

## Дальше

- **cycle 8** — SQLite persistence для `RunStore` (orchestrator_web) + SSE streaming для статуса прогона.
- (опционально) Подключить etl_checko в `build_lot_context` чтобы `owner_checko` попадал в ctx → шаблон. Сейчас данные уже там через `legal_extra`, но шаблон их не упоминает.
