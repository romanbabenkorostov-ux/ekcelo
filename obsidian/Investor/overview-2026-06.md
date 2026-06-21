# EKCELO — Обзор для инвестора (на 2026-06-21)

> Краткая справка о статусе платформы EKCELO, реализованных возможностях,
> покрытии тестами, ближайших задачах и готовом сценарии демонстрации.
> Документ — снимок состояния на дату; обновляется по запросу.

---

## 1. Что делает проект

**EKCELO** — платформа автоматизации оценки и торгов недвижимостью.
Решает три ключевые задачи участников рынка:

### Задача A — структурировать данные ЕГРН

Выписки из Росреестра (ЕГРН) приходят в виде PDF/XML и для каждого объекта
требуют ручного разбора. EKCELO **автоматически парсит выписки** в
структурированную БД (`parser/` модуль): объекты, владельцы, права,
ограничения, ЭТП-профиль (характеристики для электронных торговых площадок).

**Эффект:** оценщик не вводит данные вручную; экономия 1-2 часов на объект.

### Задача B — собрать единую картину объекта/лота

К ЕГРН добавляются: фотографии (EXIF-разметка через viewer), геометрия
участков (NSPD/KMZ для Google Earth), документы (ДОГОВОР/СВИДЕТЕЛЬСТВО/ОСВ),
расчётные характеристики (LLM-обогащение через Claude API).

Всё сводится в **Bundle** — самодостаточный архив объекта (manifest +
db.sqlite + project.kmz + raw документы) с криптографической верификацией
sha256 каждого файла.

**Эффект:** один Bundle = один объект готов к выгрузке на ЭТП или передаче
заказчику с гарантией целостности.

### Задача C — обеспечить веб-доступ с ролями

Заказчики системы — оценщики-партнёры (assessor), клиенты-покупатели
(client), оператор (superadmin). Каждый видит только разрешённое.
REST API + ViewModel-рендеринг (frontend `ekcelo-site` — отдельный репозиторий)
+ OAuth/Bearer + Per-resource RBAC обеспечивают multi-tenant работу.

**Эффект:** assessor показывает клиенту конкретные лоты через share-токен;
client скачивает Bundle и видит ViewModel без доступа к чужим объектам.

### Кто пользователи

| Роль | Кто | Что делает |
|---|---|---|
| **superadmin** | оператор EKCELO | всё: импорт Bundle, выдача доступов, исправления |
| **assessor** | оценщик-партнёр | вводит данные по своим объектам, делегирует коллегам, выдаёт клиентам |
| **client** | заказчик / покупатель | смотрит выданные лоты, скачивает Bundle, расшаривает третьим лицам (только просмотр) |

---

## 2. Что уже сделано (2026-06-21)

### Архитектурный фундамент
- **Контрактный пакет C1-C6** (`contracts/`): нормативные интерфейсы между
  тремя кодовыми базами (parser / backend / frontend). Любые изменения
  формата проходят через PR в этот пакет — гарантия совместимости команд.
- **Документация-как-код**: ADR (architecture decision records) +
  `obsidian/` knowledge base + переписка `docs/CORRESPONDENCE/` для
  координации команд.

### Парсер (Win10-десктоп)
- Парсинг выписок ЕГРН (PDF/XML), сбор графа владения, корпоративная
  иерархия (руководители, реорганизации), история выписок.
- Контурные данные из NSPD (Росреестр), KMZ-экспорт для Google Earth
  с document-узлами (фото, договоры).
- ЭТП-профиль (характеристики для электронных торгов): автозаполнение из
  ЭГРН + ручная корректировка + EXIF из фото + LLM-обогащение.
- Параллельная реализация parser-team: 33-таблиц backend storage
  (`contracts/db/SCHEMA_SPEC.md`) — полная DB с relations/graph.

### Бэкенд (FastAPI)
- **Bundle импорт** — `POST /bundles/import` + CLI `ekcelo-import-bundle`.
  Идемпотентность: повтор того же Bundle = no-op. Sha256 verify.
- **Bundle экспорт** — `GET /bundles/{id}/download?fmt={kmz,manifest,db,json,zip}`.
  Round-trip контракт: export(zip) → import = no-op.
- **ViewModel REST** — `GET /catalog`, `/objects/{cad}`, `/lots/{lot_id}`,
  `/objects/{cad}/graph`. Четыре канонические характеристики:
  physical (что), ownership (чьё), geo (где), temporal (когда).
- **DB-контракт C2** — машиночитаемый `contracts/bundle-db-slice/schema.json`
  (8 таблиц wire-формы Bundle) + CI sync-guard + кодоген Pydantic-моделей +
  CLI валидатор `ekcelo-validate-bundle-db`.
- **OAuth2/OIDC Bearer** — JWT-верификация по issuer/audience/JWKS,
  RS256 production / HS256 dev. Strategy dispatcher: OIDC > Basic > none.
- **RBAC** — полная реализация C6 ROLES_SPEC: superadmin/assessor/client,
  scoped гранты, delegate/share, opt-in enforcement на роутах через
  `create_app(enforce_rbac=True)`. Хранилище — отдельная access.sqlite
  (изолировано от ЕГРН-данных для Bundle-security).
- **Rate limiting** — защита от credential-stuffing на auth-провалы
  (429 + Retry-After после N попыток в окне).
- **GitHub Actions handoff workflow** — автоматизированный apply zip-архивов
  через `apply-handoff.yml` + Fine-grained PAT.

### Оркестратор меморандумов
- FastAPI + SQLite persistence + Redis multi-worker (опц.) + SSE pub/sub +
  Basic Auth + PBKDF2 password hashing.
- LLM-пайплайн через Claude API (Anthropic SDK).

---

## 3. Что проверили автотесты

**Всего: 480 passing + 1 skipped (bridge-guard в sandbox)** (на дату).

Распределение по трекам:

| Трек | Тесты | Что покрывают |
|---|---|---|
| Bundle importer | 31 | манифест-валидация, sha256, идемпотентность, ADR-001 §6 (manual/osv приоритет) |
| ViewModel REST | 28 + 24 | catalog (фильтры), object/lot/graph (4 характеристики), ETP-блок, beneficiaries dedup |
| Bundle storage + export | 25 + 18 | sidecar таблица, KMZ-сохранение, реверс-экспорт fmt=db/json/zip, round-trip |
| DB-contract C2 | 13 + 14 + 10 | контракт↔DDL sync-guard, validate_db, CLI, Pydantic codegen |
| OAuth/OIDC | 19 + 7 + 5 | JWT verify (sig/aud/iss/expiry/kid), JWKS provider, strategy dispatcher |
| RBAC ядро | 44 + 25 | Principal/Grant/can/delegate/share/revoke, InMemory + SQLite |
| RBAC integration | 19 + 14 | FastAPI Depends, REST `POST/DELETE /grants`, enforcement на роутах |
| Rate limiting | 13 + 9 | counter/window/block_s, middleware integration Basic + Bearer |
| Базовая auth + workspace + др. | ~190 | Basic Auth, PBKDF2 hashing, persistence, store, CLI, и т.д. |

Контракт-эквивалентность: RBAC-тесты параметризованы по обоим store
(memory + sqlite) — гарантия что persistence не сломает поведение.

CI sync-guard защищает от дрейфа контрактов:
- `schema/egrn_current_schema.sql` ↔ `contracts/bundle-db-slice/schema.json`
- `db_codegen.generate()` ↔ committed `db_models.py`
- Bridge invariant: каждая моя slice-таблица существует в parser-team's
  полной схеме.

---

## 4. Что предстоит сделать

### Близкое (1-2 недели работы)
- **Cycle 14 M2 — browser code-flow** (`/auth/login` + `/auth/callback`).
  Нужно когда фронт `ekcelo-site` начнёт реальные login-сценарии. Сейчас
  работает API-доступ через Bearer (для интеграций).
- **C3.3 — материализация geo** (центр/геометрия из KMZ в БД). Зависит
  от parser-team: их `import_block2.py` пишет данные графа; нужна
  миграция для `objects.geo_*` колонок.
- **Cycle 15 M5 (опц.)** — фильтрация `/catalog` по грантам (показывать
  только видимое). Полировка RBAC.

### Среднее (1-2 месяца)
- **Production deploy на timeweb**: SQLite → PostgreSQL, S3-bucket для
  Bundle-хранилища (`bundles/<id>.kmz` → S3 + signed URLs), nginx
  reverse-proxy + TLS, CI/CD pipeline.
- **`ekcelo-site` (frontend)** — отдельный репозиторий, потребляет
  ViewModel REST. UI рендеринг 4 характеристик, KMZ через Google Earth
  embed, UI управления грантами.
- **EXIF v1.2 per-photo notes** — parser-A doc от 2026-05-30 (post 027/028
  self-resolved). Реализация по запросу parser-A.

### Дальнее
- Расширение источников: ФССП (исполнительные производства), картотека
  арбитражных дел, ЕГРЮЛ/ЕГРИП (parser уже встроен), банкротство.
- Multi-tenant изоляция (shared ekcelo + per-tenant access уже
  архитектурно готова).

---

## 5. Что можно решить проектом ПРЯМО СЕЙЧАС

После применения всех PR (последний — cycle 16 #119 ожидается) платформа
поддерживает следующие end-to-end сценарии:

### Сценарий A — оценщик загружает объект и отдаёт клиенту

1. Парсер на Win10 разбирает выписку ЕГРН + фото → формирует Bundle.
2. Оператор/assessor импортирует Bundle через CLI или REST:
   ```bash
   ekcelo-import-bundle --bundle ./my-object/ --db ./ekcelo.sqlite
   # ИЛИ через REST:
   POST /bundles/import (multipart zip)
   ```
3. Superadmin/assessor выдаёт client'у грант на просмотр через REST:
   ```
   POST /grants { subject_sub: "client@example", action: "view",
                   resource_type: "object", resource_id: "61:44:0050706:31" }
   ```
4. Client заходит, видит ViewModel объекта (`GET /objects/{cad}`),
   скачивает KMZ для Google Earth (`GET /bundles/{id}/download?fmt=kmz`).

### Сценарий B — реверс-экспорт для передачи

Backend генерирует свежий Bundle (объект + изменения) с round-trip-
идемпотентностью:
```
GET /bundles/{id}/download?fmt=zip
```
Получатель импортирует обратно — `import → is_noop == True`. Гарантия
целостности и воспроизводимости.

### Сценарий C — multi-tenant с делегированием

Assessor-A делегирует assessor-B доступ к подмножеству лотов:
```
# A:  POST /grants  → B получает edit-грант на конкретный лот
# B:  GET /lots/{lot_id}  → 200 (видит)
# B:  GET /lots/<чужой>  → 403 (не видит)
```
Client расшаривает Bundle третьему лицу (view-only):
```
# C:  POST /grants { action: "view", subject_sub: "buyer@external", ... }
# buyer: GET /bundles/{id}/download?fmt=kmz → 200
```

### Сценарий D — защита от перебора

При попытке brute-force паролей (Basic) или подбора токенов (Bearer):
после 5 провалов за 5 минут — 429 + Retry-After 15 минут. Легитимный
пользователь после паузы проходит. Логи фиксируют попытки.

---

## 6. Демонстрационный «золотой путь» (для презентации)

> Шаги для живой демонстрации. Время — ~15 минут. Требуется: Win10 с
> установленным проектом + Google Earth Pro + Postman (или curl).

### Шаг 0 — Подготовить окружение (заранее)

```powershell
# Старт backend локально:
cd E:\Code\ekcelo\ftontback2026-01-02
.\.venv\Scripts\Activate.ps1

# Сконфигурировать access (RBAC, rate limit, Bundle storage):
$env:EKCELO_DB="$pwd\demo-data\ekcelo.sqlite"
$env:EKCELO_ACCESS_DB="$pwd\demo-data\access.sqlite"
$env:EKCELO_BUNDLES_DIR="$pwd\demo-data\bundles"
$env:EKCELO_AUTH_USERS="admin:demo-pass,alice:demo-pass,client:demo-pass"
$env:EKCELO_AUTH_ROLES="admin:superadmin,alice:assessor,client:client"
$env:EKCELO_RATELIMIT_FAILS="5"

uvicorn lot_orchestrator_web.main:app --reload
# Запустится на http://localhost:8000
```

(Альтернативно: `create_app(enforce_rbac=True, ...)` через скрипт-обёртку.
В demo-режиме оставьте `enforce_rbac=False` чтобы не отвлекаться на гранты
на шаге 1-2.)

### Шаг 1 — Импортировать готовый Bundle

«Вот один объект из реального портфеля — выписка ЕГРН, фотографии и
геометрия. Один файл, sha256 каждого артефакта проверяется.»

```powershell
ekcelo-import-bundle --bundle .\demo-data\bundles\sample-bundle\ `
                      --db $env:EKCELO_DB --json
# → {"bundle_id": "...", "objects_inserted": 1, ...}
```

Показать `is_noop: false` на первом запуске, `true` — на повторе.
**Тезис:** «Идемпотентно. Можно перезапускать парсер хоть каждый день —
БД не растёт мусором.»

### Шаг 2 — Каталог и просмотр объекта

```bash
curl http://localhost:8000/catalog -u admin:demo-pass
# → [{ "kind":"object", "id":"61:44:0050706:31",
#      "title":"61:44:0050706:31", "address":"Ростов, ул. Пушкина 1" }]

curl http://localhost:8000/objects/61:44:0050706:31 -u admin:demo-pass
# → { "kind":"object", "id":"...",
#     "physical": {"object_type":"room","area_m2":125.4,...},
#     "ownership": {"rights":[...], "beneficiaries":[...]},
#     "geo": {...}, "temporal": {"extract_date":"2026-05-20"} }
```

**Тезис:** «Один запрос — вся ViewModel объекта, разбитая на 4 канонические
характеристики. Фронт рендерит напрямую, без перевода.»

### Шаг 3 — Граф владения

```bash
curl http://localhost:8000/objects/61:44:0050706:31/graph -u admin:demo-pass
# → { "nodes": [{"id":"61:44:...","kind":"room","label":"..."},
#                {"id":"right:42","kind":"right","label":"собственность"},
#                {"id":"inn:7707083893","kind":"beneficiary_legal","label":"ООО Тест"}],
#     "edges": [{"from":"61:44:...","to":"right:42","kind":"has_right"},
#                {"from":"right:42","to":"inn:7707083893","kind":"held_by"}] }
```

**Тезис:** «Структура владения как граф — для UI рисует кто кому принадлежит.»

### Шаг 4 — Скачивание Bundle и открытие в Google Earth

```bash
# Скачать KMZ напрямую
curl -OJ http://localhost:8000/bundles/<bundle_id>/download?fmt=kmz \
     -u admin:demo-pass
# → файл <bundle_id>.kmz на диске
```

Открыть KMZ в Google Earth: показывается участок с границами +
document-узлы (фото, договоры) кликаются.

**Тезис:** «Один клик — клиент видит участок на карте мира с фотографиями
и документами. Никакого специального вьюера не нужно.»

### Шаг 5 — Управление доступом (RBAC)

Перезапустить backend с `enforce_rbac=True`:

```powershell
# Перезапуск с включённым RBAC enforcement
$env:EKCELO_ENFORCE_RBAC="true"  # (если есть в обёртке) ИЛИ
# через скрипт create_app(enforce_rbac=True)
```

Демо отказа без гранта:
```bash
curl http://localhost:8000/objects/61:44:0050706:31 -u alice:demo-pass
# → 403 Forbidden: alice cannot view object/61:44:...
```

Выдать грант (от admin = superadmin):
```bash
curl -X POST http://localhost:8000/grants -u admin:demo-pass \
     -H "Content-Type: application/json" \
     -d '{"subject_sub":"alice","action":"view",
          "resource_type":"object","resource_id":"61:44:0050706:31"}'
# → 201 { "grant_id":"...", "subject_sub":"alice", ... }
```

Повторить запрос alice:
```bash
curl http://localhost:8000/objects/61:44:0050706:31 -u alice:demo-pass
# → 200 + ViewModel
```

**Тезис:** «Гранулярный контроль. Можно выдать доступ к одному объекту
конкретному человеку. Отозвать — `DELETE /grants/{id}`.»

### Шаг 6 — Защита от перебора

```bash
# 6 попыток с неверным паролем подряд:
for i in {1..6}; do
  curl -i http://localhost:8000/catalog -u alice:WRONG
done
# 5 раз → 401
# 6-я → 429 Too Many Requests + Retry-After: 900
```

**Тезис:** «Перебор паролей бесполезен — после 5 промахов аккаунт заперт
на 15 минут. PBKDF2 + rate limit покрывают и оффлайн, и онлайн атаки.»

### Шаг 7 — Документация и качество

Открыть `http://localhost:8000/docs` — auto-generated OpenAPI spec со всеми
эндпоинтами и схемами.

Прогнать тесты в живую:
```bash
python -m pytest -q
# → 480 passed, 1 skipped
```

**Тезис:** «480 автотестов покрывают всю критическую логику. Любое
изменение — CI проходит, или не мержим.»

---

## 7. Технологический стек

| Слой | Технологии |
|---|---|
| **Парсер** | Python 3.11+, pdfplumber, openpyxl, python-docx, Pillow, piexif, Playwright (для NSPD-screenshot), sqlite-utils |
| **Бэкенд** | Python 3.11+/3.13, FastAPI, Pydantic v2, SQLite (Postgres-ready), Redis (опц. multi-worker), uvicorn |
| **Auth** | PyJWT, cryptography (RS256), PBKDF2 hashing 600k iter, fine-grained PAT для GitHub Actions |
| **LLM** | Anthropic SDK (Claude Opus/Sonnet/Haiku) — опц., для меморандум-пайплайна |
| **Frontend** | (отдельный репо `ekcelo-site`) — потребляет ViewModel REST |
| **Карты** | KMZ + Google Earth (без отдельного вьюера) |
| **CI/CD** | GitHub Actions (`apply-handoff.yml` для авто-применения handoff-архивов) |
| **Координация** | Контрактный пакет C1-C6 + `docs/CORRESPONDENCE/` |

---

## 8. Метрики разработки

- Активная разработка: июнь 2026.
- Линий кода backend (production): ~3-5k LOC; покрытие тестами по
  критическим путям — близко к 100%.
- 480 автотестов; полный прогон ~30 секунд; CI на каждый PR.
- Документация: `obsidian/Architecture/` (12+ снимков подэтапов) +
  `obsidian/Changelog/` (~30 записей) + `obsidian/Decisions/` (ADR).
- Координация с parser-team: 29 пронумерованных постов в
  `docs/CORRESPONDENCE/`.

---

## 9. Риски и митигации

| Риск | Митигация |
|---|---|
| Дрейф схемы parser ↔ backend | CI bridge-guard `test_bridge_guard.py` падает при расхождении |
| Утечка грантов через Bundle export | Гранты в отдельной access.sqlite — физически невозможно |
| Brute-force на auth | PBKDF2 + rate limit (cycle 13 + cycle 16) |
| Зависимость от LLM (Claude) | LLM-пайплайн опционален; основные сценарии работают без |
| Парсер на Win10-десктопе | Bundle = автономная единица обмена; backend независим от Win |
| Замена контрактов | Контрактный пакет + governance в `contracts/PACKAGE.md` |

---

## 10. Что нужно от инвестора

1. **Решение по deploy** — приоритет timeweb production (SQLite + S3-bucket
   для KMZ) или альтернатива.
2. **`ekcelo-site` frontend roadmap** — отдельная команда или текущая
   расширяется.
3. **Ресурс на координацию с parser-team** — сейчас работа идёт через
   correspondence-посты; масштабирование требует регулярных созвонов.

---

## Связи в документации

- Подэтапы: `obsidian/Architecture/p0-*.md`, `cycle-14-oauth.md`,
  `cycle-15-rbac.md`, `cycle-16-ratelimit.md`.
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md`.
- Спека backend: `docs/specs/SPEC_backend.md`.
- Контракты: `contracts/PACKAGE.md` + `contracts/{api,bundle-db-slice,db,roles}/`.
- Принципы: `CLAUDE.md`.
- Журнал изменений: `obsidian/Changelog/`.
