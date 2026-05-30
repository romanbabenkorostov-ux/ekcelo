# Архитектура: lot_orchestrator (Memorandum pipeline)

> CLI-MVP cycle 4. Реализует Фазы 1-4 из `obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md`. FastAPI/web-UI отложены на cycle 5.

## Назначение

Автоматизирует ручной пайплайн «лот → меморандум»: читает рабочую папку лота, валидирует SSOT (`enrich_<lot_id>.json`), инжектит market-injector в системный промпт, вызывает Claude через `anthropic` SDK, перехватывает служебный блок `<SYSTEM_MARKET_TEMPLATE>`, маршрутизирует ответ в `final_report.md` + `investment_slides.md`.

## Структура

```
lot_orchestrator/
├── __init__.py
├── config.py             # Settings.from_env() — ANTHROPIC_API_KEY, PROMPTS_PATH, ...
├── schemas.py            # Pydantic v2: AssetData / TargetScenario / DocumentDate / Fact / Provenance / Conflict / EgrnLayer / EtpProfile
├── workspace.py          # init_workspace(root) → WorkspaceLayout (Memorandum/_data/, incoming/)
├── inputs_finder.py      # find_canonical_or_recursive + skip-list, mtime-ordering
├── temporal.py           # detect_conflicts(facts) — newer > registered > document_date
├── response_handler.py   # extract_and_write_market_template — regex <SYSTEM_MARKET_TEMPLATE>
├── router.py             # route_outputs — split по <!-- MARP_START -->
├── prompts.py            # build_prompts(prompts_path, ...) — system + user
├── llm_client.py         # AnthropicClient (retry × N) + MockClient (для тестов)
├── state_machine.py      # run_pipeline(...) — 4 фазы, OrchestrationResult
├── cli.py                # python -m lot_orchestrator.cli --workspace --lot [--mock-llm|--dry-run]
└── tests/                # 31 теста (pytest)
```

## State machine (4 фазы)

| Фаза | Что | Выход |
|---|---|---|
| **VALIDATING** | `init_workspace` + загрузка `enrich_<lot_id>.json` + Pydantic-валидация + поиск `market_analysis.txt` (canonical → recursive fallback) + опциональный `graph.html` / `market_template.md` | `AWAITING_USER_INPUT` если нет SSOT или `target_scenario` неполный; `ERROR` если нет `market_analysis.txt` |
| **CONTEXT_INJECTION** | `build_prompts(prompts_path, enrich_text, market_analysis, existing_template, graph_status)` — system из `market_injector_prompt_block.md` + system-part из `02_memorandum_prompt.md` (без ЭТАП 0). | `PromptBundle(system, user)` |
| **LLM_RUNNING** | `AnthropicClient.send(system, user)` с retry × `LLM_RETRIES`. Лог в `_data/_run_log.jsonl` (sha256 промптов, длины, usage). | `LLMResponse(text, model, usage)` |
| **ROUTING** | `extract_and_write_market_template` (если есть теги — пишет `market_template.md`, удаляет блок) → `route_outputs` (split по `<!-- MARP_START -->`). | `final_report.md` + `investment_slides.md` (slides пустой при отсутствии маркера) |

## Контракт SSOT (`enrich_<lot_id>.json`)

Pydantic-схема `AssetData` совместима с `obsidian/Prompts/llm_memorandum_pipeline/templates/enrich.json.tpl`. Ключевые валидации:

- `lot_id` — regex `^[A-Za-z0-9_:-]+$` (расширен из spec для совместимости с `lot:<slug>:<NNN>`).
- `TargetScenario.is_complete()` — все три поля (was/trigger/to_plan) non-empty.
- `DocumentDate` — хотя бы одно из `registered_date`/`document_date`.
- `Provenance.evidence_level` ∈ {1, 2}.
- `Conflict.competing_facts` — min 2 элемента.
- `EgrnLayer.tables: dict[str, Any]` + `extra="allow"` — открытый контейнер под произвольные парсерные таблицы (см. [[ADR-002-parser-checko-integration-policy]] о будущей интеграции checko-данных).

## CLI

```bash
# Реальный LLM:
export ANTHROPIC_API_KEY=sk-ant-...
python -m lot_orchestrator.cli --workspace D:/ОБЪЕКТЫ/pirushin --lot pirushin_001

# Smoke без сети:
python -m lot_orchestrator.cli --workspace ./project --lot test_001 \
    --mock-llm "Финальный отчёт. <!-- MARP_START --> # Slide"

# Только проверка валидации/входов (LLM-вызов мокается):
python -m lot_orchestrator.cli --workspace ./project --lot test_001 --dry-run
```

Exit codes:
- `0` — DONE
- `2` — AWAITING_USER_INPUT (нет SSOT / неполный target_scenario)
- `3` — ERROR (Pydantic-валидация / отсутствие обязательного входа)
- `1` — иной (uncaught)

## Env-переменные (`Settings.from_env()`)

| Переменная | Default | Назначение |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Обязательна для реального LLM (не нужна для `--mock-llm`/`--dry-run`) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Модель для anthropic SDK |
| `PROMPTS_PATH` | `obsidian/Prompts/llm_memorandum_pipeline` | Корень `.md` промптов |
| `LLM_TIMEOUT_S` | `120` | Таймаут запроса |
| `LLM_RETRIES` | `3` | Кол-во попыток при network-ошибках |
| `FUZZY_MATCH_THRESHOLD` | `0.7` | Порог fuzzy-match для `Memorandum/` |
| `AUTO_YES` | `false` | Не спрашивать при коллизии fuzzy-match (использовать существующую) |

## Точки расширения

| Cycle | Что добавится |
|---|---|
| **5** ✅ | FastAPI обёртка (`lot_orchestrator_web/`, ветка `orchestrator/frontend`): 5 endpoint'ов + Jinja2 UI. См. ниже. |
| **6** ✅ | Canonical `parser.utils.folder_match.best_match` в workspace.py (PR #88). |
| **7** ✅ | `parser/exporters/etp/etl_checko.py` opt-in адаптер innogrn.db → owner_checko (PR #89). |
| **8** ✅ | SQLite persistence (`runs.sqlite`) + SSE streaming + GLOB-based artifacts (PR #90). |
| **9** ✅ | Redis-backed `RunStore` для multi-worker через fakeredis-тесты. |
| **10** ✅ | `pyproject.toml` extras `[orchestrator]`/`[orchestrator-web]`/`[orchestrator-redis]`/`[dev]` + CLI `ekcelo-orchestrate-web`. |
| **11** ✅ | SSE через Redis pub/sub (instant вместо polling 200ms). Polling — fallback при in-memory store. |
| **12** ✅ | Опциональная HTTP Basic Auth middleware (env `EKCELO_AUTH_USERS=user:pass,...`). Production multi-user — за reverse-proxy. |
| httpx2 ✅ | TestClient на `httpx2>=2.0` (убран starlette deprecation warning). |

## FastAPI обёртка (cycle 5)

`lot_orchestrator_web/` — тонкая обёртка над `run_pipeline`. BackgroundTasks + in-memory store.

### Endpoints

| Method | Path | Описание |
|---|---|---|
| `POST` | `/lots/{lot_id}/run` | Body: `{workspace_path, mock_llm_text?}`. Создаёт run, ставит в BackgroundTask. → 202 `{run_id, lot_id}` |
| `GET` | `/lots/{lot_id}/status/{run_id}` | JSON: `{run_id, lot_id, status, phase, warnings[], errors[]}` |
| `GET` | `/lots/{lot_id}/needs-input` | HTML-форма target_scenario с предзаполнением из последнего run'а |
| `POST` | `/lots/{lot_id}/provide-input` | form-data: `workspace_path, was, trigger, to_plan`. Обновляет SSOT идемпотентно (`patch_target_scenario`) + перезапускает прогон. → 202 |
| `GET` | `/lots/{lot_id}/artifacts` | JSON: пути к `final_report.md`, `investment_slides.md`, `market_template.md`, `_run_log.jsonl` (cycle 8: GLOB-based, переживает рестарт) |
| `GET` | `/lots/{lot_id}/stream/{run_id}` | **cycle 8:** SSE stream `event: phase / done / error / timeout` (polling 200ms, 5min timeout) |
| `GET` | `/` | index с перечнем endpoints + ссылками на `/docs` / `/redoc` |

### Запуск (cycle 10 — через canonical CLI)

```bash
# Установка с extras (см. UserGuide/install.md).
pip install -e ".[orchestrator-web]"

# Dev:
ekcelo-orchestrate-web --reload

# Production с persistence:
ekcelo-orchestrate-web --persistence-db ./runs.sqlite

# Production multi-worker через Redis:
pip install -e ".[orchestrator-redis]"
ekcelo-orchestrate-web \
    --redis-url redis://localhost:6379/0 \
    --persistence-db ./runs.sqlite \
    --workers 4
```

### Multi-worker store (cycle 9)

`lot_orchestrator_web/redis_store.py`:
- Hash `ekcelo:run:<run_id>` — состояние run'а.
- Set `ekcelo:lot_runs:<lot_id>` — индекс run_id для лота.
- Pub/Sub `ekcelo:events:<run_id>` — push phase changes (потенциально для SSE без polling).

API совместим с in-memory `RunStore` (одни и те же сигнатуры). На старте загружает snapshot из SQLite (durable mirror) — если Redis потерял данные, completed-runs восстанавливаются.

### MVP-упрощения web-слоя

1. **Нет auth/authz** — деплой только за reverse-proxy с защитой.
2. **SSE через polling** (200ms) — Redis pub/sub доступен в `RedisRunStore.subscribe_events()`, но SSE endpoint пока polls. Подключение pub/sub к SSE — будущий cycle.
3. **`mock_llm_text` доступен через body** — для smoke без `ANTHROPIC_API_KEY`.

## MVP-упрощения (общие)

1. **`prompts.py` рендерит шаблон без Jinja2** — простая `str.replace` на `{{ enrich_json }}` / `{{ market_analysis }}` / `{{ existing_market_template }}` / `{{ graph_status }}`. Если шаблон обзаведётся `{% if %}` / `{% for %}` — внести Jinja2.
2. **Нет токен-счётчика** — `usage` приходит из anthropic-ответа как-есть.

См. [[parallel-parsers-map]] для контекста параллельной разработки.
