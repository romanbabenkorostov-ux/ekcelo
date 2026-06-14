# Cycle 15 — RBAC (M1: core in-memory)

> Реализация `contracts/roles/ROLES_SPEC.md` (C6) — per-lot/object/bundle
> разграничение доступа. M1 — ядро (Principal/Grant/can/delegate/share) с
> in-memory хранилищем. M2 — SQLite `access_grants`. M3 — FastAPI
> `Depends(require(...))` + REST endpoints.

## Зачем

Cycle 14 M1 (OAuth) даёт «кто пришёл» (Subject из JWT). Cycle 15 M1 даёт
«что ему позволено»: трёхуровневая модель ролей (superadmin/assessor/client)
+ scoped-гранты на конкретные ресурсы (lot/object/bundle).

C6 фиксирует:
- **superadmin** — обходит все проверки.
- **assessor** — гранты scoped на лоты/объекты; может делегировать другому
  assessor (передача роли с подмножеством).
- **client** — read-only (view+export+share); может расшарить view-токен
  третьему лицу.

## Архитектура

```
oauth.Subject (cycle 14)
   │
   ▼  Principal.from_oauth_subject(...)
Principal(sub, roles={Role.ASSESSOR, ...})
   │
   ├──► can(principal, action, resource, store) → bool
   ├──► require(principal, ...)               → raises AuthorizationError
   ├──► delegate(grantor, grantee, action, resource, store)
   └──► share(sharer, recipient, resource, store)
              │
              ▼
        GrantStore (Protocol)
        ├─ InMemoryGrantStore (M1, тесты/dev)
        └─ SQLiteGrantStore  (M2, persistence)
```

## Поведение

### `can(principal, action, resource, store)`
1. **superadmin** в ролях → True (минует всё).
2. **client** без assessor-роли + action ∈ {input, edit, delegate} → False
   (C6 read-only enforcement).
3. Ищем активный (не истёкший) грант `(subject_sub, action, resource)` —
   action-grain: view-грант НЕ даёт edit, нужен явный edit-грант.
4. expires_at в прошлом → грант не действует.

### `delegate(grantor, grantee_sub, action, resource, store)`
- grantor должен быть assessor или superadmin.
- grantor сам должен мочь выполнить action над resource.
- Создаёт грант на имя grantee_sub с `granted_by=grantor.sub`.
- → grant_id.

### `share(sharer, recipient_sub, resource, store)`
- sharer должен быть client или superadmin.
- sharer должен видеть resource (`can(sharer, VIEW, ...)`).
- Создаёт фиксированный VIEW-грант для recipient (нельзя расшарить edit).
- → grant_id.

### `Revoke`
- `store.revoke(grant_id)` → True/False. Не-revocable гранты нельзя отозвать.
- После revoke `can(...) → False` для отозванного гранта.

### TTL (`expires_at`)
- Naive datetime трактуется как UTC (защита от типичной ошибки).
- expires_at в прошлом → грант истёк (как будто отозван).

## Что НЕ в M1

Будет в **M2**:
- `lot_orchestrator_web/rbac_store.py::SQLiteGrantStore` — реализация
  GrantStore поверх таблицы `access_grants`.
- Миграция `schema/migrations/0003_access_grants.sql`.
- CRUD-операции с persistence.

Будет в **M3**:
- FastAPI `Depends(require_action(...))` для роутов C4
  (`/catalog`, `/objects/{cad}`, `/lots/{lot_id}`).
- Эндпоинты `POST /grants`, `DELETE /grants/{id}`, `GET /grants/me`.
- Source Principal: для OIDC — из `request.state.subject` (cycle 14);
  для Basic Auth — статическая карта `EKCELO_AUTH_ROLES=alice:assessor,bob:client`.

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `lot_orchestrator_web/rbac.py` | ~280 | Role/Action/Resource/Principal/Grant/can/delegate/share |
| `lot_orchestrator_web/tests/test_rbac.py` | ~280 | 44 теста |

**Тесты:** 44 (cycle 15 M1); полный suite **398 pass** (354 + 44).

Покрытие:
- Principal.from_oauth_subject: extract known roles, ignore noise, empty.
- superadmin × все Action × все Resource → True (параметризованная матрица).
- client: hard-deny INPUT/EDIT/DELEGATE даже с грантом; VIEW с грантом
  работает; VIEW без гранта — отказ.
- assessor: action-grain (view-грант не даёт edit), scoped (LOT1 ≠ LOT2).
- delegate: success, fails если grantor не может, отвергает client,
  superadmin может всё делегировать.
- revoke: removes access, unknown returns False, non-revocable fails.
- share: создаёт view-only грант, fails если sharer не видит, отвергает
  assessor.
- TTL: expired denies, future allows, naive datetime → UTC.
- require: raises на отказ, проходит для superadmin.
- list_for_subject: фильтр по subject.

## Связи

- C6: `contracts/roles/ROLES_SPEC.md`.
- Предшественник: `obsidian/Architecture/cycle-14-oauth.md` (источник Principal).
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md` §Cycle 15.
- DB-контракт (для M2): добавим `access_grants` как §7 sidecar (НЕ в ЕГРН §1-§6).

## Triggers (по roadmap C6)
OAuth (cycle 14) приземлён ✅ ИЛИ появление assessor/client сценария.
