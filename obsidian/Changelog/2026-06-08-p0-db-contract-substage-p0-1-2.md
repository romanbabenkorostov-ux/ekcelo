# 2026-06-08 — P0.1 DB-контракт C2 sub-stage P0.1.2

## Что сделал
Интеграция `validate_db` (P0.1.1) в импорт-флоу: опциональная валидация
db.sqlite Bundle против C2-контракта + standalone CLI для парсер-команды.

## Файлы
- ✏️ `backend/app/services/bundle.py` — `import_bundle(..., validate_schema=False)`
  + `ImportReport.schema_violations`. При True валидирует source db.sqlite ДО
  мутации target; нарушения → errors + прерывание.
- ✨ `backend/tests/test_bundle_validate_schema.py` — 4 теста.
- ✨ `lot_orchestrator_web/validate_bundle_db_cli.py` — CLI `ekcelo-validate-bundle-db`.
- ✨ `lot_orchestrator_web/tests/test_validate_bundle_db_cli.py` — 7 тестов.
- ✏️ `lot_orchestrator_web/main.py` — `POST /bundles/import` form-param
  `validate_schema` (default false); нарушения → 422 + `schema_violations[]`.
- ✨ `lot_orchestrator_web/tests/test_validate_schema_endpoint.py` — 3 теста.
- ✏️ `pyproject.toml` — script `ekcelo-validate-bundle-db`.
- ✏️ `obsidian/Architecture/p0-db-contract.md` — обновлён под P0.1.1 + P0.1.2.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — P0.1.2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 14 новых (4 service + 7 CLI + 3 endpoint).
- Полный suite в sandbox: **313 passed** (299 + 14).
- Регрессий нет.

## Решения

- **validate_schema=False по умолчанию.** Строгая валидация по ПОЛНОМУ
  контракту (все колонки §1..§5) ломала бы минимальные тест-фикстуры
  существующих bundle-тестов (они создают objects/rights с урезанными
  колонками — валидно для импорта, но не для полного контракта). Default off
  сохраняет backward-compat; реальные Bundle от парсера — полная схема, для
  них вызывающий ставит True. Endpoint form-param и CLI flag — явный opt-in.
- **Прерывание ДО мутации target.** Валидация запускается после locate
  source db.sqlite, но ДО открытия транзакции на target. Нарушение → return
  с schema_violations, целевая БД нетронута. Это даёт чистый early-fail.
- **422 для schema violations** (как и для files_failed) — это «контент не
  прошёл валидацию», семантически Unprocessable Entity. payload всегда несёт
  `schema_violations[]` (пустой если ок/выключено), чтобы фронт/CLI
  единообразно читали.
- **Отдельный CLI, не флаг к import-CLI.** `ekcelo-validate-bundle-db` —
  чистый валидатор без побочных эффектов (не трогает target). Парсер-команда
  запускает его в своём пайплайне ДО отправки Bundle, без указания target_db.
  Exit codes 0/2/3 совместимы с CI-скриптами.

## Канал доставки
- Sandbox-proxy блокирует git push — zip-handoff.
- Архив P0.1.2 готов к доставке (применять после merge P0.1.1).

## Следующий шаг
1. Дождаться merge PR P0.1.1.
2. Применить архив P0.1.2, открыть PR.
3. После merge — P0 контрактного пакета практически закрыт. Остаётся опц.
   P0.1.3/P0.1.4 (кодоген, parser-map) и отложенный C3.3 (geo). Обсудить с
   владельцем: продолжать опц. P0.1, или переход к P1 (auth-трек cycle 14)?
