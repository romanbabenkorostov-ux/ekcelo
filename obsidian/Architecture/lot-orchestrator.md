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
| **5** | FastAPI + Jinja2 web-UI (`orchestrator/frontend` ветка): `POST /lots/{lot_id}/run`, `GET /needs-input`, `POST /provide-input`, `GET /artifacts`. Заменит ручной запуск CLI. |
| **6** | Extraction `parser/utils/folder_match.py` из `pirushin_sosn_rocha_07_init_project_v3.py` — заменит упрощённый SequenceMatcher в `workspace.py` на каноническую логику v3. |
| **7** | Адаптер `parser/exporters/etp/etl_checko.py` (см. [[ADR-002-parser-checko-integration-policy]]) — checko-данные → `object_etp_profile.legal_extra` с `source='checko'`. Триггер cycle 7 — мердж orchestrator MVP + работа на ≥1 реальном лоте. |

## MVP-упрощения

1. **Нет FastAPI/UI** — экономист запускает CLI вручную; интерактивный сбор `target_scenario` пока через ручное редактирование `enrich_*.json` или прогон Этапа 1 в claude.ai.
2. **Нет `parser.utils.folder_match`** — `workspace.py` использует упрощённый `difflib.SequenceMatcher`. Поведение совместимо в типичных случаях (`Memorandum` ↔ `memorandum`), но не покрывает все edge cases v3-логики.
3. **`prompts.py` рендерит шаблон без Jinja2** — простая `str.replace` на `{{ enrich_json }}` / `{{ market_analysis }}` / `{{ existing_market_template }}` / `{{ graph_status }}`. Если шаблон обзаведётся `{% if %}` / `{% for %}` — внести Jinja2 в cycle 5.
4. **Нет токен-счётчика** — `usage` приходит из anthropic-ответа как-есть.

См. [[parallel-parsers-map]] для контекста параллельной разработки.
