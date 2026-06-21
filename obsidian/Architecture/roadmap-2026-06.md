# Roadmap: циклы 14-16 + EXIF v1.2 (на 2026-06-03)

> Чёткие планы следующих циклов разработки orchestrator-стека и parser-стороны. Каждый цикл готов к подхвату другой командой. Источник истины по кросс-командным контрактам — пакет `contracts/` (C1-C6); этот roadmap НЕ переопределяет контракты, а указывает, какой контракт реализует каждый цикл.

## Контекст и точка опоры

На 2026-06-03 в `main`:
- **Orchestrator** доведён до cycle 13 (см. таблицу в `lot-orchestrator.md`): CLI MVP + FastAPI web + SQLite persistence + Redis multi-worker + SSE pub/sub + Basic Auth + **PBKDF2 password hashing**.
- **Contracts package** (`contracts/`, от PR #98): C1 KMZ, C2 DB, C3 Bundle, C4 REST/ViewModel, C5 Lot, C6 Roles. Это нормативные контракты для трёх кодовых баз (parser / backend / frontend).
- **Team specs**: `docs/specs/SPEC_{parser,backend,frontend}.md`.

Следующие циклы делятся на два трека:
- **Auth-трек** (14/15/16) — эволюция безопасности web-бэкенда, реализует частично C6 ROLES_SPEC.
- **Parser-трек** (EXIF v1.2) — закрывает post 027/028 (self-resolved ack).

> ⚠️ Важно: пакет `contracts/` ввёл бóльшую цель — **REST-шов + Bundle** (C3/C4) и deprecated `viewer/` в пользу `ekcelo-site`. Auth-трек (14-16) совместим с этой целью (auth нужен и текущему orchestrator-web, и будущему REST-бэкенду), но **приоритет P0 по SPEC_backend** — это DB-контракт C2, импортёр Bundle, ViewModel REST C4. Auth-трек — P1+. Координируйте порядок с владельцем репозитория.

## P0.2 Bundle importer — статус подэтапов

| Подэтап | Что | Статус |
|---|---|---|
| **A** | Pydantic-схема манифеста C3 + `load_manifest` + `verify_files` + идемпотентный `import_bundle(bundle, target_db, dry_run=…)`. Уважает ADR-001 §6 (manual/osv не перезатирается). | ✅ done (2026-06-03; см. `p0-bundle-importer.md`) |
| **B** | REST `POST /bundles/import` (multipart zip, 8 тестов) + CLI `ekcelo-import-bundle` (7 тестов, exit codes 0/2/3/4) + `pyproject.scripts`. Регистрация KMZ в локальном хранилище — отложена до C. | ✅ done (2026-06-03; те же 4 файла + `bundle_cli.py` + `_find_bundle_root` helper) |
| **C1** (= P0.3.1) | ViewModel ядро + `GET /catalog` + `GET /objects/{cad}` (4 характеристики). 28 тестов. | ✅ done (2026-06-08; см. `p0-viewmodel.md`) |
| **C2** (= P0.3.2) | `GET /lots/{lot_id}` + `GET /objects/{cad}/graph` (узлы/рёбра, graph_node_id из C1-контракта). 24 теста. | ✅ done (2026-06-08; см. `p0-viewmodel.md`) |
| **C3.1** (= P0.3.3.1) | Sidecar `bundles` table + KMZ-storage + `GET /bundles/{id}/download?fmt={kmz,manifest}` + расширение `POST /bundles/import` (возвращает `bundle_id`). 25 тестов. | ✅ done (2026-06-08; см. `p0-bundle-storage.md`) |
| **C3.2** (= P0.3.3.2) | Реверс-экспорт `fmt={zip,db,json}` — round-trip Bundle из БД. 18 тестов. | ✅ done (2026-06-08; см. `p0-bundle-export.md`) |
| **C3.3** (= P0.3.3.3) | Материализация `geo` (центр/геометрия из KMZ в БД). Зависит от parser-team. | план (отложено, не блокирует) |
| **P0.1.1** | DB-контракт C2 — машиночитаемая схема `contracts/db/schema.json` + `validate_db` + CI sync-guard. 13 тестов. | ✅ done (2026-06-08; см. `p0-db-contract.md`) |
| **P0.1.2** | Интеграция `validate_db` в `import_bundle` (`validate_schema` flag, early-fail 422 + `schema_violations[]`) + CLI `ekcelo-validate-bundle-db`. 14 тестов. | ✅ done (2026-06-08; см. `p0-db-contract.md`) |
| **P0.1.3** | Кодогенерация Pydantic-моделей из `contracts/db/schema.json` + CI sync-guard codegen↔contract + CLI `ekcelo-db-codegen` + GitHub Actions workflow `apply-handoff.yml`. 10 тестов. | ✅ done (2026-06-09) |
| **P0.1.4** | Опц.: мапа `parser/egrn_parser/db/schema.sql` (богатая) → `contracts/db/schema.json` (interchange). Для parser-team. | план |

---

## Cycle 14 — OAuth2 / OIDC (token-based auth)

**Статус:** **M1 ✅ done** (2026-06-14, см. `cycle-14-oauth.md`) — Bearer-JWT verifier + OAuthMiddleware + strategy dispatcher (OIDC > Basic > none). 31 тест. M2 (`/auth/login` + `/auth/callback` browser flow) и M3 (RBAC поверх Subject.roles, cycle 15) — план. **Реализует:** C6 ROLES_SPEC «OAuth/JWT — будущий триггер». **Триггер:** появление >2 пользователей ИЛИ внешний (не-LAN) доступ ИЛИ требование SSO.

### Зачем
Basic Auth (cycle 12-13) хранит креды в env — годится для пары операторов за reverse-proxy, но не для multi-tenant с ролями assessor/client (C6). OAuth2/OIDC даёт: внешний IdP (Keycloak/Authentik/Google), refresh-токены, отзыв сессий, готовую интеграцию с ROLES.

### Scope
1. `lot_orchestrator_web/oauth.py`: OIDC code-flow через `authlib` (опциональная зависимость в extras `[orchestrator-oauth]`).
2. Middleware-альтернатива `BasicAuthMiddleware`: `OAuthMiddleware` проверяет Bearer-JWT (подпись по JWKS IdP), извлекает `sub` + `roles` claim.
3. Конфиг через env: `EKCELO_OIDC_ISSUER`, `EKCELO_OIDC_CLIENT_ID`, `EKCELO_OIDC_AUDIENCE`, `EKCELO_OIDC_JWKS_URL`.
4. Выбор auth-стратегии в `create_app(...)`: если задан OIDC-issuer → OAuth; иначе если `EKCELO_AUTH_USERS` → Basic; иначе no-auth.
5. `/auth/login` redirect + `/auth/callback` для browser-flow; для API — прямой Bearer.

### Не в scope
- Собственный IdP (используем внешний).
- Хранение пользователей в БД (это backend C2/C6, не orchestrator-web).

### Тесты
- JWT verify happy/expired/wrong-signature/wrong-audience (через подменный JWKS).
- Стратегия-диспетчер: OIDC > Basic > none.
- Mock IdP через локальный JWKS (RS256 keypair в фикстуре).

### Зависимости
`authlib>=1.3` (+ `cryptography`), opt-in extras. Без extras OAuth недоступен, Basic Auth работает как раньше.

### Acceptance
`pytest` зелёный; запуск с `EKCELO_OIDC_ISSUER=...` принимает валидный Bearer и режет невалидный; Basic Auth не сломан (regression).

---

## Cycle 15 — Per-lot RBAC (реализация C6 ROLES_SPEC)

**Статус:** **✅ ЗАКРЫТ M1+M2+M3+M4** (2026-06-21, см. `cycle-15-rbac.md`) — M1 (ядро can/delegate/share, 44 теста), M2 (SQLiteGrantStore в отдельной access.sqlite, 25 тестов), M3 (FastAPI `require_action` + REST `/grants`, 19 тестов), M4 (enforcement на боевых роутах через `create_app(enforce_rbac=True)` + Basic Auth roles-карта `EKCELO_AUTH_ROLES`, 14 тестов). **C6 ROLES_SPEC реализован целиком.** Опц. расширение M5 (фильтрация /catalog по грантам). **Реализует:** `contracts/roles/ROLES_SPEC.md` (C6) целиком.

### Зачем
C6 фиксирует роли (superadmin / assessor / client), действия (input/edit/view/export/delegate/share) и scoped-делегирование. Сейчас auth даёт «всё-или-ничего». Cycle 15 вводит привязку «кто что видит/правит» на уровне лота/объекта.

### Scope (строго по ROLES_SPEC)
1. **Модель доступа** `lot_orchestrator_web/rbac.py`:
   - `Subject(sub, role)` ← из JWT claims (cycle 14) или из статической карты (Basic Auth fallback).
   - `Grant(subject, action, resource_type, resource_id, granted_by, revocable)` — scoped-грант.
   - `can(subject, action, resource) -> bool` — проверка с учётом роли + грантов + делегирования.
2. **Хранилище грантов**: SQLite-таблица `access_grants` (миграция в `schema/migrations/`), синхронно с C2 DB-контрактом. Для orchestrator-web — отдельный SQLite или общий с backend (согласовать).
3. **Enforcement в эндпоинтах**: dependency `Depends(require(action, resource))` на каждом route. Лот/объект, к которым нет гранта view → 403.
4. **Делегирование** (assessor→assessor) и **шеринг** (client→третье лицо) через `POST /grants` + `DELETE /grants/{id}` (revoke).

### Не в scope
- UI управления грантами (это frontend / ekcelo-site).
- Биллинг / квоты.

### Тесты
- Матрица ролей × действий × ресурсов (из ROLES_SPEC таблицы).
- Scoped-делегирование: assessor A грантит assessor B доступ к подмножеству лотов; B видит только их.
- Revoke: после отзыва B → 403.
- superadmin обходит все проверки.
- client view-only: edit/input → 403.

### Зависимости
Нет новых (SQLite stdlib). Опирается на cycle 14 для `roles` claim (или статическую карту при Basic Auth).

### Acceptance
Матричные тесты зелёные; ResModel совпадает с ROLES_SPEC; 403 на чужой лот; делегирование+revoke работают.

---

## Cycle 16 — Rate limiting на auth-провалы

**Статус:** план. **Реализует:** hardening (не привязан к C-контракту). **Триггер:** деплой с внешним доступом ИЛИ обнаружение brute-force в логах.

### Зачем
Cycle 13 защитил от offline-brute-force (PBKDF2 600k). Но online credential-stuffing (множество 401-попыток) не ограничен. Нужен throttle.

### Scope
1. `lot_orchestrator_web/ratelimit.py`: счётчик неудачных auth по ключу (IP + username).
   - In-memory (single worker) ИЛИ Redis-counter (multi-worker — переиспользует `redis_store` соединение).
   - Окно: N провалов за T секунд → 429 с `Retry-After`.
2. Интеграция в `BasicAuthMiddleware` / `OAuthMiddleware`: при провале `verify` инкремент; при превышении — 429 до истечения окна.
3. Конфиг: `EKCELO_RATELIMIT_FAILS` (default 5), `EKCELO_RATELIMIT_WINDOW_S` (default 300), `EKCELO_RATELIMIT_BLOCK_S` (default 900).

### Не в scope
- WAF / DDoS-защита (это reverse-proxy / CDN).
- Distributed rate limiting за пределами одного Redis.

### Тесты
- N провалов → 429; успешный логин сбрасывает счётчик.
- Окно истекает → снова можно.
- Redis vs in-memory backend (через fakeredis).
- Retry-After header корректен.

### Зависимости
Нет новых (Redis опционален, fallback in-memory).

### Acceptance
6-й провал за окно → 429; легитимный пользователь после паузы проходит; regression auth-тестов зелёный.

---

## EXIF v1.2 — per-photo `note` (parser-сторона)

**Статус:** план (ack получен self-resolved в post 028). **Реализует:** bump `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 → v1.2. **Триггер:** готовность parser-A; не блокирует ничего.

### Зачем
Stage 6 ETL EXIF сводит фото в `extras.advantages[]` (категории), но per-фото заметки экономиста («трещина по фасаду») теряются. Post 028 согласовал: добавить опциональное `note` в EXIF UserComment, агрегировать в `extras.notes`.

### Решённые в post 028 опции (autoaccept)
1. Имя поля: **`note`** (строка, опц.).
2. Ввод: расширение `viewer/admin-etp-profile.html` (или ekcelo-site) БЕЗ записи в EXIF; через YAML-patch.
3. БД-таргет: **`extras.notes`** (join `« — фото: »`).
4. Stage 6: аддитивно собирает `note`-поля по `cad_number`.
5. Сроки: parser-A открывает PR когда удобно.

### Scope
1. `docs/EXIF_USERCOMMENT_SCHEMA.md`: bump v1.1 → v1.2, добавить `note` в payload `kind:"photo"` (аддитивно, опц.).
2. `parser/exporters/etp/etl_exif.py`: при наличии `note` в UserComment v1.2 — собрать по cad, join `« — фото: »`, merge в `object_etp_profile.extras.notes` (gap-fill: не перезатирать OSV/manual; concat с маркером).
3. `parser/scripts/pirushin_sosn_rocha_07_init_project_v*.py`: опционально писать `note` при наличии (для тех, кто правит EXIF сторонним инструментом).
4. Backward-compat: v1.1 JPG (без `note`) читаются как раньше; v1.2-парсер на v1.1 → `note=None`.

### Не в scope
- Структурированный `{text, author, ts}` (отложено до UX-кейса с авторством).
- Гранулярная таблица `object_etp_photo_notes` (отложено).

### Тесты
- v1.2 JPG с `note` → `extras.notes` содержит текст с маркером.
- v1.1 JPG (без `note`) → поведение v1.1 (regression).
- Идемпотентность: повторный прогон не дублирует.
- Приоритет: OSV `extras.notes` не перезатирается, concat'ится.

### Зависимости
Нет новых (piexif уже в `[egrn-full]`).

### Acceptance
Smoke `etl_exif` зелёный; v1.2-фото даёт notes; v1.1 без регрессий; `EXIF_USERCOMMENT_SCHEMA.md` помечен v1.2.

---

## Порядок и зависимости

```
EXIF v1.2 ──────────────── независим (parser-A, в любой момент)

Cycle 14 (OAuth) ──┐
                   ├──► Cycle 15 (RBAC, нужен roles claim из 14)
Cycle 16 (rate)  ──┘ независим от 15, но логичнее после 14
```

- **EXIF v1.2** — можно брать сразу, параллельно всему.
- **Cycle 14 → 15** — последовательно (15 нужен `roles` из 14; при Basic Auth fallback 15 работает на статической карте ролей).
- **Cycle 16** — независим, но желательно после 14 (чтобы throttle покрывал оба middleware).

> Напоминание о приоритете: по `docs/specs/SPEC_backend.md` **P0 — это C2 DB-контракт + импортёр Bundle + ViewModel REST (C4)**, а не auth-трек. Если ресурс один — сначала P0 контрактного пакета, потом auth-трек. Этот выбор — за владельцем репозитория.

## Связи

- Контракты: `contracts/PACKAGE.md`, `contracts/roles/ROLES_SPEC.md` (C6).
- Team-спеки: `docs/specs/SPEC_{parser,backend,frontend}.md`.
- Текущее состояние orchestrator: `obsidian/Architecture/lot-orchestrator.md`.
- Передача другой команде: `obsidian/Architecture/handoff-onboarding.md`.
- Correspondence по EXIF: `docs/CORRESPONDENCE/027-*.md`, `028-*.md`.
