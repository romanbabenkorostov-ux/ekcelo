# 2026-05-30 — Cycles 9 + 10: Redis multi-worker store + pyproject extras + CLI

## Итог
Два смежных цикла в одном PR:

- **Cycle 9** — `RedisRunStore` для multi-worker production deploy (через Redis hash + pub/sub + SQLite mirror).
- **Cycle 10** — Top-level `pyproject.toml` с extras (`[orchestrator]`, `[orchestrator-web]`, `[orchestrator-redis]`, `[dev]`) + CLI `ekcelo-orchestrate-web` обёртка над uvicorn.

**Покрытие 95%** (1942 LOC / 92 missing) — соответствует требованию пользователя «≥95%».

## Артефакты

### Cycle 9 (Redis)

- `lot_orchestrator_web/redis_store.py` (~250 LOC) — `RedisRunStore` API-совместимый с in-memory `RunStore`.
- `lot_orchestrator_web/store.py` — добавлена `configure_redis_store()` factory.
- `lot_orchestrator_web/main.py` — `create_app(redis_client=...)` kwarg.
- `lot_orchestrator_web/tests/test_redis_store.py` — 16 тестов через `fakeredis`.

### Cycle 10 (pyproject + CLI)

- `pyproject.toml` (top-level, новый) — extras + scripts.
- `lot_orchestrator_web/cli.py` — обёртка над uvicorn с `--persistence-db --redis-url --workers --reload --host --port`.
- `lot_orchestrator_web/main.py` — читает env `EKCELO_PERSISTENCE_DB` / `EKCELO_REDIS_URL` при импорте (выставляются из cli.py).
- `lot_orchestrator_web/tests/test_cli.py` — 9 тестов.

### Coverage boost (тесты в нагрузку к cycle 9-10)

- `lot_orchestrator/tests/test_llm_client.py` — 8 тестов AnthropicClient через mocked anthropic SDK (retry × N, timeout, status error).
- `lot_orchestrator/tests/test_state_machine_edges.py` — 3 теста error paths (JSON parse error, ValidationError, graph.html recursive copy).
- `lot_orchestrator_web/tests/test_runner.py` — 6 тестов build_llm_client + patch_target_scenario edge cases.
- `lot_orchestrator_web/tests/test_main_edges.py` — 5 тестов error paths /run, /provide-input, /artifacts, SSE для completed run.

## pyproject extras

```toml
[project.optional-dependencies]
orchestrator = ["pydantic>=2.5", "anthropic>=0.30"]
orchestrator-web = ["ekcelo[orchestrator]", "fastapi>=0.115",
                    "uvicorn[standard]>=0.30", "python-multipart>=0.0.9",
                    "httpx>=0.27"]
orchestrator-redis = ["ekcelo[orchestrator-web]", "redis>=5.0"]
egrn-full = ["pdfplumber>=0.11", "openpyxl>=3.1", "python-docx>=1.1",
             "piexif>=1.1", "Pillow>=10.0"]
dev = ["ekcelo[orchestrator-redis,egrn-full]", "pytest>=8.0",
       "pytest-cov>=5.0", "fakeredis>=2.20"]

[project.scripts]
ekcelo-orchestrate = "lot_orchestrator.cli:main"
ekcelo-orchestrate-web = "lot_orchestrator_web.cli:main"
ekcelo-etp-smoke = "parser.exporters.etp.smoke_cli:main"
```

## Использование

### Dev (in-memory store, без persistence)

```bash
pip install -e ".[orchestrator-web]"
ekcelo-orchestrate-web --reload
```

### Production (SQLite snapshot, single worker)

```bash
pip install -e ".[orchestrator-web]"
ekcelo-orchestrate-web --persistence-db ./runs.sqlite
```

### Production multi-worker (Redis + SQLite mirror)

```bash
pip install -e ".[orchestrator-redis]"
ekcelo-orchestrate-web \
    --redis-url redis://localhost:6379/0 \
    --persistence-db ./runs.sqlite \
    --workers 4 \
    --host 0.0.0.0
```

## Архитектура Redis-store

| Redis-ключ | Что хранит |
|---|---|
| `ekcelo:run:<run_id>` (HASH) | run_id, lot_id, workspace_path, status, phase, warnings_json, errors_json, started_at, finished_at, error |
| `ekcelo:lot_runs:<lot_id>` (SET) | Все run_id для лота (для `latest_for_lot`) |
| `ekcelo:events:<run_id>` (Pub/Sub) | Phase-change события: `{run_id, status, phase, warnings, errors}` JSON |

SQLite-persistence работает параллельно как durable mirror:
- Если Redis потерял данные → completed-runs восстанавливаются на старте из `runs.sqlite`.
- Если SQLite не задан → snapshot не пишется (но Redis работает).
- Если Redis уже содержит запись на момент restore-from-snapshot → НЕ перезаписывается (защита от затирания свежих running-snapshots).

## In-process result storage

`OrchestrationResult` содержит сложные nested types (Phase enum, dataclasses, Path), которые не сериализуются в Redis hash. Решение: хранить `result` в **локальном dict per-worker** (`_in_process_results`), а `phase/warnings/errors` извлекать и писать в Redis hash. Артефакты (паттерн `final_report.md` etc.) — подбираются GLOB'ом из workspace, не нужны в Redis.

Trade-off: после рестарта worker'а потеряется in-process result, но phase/warnings/errors сохраняются. Артефакты остаются доступны через GLOB.

## Тесты (93/93 pass, 95% coverage)

```
$ python -m pytest lot_orchestrator{,_web}/tests/ --cov=lot_orchestrator --cov=lot_orchestrator_web

----- coverage: -----
TOTAL                                           1942     92    95%
93 passed in 1.59s
```

Топ-3 файла по coverage:
- `lot_orchestrator/schemas.py`: 100%
- `lot_orchestrator/response_handler.py`: 100%
- `lot_orchestrator_web/redis_store.py`: 98%

## Mental-run trace (production multi-worker)

1. Запуск: `ekcelo-orchestrate-web --redis-url ... --persistence-db ... --workers 4`
2. `cli.py::main` парсит args, выставляет `EKCELO_PERSISTENCE_DB` + `EKCELO_REDIS_URL` env vars, вызывает `uvicorn.run`.
3. uvicorn форкает 4 worker'а. Каждый импортирует `main.py`.
4. `main.py` при импорте: `_build_app_from_env()` читает env vars → создаёт redis-client → `configure_redis_store(client, persistence=SQLitePersistence(...))`.
5. На старте: `RedisRunStore.__init__` → `_restore_from_persistence` → `SQLitePersistence.load_all()` → если в Redis ключа нет, восстанавливаем snapshot (или помечаем orphaned).
6. POST `/lots/X/run` → BackgroundTask вызывает `execute_run(run, settings, store, llm)` → `run_pipeline(...)` в потоке.
7. После завершения worker A: `store.update(run_id, status="complete", result=...)` → `_publish` на `ekcelo:events:<run_id>`.
8. Worker B опрашивает `GET /status/{run_id}` → читает из Redis (тот же hash) → видит complete.
9. SSE `GET /stream/{run_id}` worker B → polling по Redis (cycle 8 поведение, на cycle 11 можно переключить на pub/sub).
10. После рестарта одного worker'а: остальные продолжают видеть state через Redis. После полного рестарта всех + Redis FLUSHDB: completed-runs восстанавливаются из SQLite, незавершённые → orphaned.

## Дальше

- **cycle 11** — Подключить SSE endpoint к Redis pub/sub (вместо polling). Будет real-time без 200ms задержки.
- **cycle 12** — auth/authz (FastAPI OAuth-прокси integration).
- (опционально) Миграция TestClient на httpx2 (starlette deprecation).
