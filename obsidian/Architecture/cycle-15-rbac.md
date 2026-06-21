# Cycle 15 — RBAC (M1 + M2 + M3)

> Реализация `contracts/roles/ROLES_SPEC.md` (C6). M1 ядро (Principal/Grant/
> can/delegate/share + InMemoryGrantStore), M2 SQLite persistence в отдельной
> access.sqlite, M3 FastAPI integration (Depends factory + REST grant-endpoints).
> M4 (enforcement на существующих роутах) — следующий sub-stage.

## Зачем

Cycle 14 M1 OAuth даёт «кто пришёл». Cycle 15 даёт «что позволено»:
трёхуровневая модель ролей + scoped-гранты на конкретные ресурсы.

## Архитектура (M1+M2)

```
oauth.Subject (cycle 14)
   │
   ▼  Principal.from_oauth_subject(...)
Principal(sub, roles)
   │
   ├──► can(principal, action, resource, store) → bool
   ├──► require(...)
   ├──► delegate(grantor, grantee_sub, action, resource, store)
   └──► share(sharer, recipient_sub, resource, store)
              │
              ▼
        GrantStore Protocol
        ├─ InMemoryGrantStore    (M1, тесты/dev)
        └─ SQLiteGrantStore       (M2, отдельная access.sqlite)
              │
              ▼
        access.sqlite (НЕ ekcelo.sqlite!)
        путь: env EKCELO_ACCESS_DB или create_app(access_db=...)
        миграция: schema/migrations/access/0001_access_grants.sql
```

## Поведение (M1)

См. полное описание M1 в этом файле выше (Role/Action/ResourceType,
superadmin bypass, client read-only, action-grain гранты, delegate/share
с двойной проверкой, TTL).

## Поведение (M2 — SQLite)

### Зачем отдельная access.sqlite

Решение принято в обсуждении после M1 (см. post 029 для parser-team):

- **ADR-001 строго соблюдается**: «БД = слепок ЕГРН + ЭТП-профиль» (ekcelo.sqlite).
  Access — отдельная категория данных, в ту же БД не смешивается.
- **Bundle security by construction**: Bundle export не может физически
  утечь гранты — они в другой БД. Если бы access_grants был §7 в
  ekcelo.sqlite, каждый новый формат экспорта (db/zip/json) был бы
  обязан явно исключать §7. Один пропуск = утечка. Раздельные БД устраняют
  риск механически.
- **Multi-tenant ready**: shared ekcelo + per-tenant access — работает «даром».
- **Industry standard**: Cognito/Auth0/Keycloak всегда отдельны от app DB.

### Конфигурация

| Способ | Описание |
|---|---|
| `EKCELO_ACCESS_DB=/var/lib/ekcelo/access.sqlite` | env, для production |
| `create_app(access_db=Path("..."))` | явный override, для тестов |
| отсутствует | `app.state.grant_store = None`; M3 wire-up в роуты пропускается |

### Миграция

`schema/migrations/access/0001_access_grants.sql` — отдельный поднамеспейс
от ekcelo.sqlite миграций (`schema/migrations/0001_etp_profile.sql`,
`0002_bundles.sql`). Lazy-инициализация при создании SQLiteGrantStore.

Схема таблицы (см. файл миграции):
```
access_grants (
  grant_id TEXT PK, subject_sub, action, resource_type, resource_id,
  granted_by, revocable, expires_at, created_at
)
+ idx_lookup (subject_sub, action, resource_type, resource_id)
+ idx_subject (subject_sub)
```

### Контракт-эквивалентность

Тесты в `test_rbac_store.py` параметризованы `@pytest.fixture(params=["memory","sqlite"])`.
Те же 8 контрактных тестов проходят на обоих store — гарантия что замена
in-memory→SQLite ничего не ломает.

### Persistence-специфичные тесты

- `test_sqlite_persistence_survives_reopen` — данные переживают перезапуск
  процесса.
- `test_sqlite_creates_parent_dirs` — `access_db` может указывать на пока
  не существующий путь.
- `test_sqlite_schema_has_indices` — миграция создала индексы.

## Файлы и тесты

| Файл | LOC | Подэтап |
|---|---|---|
| `lot_orchestrator_web/rbac.py` | ~280 | M1 |
| `lot_orchestrator_web/tests/test_rbac.py` | ~280 | M1 (44 теста) |
| `lot_orchestrator_web/rbac_store.py` | ~150 | M2 |
| `lot_orchestrator_web/tests/test_rbac_store.py` | ~200 | M2 (25 тестов) |
| `schema/migrations/access/0001_access_grants.sql` | ~30 | M2 |
| `lot_orchestrator_web/main.py` | +5 | M2 (access_db param) |

**Тесты M1+M2:** 44 + 25 = 69; полный suite **423 pass**
(354 после cycle 14 + 44 M1 + 25 M2).

## Поведение (M3 — FastAPI integration)

`lot_orchestrator_web/rbac_api.py`:

### `get_principal(request) → Principal`
Извлекает Principal из `request.state.subject` (cycle 14 OAuth). Если subject
отсутствует — anonymous (`sub=""`, roles пусто).

### `require_action(action, resource_type, id_param) → Depends`
Фабрика FastAPI-dependency. **Opt-in enforcement**:
- `app.state.grant_store is None` → пропускает (backward-compat).
- иначе строит `Resource` из path-параметра `id_param`, проверяет `can()`,
  отказ → `403`.

Использование (M4):
```python
@app.get("/objects/{cad}",
         dependencies=[Depends(require_action(Action.VIEW,
                               ResourceType.OBJECT, "cad"))])
```

### Grant-management endpoints (`register_grant_routes`)
| Метод | Путь | Описание |
|---|---|---|
| POST | `/grants` | Выдать грант. assessor/superadmin → delegate; client+view → share. 201/403/503 |
| DELETE | `/grants/{grant_id}` | Отозвать. Только автор (granted_by) или superadmin. 204/403/404/409 |
| GET | `/grants/me` | Список грантов текущего Principal. 200 |

Все требуют сконфигурированного `grant_store` (иначе 503).

POST логика по C6:
- `action=view` + роль client (без assessor/superadmin) → `share()` (view-only).
- иначе → `delegate()` (grantor должен иметь роль + сам мочь action).

## Что НЕ в M1+M2+M3

Будет в **M4**:
- Wire-up `Depends(require_action(...))` в существующие роуты (`/catalog`,
  `/objects/{cad}`, `/lots/{lot_id}`, `/bundles/{bundle_id}/download`) —
  через opt-in флаг `enforce_rbac=True` в `create_app` (чтобы существующие
  425+ тестов без auth не сломались).
- Source Principal для Basic Auth — статическая карта `EKCELO_AUTH_ROLES`
  (`alice:assessor,bob:client`).

## Связи

- C6: `contracts/roles/ROLES_SPEC.md`.
- Cycle 14: `obsidian/Architecture/cycle-14-oauth.md` (источник Subject).
- ADR-001: `CLAUDE.md §3` (разделение ЕГРН/ЭТП vs access).
- Post 029: `docs/CORRESPONDENCE/029-backend-bundle-db-slice-namespace.md`.
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md`.
