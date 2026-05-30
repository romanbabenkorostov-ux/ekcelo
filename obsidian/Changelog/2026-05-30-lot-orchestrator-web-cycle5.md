# 2026-05-30 — Orchestrator FastAPI обёртка (cycle 5)

## Итог
Поверх MVP-backend'а (cycle 4) собрана FastAPI обёртка `lot_orchestrator_web/`. 5 endpoints + Jinja2 UI + BackgroundTasks + in-memory store. 9 тестов через TestClient, 40/40 общих pass за 0.32s.

## Артефакты

| Файл | LOC | Назначение |
|---|---|---|
| `lot_orchestrator_web/__init__.py` | 1 | Marker |
| `lot_orchestrator_web/main.py` | 215 | `create_app(...)` factory + 6 routes + Pydantic-схемы запросов/ответов |
| `lot_orchestrator_web/runner.py` | 64 | `execute_run` (async wrapper for `run_pipeline`) + `patch_target_scenario` + `build_llm_client` |
| `lot_orchestrator_web/store.py` | 80 | `RunStore` (threadsafe in-memory) + `get_store` dep + `reset_store_for_tests` |
| `lot_orchestrator_web/templates/base.html` | 18 | Базовый layout |
| `lot_orchestrator_web/templates/index.html` | 12 | Главная с перечнем endpoints |
| `lot_orchestrator_web/templates/needs_input.html` | 33 | Форма target_scenario с предзаполнением |
| `lot_orchestrator_web/static/style.css` | 28 | Минимальный CSS |
| `lot_orchestrator_web/tests/conftest.py` | 50 | Фикстуры: TestClient + populated_workspace + auto-reset store |
| `lot_orchestrator_web/tests/test_routes.py` | 110 | 9 тестов HTTP-уровня |

## Endpoints

| Method | Path | Описание |
|---|---|---|
| `POST` | `/lots/{lot_id}/run` | 202 → `{run_id, lot_id}` |
| `GET` | `/lots/{lot_id}/status/{run_id}` | `{run_id, lot_id, status, phase, warnings[], errors[]}` |
| `GET` | `/lots/{lot_id}/needs-input` | HTML-форма target_scenario |
| `POST` | `/lots/{lot_id}/provide-input` | form-data → 202 (обновляет SSOT + рестарт) |
| `GET` | `/lots/{lot_id}/artifacts` | пути к final/slides/template/log |
| `GET` | `/` | index + ссылки на `/docs`, `/redoc` |

## Тесты (9/9 pass)

- `test_index_renders`
- `test_run_404_when_workspace_missing`
- `test_full_flow_happy_path` — run → status (complete/done) → artifacts (все 4 файла существуют)
- `test_status_404_for_unknown_run`
- `test_artifacts_404_for_lot_without_runs`
- `test_needs_input_renders_form`
- `test_provide_input_updates_ssot_and_starts_run` — SSOT обновлён + новый run_id
- `test_provide_input_404_when_no_enrich`
- `test_run_request_mock_llm_text_overrides_app_default`

Все 40 тестов orchestrator-стека прошли за 0.32s.

## Зависимости (новые)

- `fastapi >= 0.115`
- `uvicorn[standard] >= 0.30` (только для production-запуска, не нужна для тестов)
- `jinja2 >= 3.1`
- `python-multipart >= 0.0.9`
- `httpx >= 0.27` (для starlette TestClient)

Pyproject.toml пока не трогали — `pip install fastapi jinja2 python-multipart httpx` достаточно. Cycle 6 закрепит deps в pyproject как extras `[orchestrator-web]`.

## Smoke

```bash
uvicorn lot_orchestrator_web.main:app --reload
# http://localhost:8000/         — главная
# http://localhost:8000/docs     — OpenAPI swagger
# http://localhost:8000/redoc    — ReDoc
```

`POST /lots/{lot_id}/run` принимает `mock_llm_text` в body — для smoke без `ANTHROPIC_API_KEY`.

## MVP-упрощения

1. **In-memory store** (singleton) — runs не переживают рестарт. Multi-worker / persistence — cycle 7+.
2. **Нет auth/authz** — деплой только за reverse-proxy с защитой.
3. **Нет SSE/WebSocket** — статус опрашивается через GET.
4. **TestClient deprecation warning** — `httpx` под starlette TestClient помечено deprecated; миграция на `httpx2` — отдельная задача.

## Дальше

- **cycle 6** — extraction `parser/utils/folder_match.py` (отдельный PR перед заменой SequenceMatcher).
- **cycle 7** — `etl_checko.py` адаптер (триггер: orchestrator merged + работа на реальном лоте).
- **cycle 8+** — persistence (SQLite store), SSE streaming, multi-worker uvicorn.
