# lot_orchestrator_web — FastAPI обёртка для orchestrator (cycle 5, planned)

> **Статус:** ветка-placeholder. Код будет добавлен в cycle 5 после мерджа MVP backend'а.

## Назначение

FastAPI + Jinja2 web-UI поверх `lot_orchestrator` (cycle 4 CLI-MVP). Заменяет ручной запуск CLI для интерактивного сбора `target_scenario`, темпоральных полей и разрешения fuzzy-match коллизий.

## Запланированный API (orchestrator_spec.md §5)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `POST` | `/lots/{lot_id}/run` | `{"workspace_path": "..."}` | 202 `{"run_id": "..."}` или 400 |
| `GET` | `/lots/{lot_id}/status/{run_id}` | — | `{"phase": "...", "details": {...}}` |
| `GET` | `/lots/{lot_id}/needs-input` | — | HTML-форма (target_scenario, темпоральные поля) |
| `POST` | `/lots/{lot_id}/provide-input` | form-data | 200 (обновляет SSOT, продолжает state machine) |
| `GET` | `/lots/{lot_id}/artifacts` | — | JSON со ссылками на `final_report.md`, `investment_slides.md`, `market_template.md`, `_run_log.jsonl` |

## Скоп cycle 5

1. `main.py` — FastAPI app + lifespan.
2. `routes/lots.py` — 5 endpoint'ов из таблицы выше.
3. `templates/` — Jinja2 шаблоны: `needs_input.html`, `status.html`, `artifacts.html`.
4. `static/` — минимальный CSS.
5. Async-обёртка над `lot_orchestrator.state_machine.run_pipeline` (background tasks).
6. In-memory store `run_id → OrchestrationResult` (без БД).

## Не входит в cycle 5

- Authentication / authorization (требует отдельного решения).
- Multi-tenant.
- Streaming UI (Server-Sent Events / WebSocket) — оставлено на cycle 6+.
- Production Docker / k8s — не часть MVP.

## Зависимости (добавляются в pyproject в cycle 5)

```
fastapi >= 0.115
uvicorn[standard] >= 0.30
jinja2 >= 3.1
python-multipart >= 0.0.9  # form-data
```

## Связи

- backend: см. `orchestrator/backend` ветка → `lot_orchestrator/` пакет (cycle 4).
- spec: `obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md` §5.
- архитектура: `obsidian/Architecture/lot-orchestrator.md` (раздел «Точки расширения → cycle 5»).
