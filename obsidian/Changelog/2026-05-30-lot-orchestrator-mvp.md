# 2026-05-30 — Orchestrator MVP (cycle 4, CLI-only)

## Итог
Реализован CLI-MVP `lot_orchestrator` — 4-фазный пайплайн memorandum-генерации (validate → context_injection → llm_running → routing). Pydantic-схемы SSOT совместимы со spec'ой `orchestrator_spec.md` §6. anthropic SDK обёрнут в MockClient/AnthropicClient для тестируемости. 31/31 тестов pass.

## Артефакты (12 модулей)

| Файл | Назначение | LOC |
|---|---|---|
| `lot_orchestrator/__init__.py` | Public re-exports | 26 |
| `lot_orchestrator/config.py` | `Settings.from_env()` — 7 env-переменных | 35 |
| `lot_orchestrator/schemas.py` | Pydantic v2: AssetData / TargetScenario / DocumentDate / Fact / Provenance / Conflict / EgrnLayer / EtpProfile | 127 |
| `lot_orchestrator/workspace.py` | `init_workspace(root)` — идемпотентная Memorandum/ + fuzzy-match через SequenceMatcher | 71 |
| `lot_orchestrator/inputs_finder.py` | `find_canonical_or_recursive` — canonical → recursive fallback + skip service-dirs + mtime ordering | 56 |
| `lot_orchestrator/temporal.py` | `detect_conflicts(facts)` — newer > registered > document_date | 56 |
| `lot_orchestrator/response_handler.py` | `extract_and_write_market_template` — regex `<SYSTEM_MARKET_TEMPLATE>` | 43 |
| `lot_orchestrator/router.py` | `route_outputs` — split по `<!-- MARP_START -->` | 36 |
| `lot_orchestrator/prompts.py` | `build_prompts` — system = market_injector + 02 (без ЭТАП 0); user = шаблон ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ с подстановкой | 95 |
| `lot_orchestrator/llm_client.py` | `AnthropicClient` (retry × N) + `MockClient` (Protocol-based) | 80 |
| `lot_orchestrator/state_machine.py` | `run_pipeline(...)` — 4 фазы, jsonl-лог в `_run_log.jsonl` | 187 |
| `lot_orchestrator/cli.py` | `python -m lot_orchestrator.cli --workspace --lot [--mock-llm\|--dry-run]` | 95 |

## Тесты (31/31 pass, pytest 0.12s)

- `test_schemas.py` (7) — lot_id regex, target_scenario.is_complete, DocumentDate валидация, evidence_level constraint, Conflict min 2, минимальная фикстура.
- `test_workspace.py` (4) — идемпотентность, fuzzy-match `Memorandum`↔`memorandum`, canonical fallback, FileNotFoundError.
- `test_inputs_finder.py` (5) — canonical wins, recursive fallback, skip service-dirs, mtime ordering, None when not found.
- `test_temporal.py` (5) — без конфликта, newer_wins, registered_wins on tie, unresolved при equal level+date, независимые пути.
- `test_response_router.py` (5) — extract market_template, идемпотентность, missing tags warning, MARP split, missing marker warning.
- `test_state_machine.py` (5) — happy path, awaiting когда нет enrich, awaiting при пустом target_scenario, error при missing market_analysis, warning при missing MARP.

## Smoke CLI

```bash
python -m lot_orchestrator.cli --workspace ./project --lot test_001 \
    --mock-llm "Отчёт. <!-- MARP_START --> # Slide"
```
Возвращает rc=0 на happy path, создаёт `Memorandum/{final_report.md, investment_slides.md, _data/_run_log.jsonl}`.

## Решения (зафиксированы в ADR / архитектуре)

| Решение | Где |
|---|---|
| Top-level `lot_orchestrator/` (не `parser/orchestrator/`) | согласовано с пользователем |
| CLI-only MVP — FastAPI/UI на cycle 5 | согласовано |
| Pydantic + anthropic + pyyaml — единственные runtime deps | согласовано |
| Упрощённый SequenceMatcher вместо canonical `folder_match` — extraction отложен на cycle 6 | `lot-orchestrator.md` §MVP-упрощения |
| `EgrnLayer.tables: dict[str, Any]` — открытый контейнер под parser-checko и любые другие источники | [[ADR-002-parser-checko-integration-policy]] |

## Цикл цикла (что дальше)

- **cycle 5** — FastAPI обёртка (`POST /lots/{lot_id}/run`, `GET /needs-input`, ...) на ветке `orchestrator/frontend`. Web-UI для интерактивного сбора `target_scenario` и `documents_dates`.
- **cycle 6** — extraction `parser/utils/folder_match.py` отдельным PR; замена SequenceMatcher на canonical v3-логику.
- **cycle 7** — `etl_checko.py` адаптер (триггер: orchestrator merged + работа на реальном лоте).

## Связи

- spec: `obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md`
- архитектура: [[lot-orchestrator]]
- параллельная разработка: [[parallel-parsers-map]]
- интеграция checko: [[ADR-002-parser-checko-integration-policy]]
