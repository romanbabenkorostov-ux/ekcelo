# backend/ — структурная обёртка под fastapi-template

> Layout этой папки — зеркало [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) backend/. **Не содержит логики**. Все файлы — `re-export` существующих модулей из `lot_orchestrator/`, `lot_orchestrator_web/`, `parser/`.

## Зачем

Чтобы новый контрибьютер, знакомый с template-паттерном fastapi-template, мог быстро навигироваться:

| Где в template | Где у нас (real impl) | Покрытие |
|---|---|---|
| `backend/app/main.py` | `lot_orchestrator_web/main.py` | ✅ re-export |
| `backend/app/api/deps.py` | `lot_orchestrator_web/store.py::get_store` | ✅ re-export |
| `backend/app/api/v1/<endpoint>.py` | routes в `_register_routes(app)` внутри `main.py` | ⚠️ один файл, не разбит по router'ам (для разделения — будущий cycle) |
| `backend/app/core/config.py` | `lot_orchestrator/config.py::Settings` | ✅ re-export |
| `backend/app/core/security.py` | `lot_orchestrator_web/auth.py` (после PR #93) | ⚠️ lazy-import wrapper (на main без #93 возвращает False) |
| `backend/app/core/persistence.py` | `lot_orchestrator_web/persistence.py::SQLitePersistence` (после PR #90) | ⚠️ lazy-proxy (на main без #90 — ImportError при инстанцировании) |
| `backend/app/crud/runs.py` | `lot_orchestrator_web/store.py` | ✅ re-export |
| `backend/app/models/schemas.py` | `lot_orchestrator/schemas.py` (Pydantic v2) | ✅ re-export |
| `backend/app/services/orchestrator.py` | `lot_orchestrator/state_machine.py::run_pipeline` | ✅ re-export |
| `backend/app/services/llm.py` | `lot_orchestrator/llm_client.py` (Protocol + Anthropic + Mock) | ✅ re-export |
| `backend/alembic/` | — | ⚠️ stub только; `target_metadata=None`. См. ADR-003 тема 4 (deferred). |

## Использование

Эквивалентность путей запуска:

```bash
# Template-style:
uvicorn backend.app.main:app --reload

# Direct (наш канонический путь):
uvicorn lot_orchestrator_web.main:app --reload

# После merge PR #92 (console script):
ekcelo-orchestrate-web --reload
```

Все 3 варианта дают тот же FastAPI app с теми же 6 endpoints, тем же title `Ekcelo Orchestrator` и теми же background tasks.

## Что НЕ делаем (явно отложено)

Эти пункты соответствуют шаблону fastapi-template, но в ekcelo сознательно отложены:

| Что в template | Что у нас | Триггер активации |
|---|---|---|
| SQLModel ORM | sqlite3-direct + JSON-колонки | Решение пользователя о миграции (ADR-003 тема 4) |
| Alembic runtime migrations | stub (`env.py` с `target_metadata=None`) | Adoption SQLModel |
| JWT + OAuth2 | Basic Auth middleware (cycle 12 в PR #93) | Триггеры cycles 13-15 — явно остановлены пользователем 2026-05-30 |
| PostgreSQL | SQLite | Production-кейс с multi-user write contention |
| React + TypeScript frontend | Vanilla HTML `viewer/` + Jinja2 templates | Решение о frontend-rewrite (отсутствует на 2026-05-30) |
| Docker / Traefik | — | Production deploy decision |

## Тесты

```bash
python -m pytest backend/tests/
```

12 тестов проверяют, что все `backend/app/*` re-exports реально являются той же сущностью, что и прямой импорт из `lot_orchestrator{,_web}` (через `assert X is Y`).

## Когда удалять обёртку

- Если решено отказаться от template-совместимости и работать только с direct-layout → удалить `backend/`.
- Если решено мигрировать на template **функционально** (SQLModel + Alembic + JWT + React) → удалить `backend/` re-exports и собрать real-layout с runtime-кодом.

Сейчас (2026-05-30) ни одного из двух решений не принято. Обёртка остаётся как точка расширения без обязательств.

## Связи

- `obsidian/Architecture/system-state-2026-05-30.md` — общий снимок системы.
- `obsidian/Architecture/lot-orchestrator.md` — архитектура core-модулей.
- `obsidian/Decisions/ADR-003-temporal-v2-ownership.md` — тема 4 «DB-миграция deferred».
