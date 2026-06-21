# SPEC — Команда ekcelo (бэкенд: FastAPI + БД)

> Консистентность — через пакет `contracts/`. Веб-шов = **полный REST-рендеринг**:
> бэкенд — источник данных для фронта. **Кода в этой итерации не пишем — только
> DB-контракт, OpenAPI, ViewModel-схема и спеки.**

## Роль и контрактная поверхность

Импортирует Bundle в БД §1–§6, отдаёт **ViewModel** по REST, реэкспортирует Bundle,
хранит контракт ролей. Эмитит **C4** (REST/ViewModel), реэкспорт **C3**.
Потребляет **C2**, **C3**. Прод: timeweb, FastAPI + SQLite(локаль)/Postgres(масштаб) + S3.

## Текущее состояние (на 2026-06-14)

**P0 контрактного пакета — закрыто. P1 auth-трек начат (cycle 14 M1).** В `main`:
- ✅ **P0.2 импортёр Bundle** (PR #104): `POST /bundles/import` + CLI
  `ekcelo-import-bundle`; идемпотентный импорт §1..§6 + ЭТП §6, ADR-001
  manual/osv-приоритет, sha256 verify.
- ✅ **P0.3 ViewModel REST C4** (PR #105/#106): `GET /catalog`,
  `/objects/{cad}`, `/lots/{lot_id}`, `/objects/{cad}/graph`; 4 канонические
  характеристики physical/ownership/geo/temporal. См. `obsidian/Architecture/
  p0-viewmodel.md`.
- ✅ **P0.3.3 Bundle storage + reverse-export** (PR #107/#108): sidecar
  таблица `bundles`, KMZ-хранилище, `GET /bundles/{id}/download?fmt=` для
  kmz/manifest/db/json/zip. Round-trip контракт C3 зелёный
  (export(zip)→import=no-op). См. `p0-bundle-storage.md`, `p0-bundle-export.md`.
- ✅ **P0.1 DB-контракт C2** (PR #109+#110+#113):
  - P0.1.1 — машиночитаемый `contracts/db/schema.json` + `validate_db` + CI
    sync-guard schema.sql ↔ contract.
  - P0.1.2 — `validate_schema` в `import_bundle` (early-fail 422) + CLI
    `ekcelo-validate-bundle-db` для parser-team.
  - P0.1.3 — Pydantic codegen из контракта + GitHub Actions
    `apply-handoff.yml` для автоматизации zip-handoff.
  - См. `p0-db-contract.md`.
- ✅ **Cycle 14 M1 OAuth/OIDC** (PR #114): Bearer-JWT верификация +
  `OAuthMiddleware` + strategy dispatcher (OIDC > Basic > none).
  Реализует частично C6 ROLES_SPEC. См. `cycle-14-oauth.md`.
- ✅ **Cycle 15 M1 RBAC** (PR #115): Principal/Grant/can/delegate/share +
  InMemoryGrantStore. 44 теста. См. `cycle-15-rbac.md`.
- 🟡 **Cycle 15 M2 RBAC SQLite** (готов локально, zip-handoff):
  `SQLiteGrantStore` поверх отдельной access.sqlite (НЕ ekcelo.sqlite —
  ADR-001 + Bundle security). Миграция
  `schema/migrations/access/0001_access_grants.sql`. 25 тестов
  (параметризованных по обоим store). См. `cycle-15-rbac.md`.
- 🟡 **Bridge namespace split** (готов локально, zip-handoff):
  `contracts/db/schema.json` → `contracts/bundle-db-slice/schema.json` —
  разделение моей 8-таблиц wire-slice от parser-team's 33-таблиц backend
  storage в `contracts/db/`. Post 029 + bridge-guard тест. См.
  `docs/CORRESPONDENCE/029-backend-bundle-db-slice-namespace.md`.
- 🟡 **Cycle 15 M3 RBAC FastAPI** (готов локально, zip-handoff):
  `require_action` dependency (opt-in) + REST `POST/DELETE /grants` +
  `GET /grants/me`. 19 тестов. Wire-up в боевые роуты — M4. См.
  `cycle-15-rbac.md`.

**Остаётся опциональным/отложенным:**
- C3.3 — materialization `geo` (KMZ→БД). **Отложен**, не блокирует фронт.
- P0.1.4 — мапа богатой parser-схемы → interchange. Опц.
- Cycle 14 M2 — `/auth/login` + `/auth/callback` browser code-flow.
- Cycle 15 M4 — enforcement wire-up в роуты (`create_app(enforce_rbac=True)`)
  + Basic Auth roles-карта `EKCELO_AUTH_ROLES`.
- Cycle 16 — Rate limiting на auth-провалы.

См. `obsidian/Architecture/roadmap-2026-06.md` для приоритетов.

Старое описание (для истории): FastAPI cycle 5 — только оркестратор
меморандумов (6 эндпоинтов lots/run/status/artifacts); БД §1–§6 в `schema/`;
нет импорта Bundle, каталога объектов, API рендеринга, ролей; легаси `viewer/`.

## Целевое состояние

REST-бэкенд — источник данных для веб-фронта + пайплайн-оркестратор.

## Рабочие треки

### P0
1. **DB-контракт C2.** Привести `schema/egrn_current_schema.sql` к нормативной
   §1–§6, синхронной с `egrn_parser/db/schema.sql`; расхождения свести (миграции
   только через `schema/migrations/`). Машиночитаемая выжимка → `contracts/db/`.
   Dual-target SQLite↔Postgres (JSON1↔JSONB) — зафиксировать соответствие типов.
2. **Импортёр Bundle (главный новый модуль).** `POST /bundles/import` + локальный
   CLI `ekcelo-import-bundle`: валидирует `manifest.json` по C3, грузит
   `db.sqlite`→БД идемпотентно (upsert по `cad_number`/`content_hash`, паттерн
   `merge/upsert.py`), регистрирует KMZ в S3/локально, индексирует §6. Повтор
   импорта того же Bundle — no-op.
3. **ViewModel + REST C4.** `contracts/api/openapi.yaml` + `viewmodel.schema.json`.
   Эндпоинты: `GET /catalog`, `GET /objects/{cad}` → ViewModel (4 характеристики),
   `GET /lots/{lot_id}` → ViewModel лота, `GET /objects/{cad}/graph`,
   `GET /bundles/{id}/download?fmt=`. ViewModel — единственная нормализованная форма.

### P1
4. **Реэкспортёр Bundle.** Обратная сборка Bundle из БД (зеркало трека 2) —
   замыкает round-trip и реализует «отдай БД по моему объекту/лоту»
   (db/json/kmz или полная папка с raw).
5. **Контракт ролей C6.** `contracts/roles/ROLES_SPEC.md`: superadmin / assessor
   (+делегирование) / client (+передача просмотра); объекты доступа, действия,
   share-token поверх `tokens.js`. **Реализация — после веб-шва.**

### P2
6. **Оркестратор.** Меморандум-пайплайн (lot_orchestrator) подключить к каталогу:
   меморандум/контракты (golden path 09–13) как артефакты лота через
   `GET /lots/{id}/artifacts`.
7. **Инфра прод.** SQLite→Postgres через `core/config`; S3-раскладка bundle
   (`s3://…/<lot>/<cad>/<extract_date>/`); Cloudflare worker наследуется от фронта.

## Точки стыковки

| Потребляет | От кого | Эмитит | Кому |
|------------|---------|--------|------|
| C2, C3 | parser (Bundle) | C4 REST/ViewModel | frontend |
| — | — | реэкспорт C3 | заказчик/локаль |

## Definition of Done

импорт Bundle vN → `GET /objects/{cad}` отдаёт ViewModel, валидную по
`viewmodel.schema.json`; реэкспорт даёт идемпотентный Bundle (round-trip тест в
`backend/tests/`); OpenAPI опубликован в `contracts/`.
