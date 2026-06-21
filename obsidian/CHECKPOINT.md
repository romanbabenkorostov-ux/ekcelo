# CHECKPOINT — 2026-06-21 (P0 ✅ · cycle 14 ✅ · cycle 15 RBAC ЗАКРЫТ M1-M4)

> **2026-06-21:** Cycle 15 M4 done — enforcement на боевых роутах
> (`create_app(enforce_rbac=True)`) + Basic Auth roles-карта
> `EKCELO_AUTH_ROLES`. **Трек RBAC закрыт целиком (C6 ROLES_SPEC).** 14 M4
> тестов, suite 458 passed. Применять ПОСЛЕ merge #117 (M3).
> Защищаемые роуты: `/objects/{cad}`, `/objects/{cad}/graph`,
> `/lots/{lot_id}`, `/bundles/{id}/download`. `/catalog` — листинг, не под
> require_action. См. `obsidian/Architecture/cycle-15-rbac.md`,
> `obsidian/Changelog/2026-06-21-cycle-15-rbac-m4.md`.
>
> Ниже — запись M3; обновится после merge.

# CHECKPOINT — 2026-06-15 (P0 ✅ · #114/#115/#116 · cycle 15 M3 done)

> **2026-06-15 (M3):** Cycle 15 M3 RBAC FastAPI integration — `require_action`
> dependency (opt-in) + REST `POST/DELETE /grants` + `GET /grants/me`. 19
> тестов. Suite 444 passed. Применять ПОСЛЕ merge #116 (M2+bridge).
> Существующие роуты НЕ затронуты (enforcement = M4 через флаг).
> См. `obsidian/Architecture/cycle-15-rbac.md` (M1+M2+M3).
>
> Ниже — запись M2+bridge; обновится после merge.

# CHECKPOINT — 2026-06-15 (P0 ✅ · #114/#115 ✅ · cycle 15 M2 + bridge done)

> **2026-06-15:** Cycle 15 M2 (SQLiteGrantStore в отдельной access.sqlite) +
> Bridge burst 1 (namespace split contracts/bundle-db-slice/ + post 029) +
> datetime cleanup. 25 M2 тестов + 3 bridge-guard. Suite 423 passed.
> См. `obsidian/Architecture/cycle-15-rbac.md` (M1+M2), `docs/CORRESPONDENCE/
> 029-backend-bundle-db-slice-namespace.md`. Применять ПОСЛЕ merge #115.
>
> Ниже — старая запись от утра 2026-06-14; обновится после merge.

# CHECKPOINT — 2026-06-14 (P0 ✅ · #114 cycle 14 M1 ✅ · cycle 15 M1 done)

> **2026-06-14 (вечер):** Cycle 15 M1 RBAC done — Principal/Grant/can/delegate/
> share + InMemoryGrantStore. 44 теста. Suite 398 passed. Также убран
> InsecureKeyLengthWarning из cycle 14 (HMAC secrets ≥32 байт).
> Применять ПОСЛЕ merge cycle 14 (#114 ✅).
>
> ⚠️ В main параллельно появилась работа parser-team в `contracts/db/` —
> 33-таблиц backend storage (7163 insertions, 73 файла). Архитектурное
> расхождение с моим C2 interchange-контрактом (8 таблиц). Согласовать
> через post 029 после merge cycle 15 M1.
>
> Ниже — утренняя запись 2026-06-14; обновится после merge.

# CHECKPOINT — 2026-06-14 (P0 ✅ · cycle 14 M1 done · zip + Actions)

> **2026-06-14:** Cycle 14 M1 done — Bearer-JWT verifier + OAuthMiddleware +
> strategy dispatcher (OIDC > Basic > none). 31 теста. Suite 354 passed.
> См. `obsidian/Changelog/2026-06-14-cycle-14-oauth-m1.md` и
> `obsidian/Architecture/cycle-14-oauth.md`. Применять ПОСЛЕ merge P0.1.3.
>
> Ниже — старая запись от 2026-06-09; обновится после merge.

# CHECKPOINT — 2026-06-09 (P0.3 ✅ · P0.1.1+P0.1.2+P0.1.3 done · zip + Actions)

> **2026-06-09:** P0.1.3 done — Pydantic codegen из C2-контракта (10 тестов)
> + GitHub Actions workflow `apply-handoff.yml` для автоматизации
> zip-handoff. Suite 323 passed. См.
> `obsidian/Changelog/2026-06-09-p0-1-3-codegen-and-actions.md` и
> `obsidian/UserGuide/github-actions-handoff.md` (setup PAT).
>
> Ниже — старая запись от 2026-06-08; обновится после merge P0.1.3.

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
