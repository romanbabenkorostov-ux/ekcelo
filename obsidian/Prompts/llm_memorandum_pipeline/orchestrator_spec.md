# orchestrator_spec.md — спецификация оркестратора лота

Документ-спека для команды разработки. Код в этом артефакте НЕ пишется; spec фиксирует контракт, по которому будет реализован отдельный PR `feat/lot-orchestrator-impl`.

## 1. Назначение и контекст

Оркестратор автоматизирует ручной пайплайн из `INDEX.md`:

- читает рабочую папку лота (`<Название_проекта>/`);
- идемпотентно создаёт/использует подпапку направления `Memorandum/` (по правилам v3, см. `workspace_contract.md`);
- собирает SSOT (Фаза 1), при необходимости запрашивает у оператора недостающие поля через web-UI;
- инжектит `market_injector_prompt_block.md` в системный промпт (Фаза 2);
- вызывает Claude через `anthropic` SDK (Фаза 3);
- перехватывает служебный блок `<SYSTEM_MARKET_TEMPLATE>`, разделяет ответ по маркеру `<!-- MARP_START -->`, маршрутизирует выходы в `Memorandum/` (Фаза 4).

Marp-рендер в HTML/PDF — отдельная команда оператора (`marp investment_slides.md -o ...`). Оркестратор НЕ требует Marp CLI как зависимость.

## 2. Стек

- Python 3.11+
- FastAPI (web-UI и API)
- Pydantic v2 (валидация SSOT)
- Jinja2 (шаблоны промптов и web-UI)
- `anthropic` SDK (LLM-клиент)
- pyyaml (чтение YAML-карточек)
- python-dotenv (env)
- pytest (тесты)

LLM-провайдер — Claude-only. Модель по умолчанию — `claude-sonnet-4-6` (соответствует CLAUDE.md проекта; можно переопределить через `ANTHROPIC_MODEL`).

## 3. Структура модулей (рекомендуемая)

```
lot_orchestrator/
├── main.py              # FastAPI app, entrypoints
├── config.py            # Pydantic Settings
├── workspace.py         # валидация и идемпотентная инициализация Memorandum/
├── state_machine.py     # оркестрация 4 фаз
├── prompts.py           # загрузка .md промптов из PROMPTS_PATH
├── prompt_builder.py    # склейка system + user, инъекция market_injector
├── llm_client.py        # anthropic wrapper: retry × 3, timeout, streaming-fallback
├── response_handler.py  # regex-перехват <SYSTEM_MARKET_TEMPLATE>, запись market_template.md
├── router.py            # split по <!-- MARP_START -->, запись final_report.md и investment_slides.md
├── inputs_finder.py     # fallback-цепочки + рекурсивный поиск входов
├── temporal.py          # правила as_of_date + evidence_level, разрешение конфликтов
├── ui/                  # Jinja2 templates: формы target_scenario, темпоральных полей, страница статуса
└── tests/
```

### Переиспользование v3-логики

`workspace.py` должен **импортировать** `parser.utils.folder_match.best_match` и логику `_resolve_existing_or_new` из `parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py`, не дублируя их. Если эти функции живут только внутри скрипта v3 — вынести их в `parser/utils/folder_match.py` (отдельной задачей, отдельным PR; spec фиксирует требование, реализация — за командой парсера).

## 4. State machine (4 фазы)

### Фаза 1 — Validate & UI

1. Подтвердить, что `workspace_path` существует и это директория. Spec не требует никакой конкретной корневой структуры за пределами `Memorandum/`.
2. Создать `Memorandum/`, `Memorandum/_data/`, `Memorandum/incoming/` идемпотентно по правилам v3 (`_resolve_existing_or_new` + `best_match` ≥ 0.7). При коллизии — спросить оператора через UI (или авто-«пропустить» при флаге `--yes` / env `AUTO_YES=true`).
3. Проверить наличие `Memorandum/_data/enrich_<lot_id>.json`. Если нет — fallback на Этап 1 (предложить оператору загрузить YAML-карточки и парсерный JSON; оркестратор склеит).
4. Валидировать `enrich_*.json` Pydantic-схемой (см. §6).
5. Если `target_scenario.was/trigger/to_plan` пусты — 202 + статус `awaiting_user_input`, через UI запросить ввод; обогатить JSON; продолжить.
6. Поиск `market_analysis.txt`: канонически в `Memorandum/incoming/`, fallback — `inputs_finder.find_recursive(root, r"^market_analysis.*\.txt$")`. Если не найден — 400 «обязательный вход отсутствует». Источник записать в `_run_log.jsonl`.
7. Поиск графа: явный `graph_path` → `inputs_finder.find_recursive(root, r"^graph\.html$")`. Если найден — `graph_status=TRUE`; иначе предупреждение в UI + опция загрузки (запись в `Memorandum/graph.html` чтобы при следующем прогоне нашёлся канонически).
8. Поиск существующего `market_template.md`: канонически в `Memorandum/market_template.md`, fallback — `inputs_finder.find_recursive(root, r"^market_template.*\.md$")`. Если найден — `existing_market_template=<content>`; иначе `None`.
9. Темпоральная валидация: каждый документ в `documents_dates[]` должен иметь хотя бы одно из `registered_date`/`document_date`.

### Фаза 2 — Context Injection

1. Системный промпт = содержимое `market_injector_prompt_block.md` + содержимое системной части `02_memorandum_prompt.md`. Загрузка через `prompts.py`, склейка через `prompt_builder.py`. Дубликат блока Context Injection (он есть и в `02_memorandum_prompt.md`) — при склейке оркестратор использует **только** `market_injector_prompt_block.md`, секцию «ЭТАП 0» из `02_memorandum_prompt.md` пропускает.
2. Пользовательский промпт — Jinja2-рендер шаблона из «ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ» в `02_memorandum_prompt.md` с переменными:
   - `enrich_json` — содержимое SSOT;
   - `market_analysis` — содержимое `market_analysis.txt`;
   - `existing_market_template` — содержимое или пустая строка;
   - `graph_status` — `TRUE`/`FALSE`.
3. Лог в `_run_log.jsonl`: ISO timestamp, фаза, токены (через `tiktoken` или встроенный счётчик anthropic), SHA-256 системного и пользовательского промпта.

### Фаза 3 — LLM call + перехват

1. `llm_client.send(system, user)` с retry × 3 (exp backoff 2s/4s/8s) и timeout 120s. При сетевых ошибках — повтор; при API-ошибках 4xx — отдать в state machine как `error`.
2. На полученном ответе `response_text` применить регекс `(?s)<SYSTEM_MARKET_TEMPLATE>(.*?)</SYSTEM_MARKET_TEMPLATE>`:
   - Если найден — извлечь содержимое, перезаписать `Memorandum/market_template.md` (канонический путь, даже если входной шаблон поднимали из глубины дерева). Удалить блок (вместе с тегами) из `response_text`.
   - Если не найден — warning в `_run_log.jsonl`, `market_template.md` НЕ трогать.

### Фаза 4 — Routing

1. Split очищенного `response_text` по маркеру `<!-- MARP_START -->`:
   - до маркера → `Memorandum/final_report.md`;
   - после маркера → `Memorandum/investment_slides.md`.
2. Если маркера нет → всё в `final_report.md`, `investment_slides.md` пустой + warning.
3. HTML/PDF-рендер презентации **НЕ** делается оркестратором.
4. Записать в `_run_log.jsonl` итог (длина outputs, источники входов, разрешённые конфликты).

## 5. API (контракт)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `POST` | `/lots/{lot_id}/run` | `{"workspace_path": "..."}` | 202 `{"run_id": "..."}` или 400 |
| `GET` | `/lots/{lot_id}/status/{run_id}` | — | `{"phase": "...", "details": {...}}` |
| `GET` | `/lots/{lot_id}/needs-input` | — | HTML-форма (target_scenario, темпоральные поля, конфликт fuzzy-match) |
| `POST` | `/lots/{lot_id}/provide-input` | form-data ответов | 200 (обновляет SSOT, продолжает state machine) |
| `GET` | `/lots/{lot_id}/artifacts` | — | JSON со ссылками на `final_report.md`, `investment_slides.md`, `market_template.md`, `_run_log.jsonl` |

Статусы фаз: `validating`, `awaiting_user_input`, `context_injection`, `llm_running`, `routing`, `done`, `error`.

## 6. Pydantic-схемы (описание полей)

- **`AssetData`** (корень `enrich_*.json`):
  - `schema_version: Literal["1.0"]`
  - `lot_id: str` (regex `^[A-Za-z0-9_-]+$`)
  - `generated_at: datetime`
  - `target_scenario: TargetScenario`
  - `egrn: EgrnLayer` (контейнер с `tables: dict[str, Any]` — выход парсера)
  - `etp_profile: EtpProfile | None`
  - `graph_ref: str | None` (имя/относительный путь графа, обычно `"graph.html"`)
  - `gpzu_minkult: dict | None`
  - `field_inspection: dict | None`
  - `photo_album: dict | None`
  - `documents_dates: list[DocumentDate]`
  - `facts_index: list[Fact]`
  - `conflicts: list[Conflict]`
  - `missing_layers: list[Literal["gpzu_minkult", "field_inspection", "photo_album"]]`

- **`TargetScenario`**: `was: str`, `trigger: str`, `to_plan: str`. Все non-empty при `status="done"` (валидация на выходе Фазы 1).

- **`DocumentDate`**:
  - `document_id: str`
  - `type: Literal["ЕГРН", "ЕГРЮЛ", "ЕГРИП"]`
  - `registered_date: date | None`
  - `document_date: date | None`
  - `covers_cad_numbers: list[str]` (пусто, если документ ЕГРЮЛ/ЕГРИП)
  - `covers_entities: list[Entity] | None` (для ЕГРЮЛ/ЕГРИП)
  - Валидатор: `registered_date is not None or document_date is not None`.

- **`Fact`**:
  - `fact_path: str` (JSONPath-подобный, например `egrn.tables.objects[0].area`)
  - `value: Any`
  - `provenance: Provenance`

- **`Provenance`**:
  - `document_id: str`
  - `as_of_date: date`
  - `evidence_level: Literal[1, 2]`

- **`Conflict`**:
  - `fact_path: str`
  - `competing_facts: list[Fact]` (минимум 2)
  - `resolution: Literal["newer_wins", "registered_wins", "unresolved"]`
  - `winning_fact_index: int | None` (индекс в `competing_facts`)

- **`EtpProfile`** — минимальный контракт по фикстуре `parser/tests/fixtures/etp/object_etp_profile_sample.json`: ключи `object_etp_profile[]` с полями `source`, `confidence`, `building_extra`, `risks`, `extras`. Schema_version и точные поля сверять с фикстурой в момент имплементации.

## 7. Требования к тестам

- `test_workspace.py::test_creates_memorandum_idempotent` — повторный вызов на готовом `Memorandum/` не пересоздаёт, файлы не перезатёрты.
- `test_workspace.py::test_fuzzy_match_collision` — есть «memorandum» (lowercase) → поведение совпадает с v3 (`_resolve_existing_or_new` возвращает существующую при ответе [1]).
- `test_inputs_finder.py::test_finds_market_analysis_recursively` — `market_analysis.txt` лежит на 3 уровня глубже, найден; источник записан в лог.
- `test_inputs_finder.py::test_skips_service_dirs` — копия `market_analysis.txt` в `.git/` или `node_modules/` НЕ выбирается.
- `test_inputs_finder.py::test_mtime_ordering` — два совпадения, берётся более свежий.
- `test_response_handler.py::test_market_template_idempotency` — повторный прогон одинаковых тегов не плодит дубль (SHA-256 содержимого до и после совпадают).
- `test_response_handler.py::test_missing_tags_warning` — отсутствие тегов → warning, файл не перезаписан.
- `test_temporal.py::test_conflict_resolution` — две выписки на разные даты → выбрана свежая; равные даты → registered побеждает document_date.
- `test_router.py::test_split_by_marp_marker` — корректное разделение по `<!-- MARP_START -->`.
- `test_router.py::test_missing_marker` — отсутствие маркера → всё в `final_report.md`, `investment_slides.md` пустой + warning.
- `test_state_machine.py::test_happy_path` — полный прогон от validation до done.
- `test_state_machine.py::test_awaiting_user_input_target_scenario` — пустой `target_scenario` → 202 + статус.

Все LLM-вызовы в тестах мочатся (`anthropic` клиент через `unittest.mock`); реальная сеть в CI запрещена.

## 8. Конфигурация (`.env.example`)

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

LOT_WORKSPACE_ROOT=D:/ОБЪЕКТЫ
PROMPTS_PATH=./obsidian/Prompts/llm_memorandum_pipeline

LLM_TIMEOUT_S=120
LLM_RETRIES=3

FUZZY_MATCH_THRESHOLD=0.7
AUTO_YES=false
```

## 9. Запуск (для будущей реализации)

```bash
pip install -e .
cp .env.example .env  # вписать ANTHROPIC_API_KEY
uvicorn lot_orchestrator.main:app --reload
```

Открыть `http://localhost:8000/`, выбрать рабочую папку лота, нажать «Run».

## 10. Out of scope первой реализации

- Production-deploy (Docker, k8s).
- Authentication / authorization.
- Multi-tenant.
- Streaming UI результатов в реальном времени.
- Поддержка других LLM-провайдеров (только Claude по CLAUDE.md).
- Marp-рендер в HTML/PDF (оператор делает сам).
- Автогенерация YAML-карточек из голосовых заметок / фото.

## 11. Связь с этой папкой spec'а

Оркестратор читает промпты из `PROMPTS_PATH` (env), не дублируя их в коде. При изменении любого `.md` промпта правка вступает в силу без передеплоя backend'а.

При изменении v3-паттерна (или появлении `pirushin_sosn_rocha_07_init_project_v4.py`) нужно синхронизировать `workspace.py`, `workspace_contract.md` и §7 тестов.
