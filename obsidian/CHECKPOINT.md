# CHECKPOINT — 2026-06-08 (P0.3 ✅ closed · P0.1.1 done · zip-handoff)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox):** `backend/p0-1-db-contract` (P0.1.1 поверх C3.2).
- **Подэтап:** P0.3 закрыт (C1+C2+C3.1+C3.2 в main), **P0.1.1** готов локально.
- **Тесты:** 299 passed в sandbox (191 baseline + 28 C1 + 24 C2 + 25 C3.1 + 18 C3.2 + 13 P0.1.1).
- **main:** PR #105 (C1), #106 (C2), #107 (C3.1), #108 (C3.2) смержены.
- **PR в полёте:**
  - 🟡 fix workspace-test Windows-portable — открыт пользователем.
  - 🟡 P0.1.1 db-contract — готов локально, ждёт доставки.
- **Стратегическое решение (2026-06-08):** НЕ писать parser-team. Идём по
  пути A (P0.1 DB-контракт C2). C3.3 (geo materialization) — отложен, не
  блокирует фронт. См. `obsidian/Architecture/p0-db-contract.md` §«Почему НЕ
  блокирует parser-team».

## Сделано (P0.1.1)

- ✨ `contracts/db/schema.json` — машиночитаемый контракт interchange-схемы
  (8 таблиц §1..§6, restorable=true/false по ADR-001).
- ✨ `contracts/db/DB_SPEC.md` — человекочитаемая спека.
- ✨ `backend/app/services/db_contract.py`:
  - `load_contract()` → dict;
  - `validate_db(db_path, require_section6=False)` → list[str] нарушений;
  - `check_contract_matches_ddl()` → list[str] (CI sync-guard).
- 13 тестов (3 load + 5 validate + 5 sync-guard).

## В процессе / не закончено

- **P0.1.2** — интеграция `validate_db` в `import_bundle` (early-fail 422
  на невалидном db.sqlite) + CLI `ekcelo-validate-bundle-db <path>`. Не начат.
- **P0.1.3** — кодогенерация Pydantic/dataclass моделей из контракта. Опц.
- **P0.1.4** — мапа богатой parser-схемы → interchange-схемы. Опц.
- **C3.3** — geo materialization. **Отложен**, не блокирует фронт.
- Push из sandbox в GitHub не работает — продолжаем zip-handoff.

## Следующий конкретный шаг

После применения архива P0.1.1 на стороне пользователя:
1. Создать ветку `backend/p0-1-db-contract`, скопировать `files/`, commit, push.
2. Открыть PR + сообщить номер.
3. Старт **P0.1.2** (валидация в import).

## Открытые PR

- ✅ #105 C1, #106 C2, #107 C3.1, #108 C3.2 — смержены.
- 🟡 fix workspace-test Windows-portable — открыт пользователем.
- 🟡 Готов локально P0.1.1 (13 тестов) — ждёт доставки.

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Подэтап-снимки:
  - `obsidian/Architecture/p0-viewmodel.md` (C1+C2)
  - `obsidian/Architecture/p0-bundle-storage.md` (C3.1)
  - `obsidian/Architecture/p0-bundle-export.md` (C3.2)
  - `obsidian/Architecture/p0-db-contract.md` (P0.1.1) ← новый
  - `obsidian/Architecture/p0-bundle-importer.md` (A+B)
- Спека: `docs/specs/SPEC_backend.md`
- Контракты:
  - `contracts/db/schema.json` + `DB_SPEC.md` (C2) ← новый
  - `contracts/api/viewmodel.schema.json` + `openapi.yaml` (C4)
  - `contracts/bundle/bundle.schema.json` (C3)
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
