# 2026-05-30 — Smoke-CLI: end-to-end проверка ЭТП-экспортёра одной командой

## Итог
Добавлен `parser/exporters/etp/smoke_cli.py` — end-to-end smoke-тест в tmp-директории. Гоняет import-check всех 20 модулей пакета, `init_db --with-template`, Stage 3 export, `export_json_cli` и проверяет артефакты. Профилактика «missing-module» инцидентов (см. `etp-local-sync.md` / PR #83) на уровне CI / релиз-валидации.

## Артефакты
- `parser/exporters/etp/smoke_cli.py` — CLI (≈220 строк):
  - `--work-dir <dir>` — кастомная директория (default: tmp с автоудалением).
  - `--keep` — не удалять tmp (для отладки).
  - `--quiet` — подавить [OK]-строки; провалы печатаются всегда.
- `parser/tests/test_smoke_cli.py` — 6 тестов.
- `obsidian/Architecture/etp-exporter.md` — добавлена строка в таблице этапов + раздел «CLI: smoke-тест end-to-end».

## Что проверяет (32 чек-поинта)
1. **import-check** (20) — `importlib.import_module` для каждого модуля пакета. Ловит missing-module ДО запуска любого CLI.
2. **init-db** (1) — `init_db_cli --with-template` создаёт SQLite + 3 объекта + профиль + лот.
3. **db rows** (4) — `objects=3 / object_etp_profile=1 / lots=1 / lot_items=2`.
4. **cli export** (1) — Stage 3 `cli` для `lot:pirushin:001` × `torgi.gov.ru` × `short,full`.
5. **artifacts** (4) — `lot_appendix.md`, `description.short.txt`, `description.full.txt`, `long_description.json` существуют и непустые.
6. **export-json** (1) — `export_json_cli` отрабатывает rc=0.
7. **json payload** (1) — ключи `$schema_version` / `object_etp_profile` / `lots` / `lot_items` присутствуют, `profiles` и `lots` непустые.

Exit code 0 — все 32 прошли; 1 — провал с детализацией в stderr.

## Тесты (6/6 pass)
- `test_smoke_happy_path` — rc=0, ни одного `[FAIL]` в выводе.
- `test_smoke_produces_artifacts` — все ожидаемые файлы непустые.
- `test_smoke_export_json_payload` — структура `object_etp_profile.json` валидна.
- `test_smoke_detects_import_failure` — подмена `importlib.import_module` для `auto_export` → rc=1, упоминание модуля и `ModuleNotFoundError` в stderr.
- `test_smoke_keep_preserves_workdir` — `--work-dir` сохраняет артефакты.
- `test_required_modules_list_matches_package` — список `_REQUIRED_MODULES` не расходится с фактическим содержимым `parser/exporters/etp/`.

## Назначение
- **CI / release validation** — single-command зелёный/красный сигнал.
- **Локальная проверка после клона/обновления** — `python -m parser.exporters.etp.smoke_cli` за ~2 сек.
- **Профилактика инцидентов** — пропущенный файл при ZIP-доставке (как `auto_export.py` в #83) ловится на import-фазе, до запуска CLI.

## Связи
- PR #83 (`obsidian/Architecture/etp-local-sync.md`) — описывает корневую причину инцидента, который теперь воспроизводимо детектится smoke-CLI.
- Использует существующие `main()` контракты: `init_db_cli`, `cli`, `export_json_cli` — без новых зависимостей.
- Stage 5/6 (NSPD/EXIF) намеренно НЕ включены в smoke — они требуют внешних артефактов (NSPD-JSON, JPG с UserComment) и покрываются отдельными интеграционными тестами.

## Дальше
- Cycle закрыт. Следующий — **Orchestrator (#4)** отдельным циклом после согласования scope.
