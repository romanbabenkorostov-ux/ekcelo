# CHECKPOINT — 2026-06-08 (P0.3 ✅ · P0.1.1+P0.1.2 done · zip-handoff)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox):** `backend/p0-1-2-validate-import` (P0.1.2 поверх P0.1.1).
- **Подэтап:** P0.3 закрыт; P0.1.1 запушен (PR ждёт merge); **P0.1.2** готов локально.
- **Тесты:** 313 passed в sandbox (191 baseline + 28 C1 + 24 C2 + 25 C3.1 + 18 C3.2 + 13 P0.1.1 + 14 P0.1.2).
- **main:** #104 (P0.2), #105 (C1), #106 (C2), #107 (C3.1), #108 (C3.2) смержены.
- **PR в полёте:**
  - 🟡 fix workspace-test Windows-portable — открыт пользователем.
  - 🟡 P0.1.1 db-contract (commit 1c15191) — запушен, ждёт merge.
  - 🟡 P0.1.2 validate-import — готов локально, ждёт доставки.
- **Стратегия (2026-06-08):** путь A — НЕ писать parser-team, идём P0.1.
  C3.3 (geo) отложен, не блокирует фронт.

## Сделано (P0.1.2)

- `import_bundle(..., validate_schema=False)` + `ImportReport.schema_violations`
  — opt-in валидация source db.sqlite против C2-контракта ДО мутации target.
- `POST /bundles/import` form-param `validate_schema` (default false) → 422 +
  `schema_violations[]` на не-схемном db.sqlite.
- CLI `ekcelo-validate-bundle-db <bundle|db>` — standalone валидатор для
  парсер-команды (exit 0/2/3, `--require-section6`, `--json`).
- 14 тестов (4 service + 7 CLI + 3 endpoint).

## В процессе / не закончено

- **P0.1.3** (опц.) — кодогенерация Pydantic/dataclass из контракта. Не начат.
- **P0.1.4** (опц.) — мапа богатой parser-схемы → interchange-схемы. Не начат.
- **C3.3** — geo materialization (KMZ→БД). **Отложен**, не блокирует фронт.
- После P0.1.2 в main — **P0 контрактного пакета практически закрыт**.
  Развилка: опц. P0.1.3/4, или переход к P1 (auth cycle 14). Решение владельца.
- Push из sandbox в GitHub не работает — zip-handoff.

## Следующий конкретный шаг

После merge P0.1.1:
1. Применить архив P0.1.2 (`backend/p0-1-2-validate-import`), PR, номер.

После merge P0.1.2:
2. Решить с владельцем: опц. P0.1.3/4 vs P1 auth-трек vs ждать parser для C3.3.

## Открытые PR

- ✅ #104 P0.2, #105 C1, #106 C2, #107 C3.1, #108 C3.2 — смержены.
- 🟡 fix workspace-test — открыт.
- 🟡 P0.1.1 — запушен, ждёт merge.
- 🟡 P0.1.2 — готов локально, ждёт доставки.

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Подэтап-снимки:
  - `obsidian/Architecture/p0-db-contract.md` (P0.1.1 + P0.1.2) ← обновлён
  - `obsidian/Architecture/p0-viewmodel.md` (C1+C2)
  - `obsidian/Architecture/p0-bundle-storage.md` (C3.1)
  - `obsidian/Architecture/p0-bundle-export.md` (C3.2)
  - `obsidian/Architecture/p0-bundle-importer.md` (A+B)
- Спека: `docs/specs/SPEC_backend.md`
- Контракты:
  - `contracts/db/schema.json` + `DB_SPEC.md` (C2)
  - `contracts/api/viewmodel.schema.json` + `openapi.yaml` (C4)
  - `contracts/bundle/bundle.schema.json` (C3)
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
