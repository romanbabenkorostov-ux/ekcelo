# 2026-06-15 — Cycle 15 M2 + Bridge burst 1 + cleanup

## Что сделал

1. **Cycle 15 M2 — SQLite GrantStore** в отдельной access.sqlite (вариант B
   из обсуждения: ADR-001 + Bundle security).
2. **Bridge burst 1** — namespace-разделение моего slice от parser-team's
   full C2; post 029.
3. **Cleanup** — datetime.utcnow() → tz-aware (deprecation warning fix).

## Файлы (M2)
- ✨ `schema/migrations/access/0001_access_grants.sql` — DDL отдельной
  access.sqlite (поднамеспейс access/ от ekcelo миграций).
- ✨ `lot_orchestrator_web/rbac_store.py` — `SQLiteGrantStore` (~150 LOC).
- ✨ `lot_orchestrator_web/tests/test_rbac_store.py` — 25 тестов,
  параметризованных по обоим store (`memory|sqlite`) для контракт-
  эквивалентности + persistence-специфичные.
- ✏️ `lot_orchestrator_web/main.py` — `+access_db` параметр + env
  `EKCELO_ACCESS_DB` + создание `app.state.grant_store` (или None).

## Файлы (Bridge burst 1)
- 🔀 `contracts/db/schema.json` → `contracts/bundle-db-slice/schema.json`
  (git mv).
- 🔀 `contracts/db/DB_SPEC.md` → `contracts/bundle-db-slice/SLICE_SPEC.md`.
- ✏️ `backend/app/services/db_contract.py` — `_CONTRACT_PATH` обновлён.
- ✏️ `backend/app/services/db_codegen.py` — docstrings + CLI описание.
- ✏️ `backend/app/services/bundle.py` — docstring (validate_schema путь).
- ♻️ `backend/app/services/db_models.py` — регенерирован (новый источник
  в header, sha-марка контракта пересчитана).
- ✨ `backend/tests/test_bridge_guard.py` — soft-guard: каждая slice-
  таблица должна существовать в `contracts/db/SCHEMA_SPEC.md` ИЛИ
  `models.py` parser-team. Skip если файлы отсутствуют (свежий клон).
- ✨ `docs/CORRESPONDENCE/029-backend-bundle-db-slice-namespace.md` —
  информационный пост parser-team (стиль (в): no action required от них).
- ✏️ `docs/CORRESPONDENCE/INDEX.md` — добавлены строки 028 + 029.

## Файлы (cleanup)
- ✏️ `lot_orchestrator_web/tests/test_rbac.py` — `datetime.utcnow()` →
  `datetime.now(timezone.utc).replace(tzinfo=None)` (deprecation fix).

## Файлы (docs)
- ✏️ `obsidian/Architecture/cycle-15-rbac.md` — обновлён под M1+M2.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — cycle 15 M2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live.
- ✏️ `docs/specs/SPEC_backend.md` — актуализирован.

## Тесты
- 25 новых M2 + 3 bridge-guard (2 pass + 1 soft-skip в sandbox).
- Полный suite в sandbox: **423 passed** (398 + 25 M2).
- На вашем main: ожидается 423 passed + bridge-guard prove (parser-team
  файлы есть → match по 8 таблицам в их SCHEMA_SPEC.md/models.py).

## Решения

- **Отдельная access.sqlite (вариант B)**. Главный аргумент — Bundle
  security: гранты физически не могут утечь через export. ADR-001 сохранён
  чисто. Multi-tenant ready без рефактора. Industry-standard паттерн
  (Cognito/Auth0/Keycloak).
- **`schema/migrations/access/` поднамеспейс**. Чтобы не путать с
  ekcelo.sqlite миграциями (`0001_etp_profile.sql`, `0002_bundles.sql`).
  Lazy-инициализация: миграция применяется при первом обращении к
  `SQLiteGrantStore`.
- **`@pytest.fixture(params=["memory","sqlite"])`** — параметризация
  тестов даёт контракт-эквивалентность бесплатно. Те же 8 тестов прогоняют
  обе реализации.
- **Bridge burst 1: rename, не copy**. `git mv` сохраняет историю файлов;
  parser-team увидит чистый «move» в diff.
- **Bridge-guard как soft test** (skip если parser-team файлы отсутствуют).
  Это даёт graceful degradation: тест зелёный на свежем клоне без их
  работы (CI всегда зелёный), но на main у пользователя prove-mode.
- **Post 029 стиль (в) information**. Самый низкий conflict-risk: я
  сообщаю что сделал, не прошу одобрения, не требую действий. Если у них
  возражения — открыт post 030.

## Канал доставки
- Sandbox-proxy блокирует push — zip-handoff.
- После merge cycle 14 (#114) и cycle 15 M1 (#115) — apply этот архив.

## Следующий шаг
1. Применить архив, открыть PR.
2. После merge — обсудить:
   - **M3** — FastAPI Depends + REST endpoints `POST /grants` etc.
   - Параллельно — наблюдать реакцию parser-team на post 029 (если будет).
