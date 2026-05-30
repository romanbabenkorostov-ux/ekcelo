# 2026-05-30 — Cycle 8: SQLite persistence + SSE streaming

## Итог
Web-обёртка orchestrator'а получила два production-ready улучшения:
1. **SQLite persistence** для `RunStore` — runs переживают рестарт процесса.
2. **SSE endpoint** `/lots/{lot_id}/stream/{run_id}` — server-sent events для статуса прогона.
3. **GLOB-based `/artifacts`** — артефакты подбираются из workspace, работает даже после рестарта.

49/49 тестов pass за 0.41s (40 cycle 4-5 + 9 cycle 8).

## Артефакты

| Файл | Изменение |
|---|---|
| `lot_orchestrator_web/persistence.py` | NEW (~115 LOC). `SQLitePersistence` + `RunSnapshot`. |
| `lot_orchestrator_web/store.py` | Расширен. `Run.phase/warnings/errors` стали property; добавлены `restored_*` поля для loaded-from-DB run'ов; `configure_store(persistence)` для startup. |
| `lot_orchestrator_web/main.py` | `create_app(persistence_db=...)`; новый SSE endpoint; `/artifacts` переписан на GLOB. |
| `lot_orchestrator_web/tests/test_persistence_sse.py` | NEW. 9 тестов. |

## SQLite-схема (`runs.sqlite`)

```sql
CREATE TABLE runs (
    run_id          TEXT PRIMARY KEY,
    lot_id          TEXT NOT NULL,
    workspace_path  TEXT NOT NULL,
    status          TEXT NOT NULL,        -- pending|running|complete
    phase           TEXT NOT NULL,        -- validating|...|done|error
    warnings_json   TEXT NOT NULL DEFAULT '[]',
    errors_json     TEXT NOT NULL DEFAULT '[]',
    started_at      TEXT NOT NULL,        -- ISO timestamp
    finished_at     TEXT
);
CREATE INDEX idx_runs_lot_id ON runs(lot_id);
CREATE INDEX idx_runs_started_at ON runs(started_at);
```

**ЧТО НЕ ПЕРСИСТИТСЯ** (намеренно):
- `OrchestrationResult` целиком — содержит сложные nested types.
- Пути артефактов — артефакты на диске в `Memorandum/`, подбираются GLOB'ом.
- Жирные warnings/errors лога LLM (только финальные строки `result.warnings/errors`).

## Поведение после рестарта

| Состояние run в БД | После реконструкции |
|---|---|
| `status='complete'` | Восстанавливается как complete, phase из snapshot, warnings/errors → `restored_*` |
| `status='pending'/'running'` | Перезаписывается на `complete + phase='error'`, `error='orphaned by restart'` |

## SSE endpoint

`GET /lots/{lot_id}/stream/{run_id}` → `Content-Type: text/event-stream`:

```
event: phase
data: {"run_id":"...","status":"running","phase":"validating","warnings":[],"errors":[]}

event: phase
data: {"run_id":"...","status":"running","phase":"context_injection",...}

event: done
data: {"run_id":"...","phase":"done"}
```

Polling-based (200ms tick), timeout 5 мин. Не использует cross-thread `asyncio.Queue` — `execute_run` работает в `to_thread`, polling гарантирует читаемость без race.

## Использование

```python
from pathlib import Path
from lot_orchestrator_web.main import create_app

app = create_app(persistence_db=Path("./runs.sqlite"))
# uvicorn lot_orchestrator_web.main:app
```

CLI integration (future): `--persistence-db ./runs.sqlite` flag for production deploy.

## Тесты (9/9)

1. `test_persistence_save_and_load` — round-trip RunSnapshot.
2. `test_persistence_upsert_overwrites` — повторный save с тем же run_id.
3. `test_store_persists_run_on_create_and_update` — store с persistence пишет в SQLite.
4. `test_store_loads_persisted_runs_on_startup` — load_all при `__init__`.
5. `test_store_marks_orphaned_runs_after_restart` — pending → orphaned после рестарта.
6. `test_app_with_persistence_db` — `create_app(persistence_db=...)` интеграция.
7. `test_sse_emits_phase_and_done` — happy path SSE.
8. `test_sse_emits_error_for_unknown_run` — `error` event для ненайденного run.
9. `test_artifacts_endpoint_uses_glob_not_inmemory_result` — `/artifacts` работает после рестарта (новый app instance + тот же persistence_db).

## Дальше

- **cycle 9** — Multi-worker uvicorn (RunStore через Redis вместо in-memory словаря с SQLite-зеркалом).
- **cycle 10** — `--persistence-db` CLI flag + `[orchestrator-web]` extras в pyproject.
- Опционально: миграция TestClient на httpx2 (starlette deprecation warning).
