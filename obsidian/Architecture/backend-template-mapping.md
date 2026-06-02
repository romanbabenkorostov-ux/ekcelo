# Backend layout mapping: fastapi-template ↔ ekcelo

> Зеркало шаблона [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) в папке `backend/app/`. Re-export'ы без логики; реальный код остаётся в `lot_orchestrator/`, `lot_orchestrator_web/`, `parser/`.

## Маппинг

```
fastapi-template                           ekcelo                                                Что
─────────────────────────────────────────────────────────────────────────────────────────────────
backend/app/main.py                  →     lot_orchestrator_web/main.py                          FastAPI app + create_app
backend/app/api/deps.py              →     lot_orchestrator_web/store.py::get_store              Depends(get_store)
backend/app/api/v1/<endpoint>.py     ⚠️    _register_routes(app) внутри main.py                  Routes (один файл, не разбит)
backend/app/core/config.py           →     lot_orchestrator/config.py::Settings                  env-конфигурация
backend/app/core/security.py         →     lot_orchestrator_web/auth.py (PR #93)                 Basic Auth middleware (lazy import)
backend/app/core/persistence.py      →     lot_orchestrator_web/persistence.py (PR #90)          SQLite snapshot (lazy proxy)
backend/app/crud/runs.py             →     lot_orchestrator_web/store.py                         RunStore, Run, get_store
backend/app/models/schemas.py        →     lot_orchestrator/schemas.py                           Pydantic v2 SSOT
backend/app/services/orchestrator.py →     lot_orchestrator/state_machine.py::run_pipeline       4-фазный pipeline
backend/app/services/llm.py          →     lot_orchestrator/llm_client.py                        Protocol + Anthropic + Mock
backend/alembic/                     ⚠️    schema/migrations/*.sql                               Stub vs ручные SQL миграции
backend/tests/                       →     lot_orchestrator{,_web}/tests/                        Direct тесты + 12 re-export check'ов
```

## Эквивалентность запуска

```bash
# Template-стиль:
uvicorn backend.app.main:app --reload

# Прямой канонический:
uvicorn lot_orchestrator_web.main:app --reload
```

Оба — тот же FastAPI app, одни и те же 6 routes, одна и та же конфигурация Settings.

## Отличия от шаблона (которые НЕ закрываются re-export'ом)

| Что | Template | ekcelo | Триггер изменения |
|---|---|---|---|
| ORM | SQLModel | sqlite3-direct + JSON | Решение о DB-миграции (ADR-003 тема 4) |
| Миграции | Alembic runtime | `schema/migrations/0001_*.sql` (ручные) | Adoption SQLModel |
| Auth | JWT + OAuth2 + RBAC | Basic Auth (env-creds) | Cycles 13-15 отложены пользователем 2026-05-30 |
| DB | PostgreSQL | SQLite | Production multi-user write contention |
| Frontend | React + Vite + TS + Chakra | Vanilla HTML (`viewer/`) + Jinja2 (`lot_orchestrator_web/templates/`) | Решение о frontend-rewrite |
| Реверс-прокси | Traefik | — | Production deploy |
| Observability | Sentry | jsonl-лог в `_run_log.jsonl` | Production observability |
| Docker | docker-compose | — | Production packaging |

## Когда удалять обёртку

- ❌ Откажемся от template-совместимости → `rm -rf backend/`.
- ✅ Решим мигрировать на template **функционально** → заменить `backend/app/*` re-export'ы на real-impl с SQLModel + Alembic + JWT.

Текущий статус (2026-05-30): ни одного решения. Обёртка остаётся как точка расширения.

## Связи

- ADR-003 — ownership и триггеры для temporal-v2 + DB-миграции.
- `backend/README.md` — пользовательский README с примерами запуска.
- system-state — общий снимок.
