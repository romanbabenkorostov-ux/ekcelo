# 2026-06-09 — P0.1.3 codegen + GitHub Actions handoff workflow

## Что сделал

1. **P0.1.3 — Pydantic codegen из C2-контракта.**
   - `backend/app/services/db_codegen.py` — генерирует `db_models.py` из
     `contracts/db/schema.json`. 8 классов *Row, маппинг `TABLE_TO_MODEL`.
   - `backend/app/services/db_models.py` — сгенерированный модуль (committed,
     ре-генерируется CLI).
   - CLI `ekcelo-db-codegen` (`pyproject.toml::scripts`).
   - CI sync-guard: тест проверяет что текущий `db_models.py` побайтно совпадает
     с `db_codegen.generate()` — ловит забытую перегенерацию.
   - 10 тестов: generate, sync-guard, table coverage, TABLE_TO_MODEL, validate
     happy/missing/extra, CLI stdout/file, sha-марка.

2. **GitHub Actions: `apply-handoff.yml`** — автоматизирует zip-handoff.
   - `workflow_dispatch` с inputs (archive_url, branch_name, commit_message, pr_title).
   - Скачивает zip из URL → unpack files/* в репо → branch → commit → push → PR.
   - Использует Fine-grained PAT (1 год) в секрете `EKCELO_APPLY_PAT`.
   - Документация: `obsidian/UserGuide/github-actions-handoff.md` (setup + usage).

## Файлы
- ✨ `backend/app/services/db_codegen.py` — codegen ядро.
- ✨ `backend/app/services/db_models.py` — сгенерированный модуль.
- ✨ `backend/tests/test_db_codegen.py` — 10 тестов.
- ✏️ `pyproject.toml` — script `ekcelo-db-codegen`.
- ✨ `.github/workflows/apply-handoff.yml` — workflow.
- ✨ `obsidian/UserGuide/github-actions-handoff.md` — setup guide для PAT + workflow.
- ✏️ `obsidian/Architecture/p0-db-contract.md` — обновлён под P0.1.3.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — P0.1.3 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 10 новых (P0.1.3 codegen).
- Полный suite: **323 passed** (313 + 10).

## Решения

- **Сгенерированный файл committed в репо**, не на лету. Причины:
  IDE-автокомплит, понятный diff в PR при изменении контракта, можно
  использовать без запуска codegen. CI sync-guard защищает от рассинхрона.
- **Имя классов = `<TablePascalCase>Row`** (плюс суффикс Row для ясности
  «это модель строки БД»). `objects` → `ObjectsRow`, `object_etp_profile`
  → `ObjectEtpProfileRow`. Без специальной депрализации (была бы соблазн
  убрать `s` в `objects→Object`, но тогда конфликт с другими классами).
- **`extra='allow'`** в каждой модели — forward-compat: лишние колонки в
  row не ломают валидацию (parser может эмитить дополнительные поля).
- **SHA-марка контракта в сгенерированном файле**. Если кто-то изменил
  schema.json но забыл перегенерировать — sha разойдётся, sync-guard
  выдаст конкретную подсказку.
- **Workflow с `workflow_dispatch`** (ручной запуск), не push-trigger.
  Безопаснее: ничего не запускается автоматически при push в репо.
- **PAT через repository secret**, не env. GitHub маскирует значения секретов
  в логах. PAT не виден ни мне (sandbox не имеет доступа к Settings →
  Secrets), ни в публичных логах workflow.
- **Fine-grained PAT 1 год** — оптимум: классические PAT no-expire
  опаснее (потеря = доступ ко всем репо без срока), 7-30 дневные
  требуют частой ротации.

## Что НЕ в P0.1.3

- **P0.1.4 (опц.)** — мапа богатой parser-схемы (`parser/egrn_parser/db/
  schema.sql`, 23 таблицы) → interchange-схемы (8 таблиц). Будет отдельным
  sub-stage если есть запрос от parser-team.
- **Refactoring bundle.py / viewmodel.py к типизированному доступу**
  через сгенерированные модели — оставлено как opt-in (текущий
  `row["col"]` работает; миграция = большой diff без функционального
  улучшения).
- **OAuth cycle 14** — следующий sub-stage (большой объём, требует
  отдельного архива).

## Канал доставки

- Sandbox-proxy блокирует git push — zip-handoff активен.
- Этот архив включает workflow, который ПОСЛЕ merge сделает следующие
  архивы автоматизированно applied (если настроите PAT).

## Следующий шаг

1. Применить архив P0.1.3, открыть PR.
2. После merge — настроить PAT + secret (one-time).
3. Старт **cycle 14 OAuth** (большой sub-stage).
