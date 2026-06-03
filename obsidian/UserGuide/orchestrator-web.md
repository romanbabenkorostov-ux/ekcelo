# Сборка меморандума через web-UI

> Как запустить FastAPI-сервер и использовать его из браузера / curl.

## Когда использовать

- Несколько лотов параллельно.
- Экономист предпочитает форму в браузере.
- Нужна history (предыдущие прогоны видно).

> **API-ключ нужен только при реальном LLM-вызове.** Для smoke / демо передавайте `mock_llm_text` в body POST `/lots/{lot_id}/run` — оркестратор использует MockClient и не дёргает Anthropic. См. [[install]] раздел «Когда нужен ANTHROPIC_API_KEY».

## Установка

```bash
pip install -e ".[orchestrator-web]"
```

## Базовый запуск (dev-режим)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn lot_orchestrator_web.main:app --reload
```

Откройте http://localhost:8000/.

- `/` — главная с перечнем endpoints.
- `/docs` — Swagger UI (попробовать API в браузере).
- `/redoc` — ReDoc (то же самое в другом стиле).

## Production-запуск с persistence

```bash
# С SQLite-снимком (runs переживают рестарт):
PERSISTENCE_DB=./runs.sqlite uvicorn lot_orchestrator_web.main:app

# С multi-worker через Redis (production):
REDIS_URL=redis://localhost:6379/0 \
PERSISTENCE_DB=./runs.sqlite \
uvicorn lot_orchestrator_web.main:app --workers 4
```

См. [[install]] §extras для опций `[orchestrator-redis]`.

## API сценарии

### Старт прогона

```bash
curl -X POST http://localhost:8000/lots/pirushin_001/run \
    -H 'Content-Type: application/json' \
    -d '{"workspace_path": "/home/user/projects/pirushin"}'
```

Ответ:
```json
{"run_id": "abc123...", "lot_id": "pirushin_001"}
```

### Опрос статуса

```bash
curl http://localhost:8000/lots/pirushin_001/status/abc123
```

Ответ:
```json
{
  "run_id": "abc123",
  "lot_id": "pirushin_001",
  "status": "running",
  "phase": "context_injection",
  "warnings": [],
  "errors": []
}
```

### Стриминг прогресса (SSE)

```bash
curl -N http://localhost:8000/lots/pirushin_001/stream/abc123
```

Эмитит:
```
event: phase
data: {"run_id":"abc123","status":"running","phase":"validating",...}

event: phase
data: {"run_id":"abc123","status":"running","phase":"llm_running",...}

event: done
data: {"run_id":"abc123","phase":"done"}
```

В браузере для SSE используйте `EventSource`:

```javascript
const es = new EventSource(`/lots/${lotId}/stream/${runId}`);
es.addEventListener("phase", e => console.log(JSON.parse(e.data).phase));
es.addEventListener("done", e => { es.close(); /* показать артефакты */ });
```

### Получить артефакты

```bash
curl http://localhost:8000/lots/pirushin_001/artifacts
```

Ответ:
```json
{
  "lot_id": "pirushin_001",
  "memorandum": "/home/user/projects/pirushin/Memorandum",
  "final_report": "/home/user/projects/pirushin/Memorandum/final_report.md",
  "investment_slides": "/home/user/projects/pirushin/Memorandum/investment_slides.md",
  "market_template": "/home/user/projects/pirushin/Memorandum/market_template.md",
  "run_log": "/home/user/projects/pirushin/Memorandum/_data/_run_log.jsonl"
}
```

`null` значения означают что файл не создан (например, `market_template.md` — если LLM не вернул блок `<SYSTEM_MARKET_TEMPLATE>`).

### Форма target_scenario (HTML)

Откройте в браузере: `http://localhost:8000/lots/pirushin_001/needs-input`.

Заполните 3 поля (was/trigger/to_plan) + workspace_path → «Сохранить и перезапустить». Это обновит `enrich_<lot_id>.json` и стартует новый run.

## Smoke без API-ключа

В body POST-запроса добавьте `mock_llm_text`:

```bash
curl -X POST http://localhost:8000/lots/test_001/run \
    -H 'Content-Type: application/json' \
    -d '{
        "workspace_path": "/tmp/test",
        "mock_llm_text": "Mock report.\n<!-- MARP_START -->\n# Slide"
    }'
```

## Troubleshooting

### `POST /lots/.../run` → 400 «workspace_path не найден»

Путь должен существовать. Создайте папку и положите туда `Memorandum/{_data,incoming}` если их нет.

### `GET /artifacts` → 404 «для лота X нет завершённых прогонов»

Сначала сделайте `POST /run`. Прогон запускается в BackgroundTask, дайте 1-2 сек до первого опроса.

### После рестарта сервера все runs пропали

Это in-memory store. Используйте `PERSISTENCE_DB=./runs.sqlite` (см. выше).

### SSE-стрим висит / не закрывается

Polling tick = 200ms, timeout = 5 мин. Если прогон длится дольше — увеличьте таймаут в коде (`lot_orchestrator_web/main.py::_sse_phase_changes`) или закройте соединение со стороны клиента.

### `ANTHROPIC_API_KEY не задан`

Положите в `.env` или экспортируйте перед запуском. Для smoke без ключа — используйте `mock_llm_text` в body.

## Multi-worker production deploy

```bash
pip install -e ".[orchestrator-web,orchestrator-redis]"

REDIS_URL=redis://localhost:6379/0 \
PERSISTENCE_DB=./runs.sqlite \
ANTHROPIC_API_KEY=sk-ant-... \
uvicorn lot_orchestrator_web.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers 4
```

Workers разделяют состояние через Redis; SQLite — durable snapshot для recovery. Артефакты должны лежать на shared FS (NFS/EFS), иначе разные workers увидят разный `/artifacts`.

### HTTP Basic Auth (встроенный, cycle 12)

Для одного / пары пользователей доступен опциональный middleware:

```bash
ekcelo-orchestrate-web --auth-users "alice:secret,bob:s3cret!"
# или через env:
AUTH_USERS="alice:secret,bob:s3cret!" ekcelo-orchestrate-web
```

При первом GET / POST браузер покажет диалог логина. Если `--auth-users` не задан → auth отключён (поведение по умолчанию).

Эндпоинты `/static/*`, `/docs`, `/openapi.json`, `/redoc` остаются открытыми — для документации без логина.

⚠️ Это минимум для приватного использования. **Для production multi-user / SSO** — всё равно за reverse-proxy (oauth2-proxy / Authelia / Authentik / nginx auth).

## Связи

- CLI-сценарий: [[orchestrator-cli]].
- архитектура: `obsidian/Architecture/lot-orchestrator.md`.
- API spec: `obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md` §5.
