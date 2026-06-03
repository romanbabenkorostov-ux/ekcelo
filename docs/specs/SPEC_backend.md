# SPEC — Команда ekcelo (бэкенд: FastAPI + БД)

> Консистентность — через пакет `contracts/`. Веб-шов = **полный REST-рендеринг**:
> бэкенд — источник данных для фронта. **Кода в этой итерации не пишем — только
> DB-контракт, OpenAPI, ViewModel-схема и спеки.**

## Роль и контрактная поверхность

Импортирует Bundle в БД §1–§6, отдаёт **ViewModel** по REST, реэкспортирует Bundle,
хранит контракт ролей. Эмитит **C4** (REST/ViewModel), реэкспорт **C3**.
Потребляет **C2**, **C3**. Прод: timeweb, FastAPI + SQLite(локаль)/Postgres(масштаб) + S3.

## Текущее состояние

FastAPI cycle 5 — только оркестратор меморандумов (6 эндпоинтов lots/run/status/
artifacts); БД §1–§6 в `schema/`; нет импорта Bundle, каталога объектов, API
рендеринга, ролей; легаси `viewer/`.

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
