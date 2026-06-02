# Сборка меморандума через CLI

> Как собрать `final_report.md` + `investment_slides.md` по лоту через командную строку (без web-UI).

## Когда использовать

- Один лот, batch-операция, CI/release-pipeline.
- Нет браузера / нет желания запускать сервер.
- Нужно автоматизировать через cron/shell-скрипт.

Для интерактивного сценария см. [[orchestrator-web]].

> **API-ключ нужен только для реального LLM-вызова.** Для smoke / тестов / валидации входов работает без ключа через `--mock-llm` или `--dry-run`. См. [[install]] раздел «Когда нужен ANTHROPIC_API_KEY».

## Установка

```bash
pip install -e ".[orchestrator]"
```

## Подготовка рабочей папки лота

Структура (создаётся автоматически если нет):

```
<рабочая_папка>/
└── Memorandum/
    ├── _data/
    │   └── enrich_<lot_id>.json     # SSOT — собирается на Этапе 1 (intake)
    ├── incoming/
    │   └── market_analysis.txt      # ОБЯЗАТЕЛЬНО: аналитика рынка
    └── graph.html                   # ОПЦИОНАЛЬНО: граф связей бенефициаров
```

`enrich_<lot_id>.json` собирается отдельно через Этап 1 — copy-paste промптов из `obsidian/Prompts/llm_memorandum_pipeline/01_intake_and_pipeline.md` в claude.ai.

## Базовый запуск

```bash
export ANTHROPIC_API_KEY=sk-ant-...

python -m lot_orchestrator.cli \
    --workspace D:/ОБЪЕКТЫ/pirushin \
    --lot pirushin_001
```

## Smoke без API-ключа

```bash
python -m lot_orchestrator.cli \
    --workspace ./project \
    --lot test_001 \
    --mock-llm "Тестовый отчёт.
<!-- MARP_START -->
# Тестовый слайд"
```

## Параметры

| Параметр | Обязательный | Что делает |
|---|---|---|
| `--workspace` | да | Путь к рабочей папке лота. |
| `--lot` | да | `lot_id`. Regex `[A-Za-z0-9_:-]+`. |
| `--mock-llm <текст>` | нет | Использовать MockClient вместо anthropic. Текст становится «ответом LLM». |
| `--dry-run` | нет | MockClient с пустым текстом — для проверки валидации входов. |

## Что получите

```
<workspace>/Memorandum/
├── final_report.md              # Текст меморандума (до маркера MARP_START)
├── investment_slides.md         # Слайды Marp (после маркера)
├── market_template.md           # Карточка локации (если LLM выделил блок)
└── _data/
    └── _run_log.jsonl           # Журнал прогона (sha256 промптов, токены)
```

Marp-рендер в PDF/HTML — отдельная команда:

```bash
marp Memorandum/investment_slides.md -o Memorandum/slides.html
```

## Exit codes

| Код | Когда |
|---|---|
| `0` | DONE — все 4 фазы прошли. |
| `2` | AWAITING_USER_INPUT — нет SSOT или `target_scenario` неполный. |
| `3` | ERROR — Pydantic-валидация или нет `market_analysis.txt`. |
| `1` | Иная ошибка (uncaught). |

## Типичный workflow

```bash
# 1. Создать рабочую папку, положить market_analysis.txt в incoming/.
mkdir -p D:/ОБЪЕКТЫ/pirushin/Memorandum/{_data,incoming}
cp ~/Downloads/market_analysis.txt D:/ОБЪЕКТЫ/pirushin/Memorandum/incoming/

# 2. Собрать SSOT через Этап 1 в claude.ai → сохранить enrich_pirushin_001.json.
#    Положить в D:/ОБЪЕКТЫ/pirushin/Memorandum/_data/.

# 3. Smoke: проверить что валидация проходит без вызова LLM.
python -m lot_orchestrator.cli --workspace D:/ОБЪЕКТЫ/pirushin --lot pirushin_001 --dry-run

# 4. Полный прогон.
python -m lot_orchestrator.cli --workspace D:/ОБЪЕКТЫ/pirushin --lot pirushin_001

# 5. Рендер слайдов.
marp D:/ОБЪЕКТЫ/pirushin/Memorandum/investment_slides.md -o slides.html
```

## Troubleshooting

### Phase: AWAITING_USER_INPUT, warning «enrich_pirushin_001.json не найден»

Сначала пройдите Этап 1 (intake) — соберите SSOT через промпт в claude.ai и положите в `Memorandum/_data/enrich_<lot_id>.json`. См. `obsidian/Prompts/llm_memorandum_pipeline/01_intake_and_pipeline.md`.

### Phase: AWAITING_USER_INPUT, warning «target_scenario неполный»

В `enrich_<lot_id>.json` есть пустые поля в `target_scenario.{was, trigger, to_plan}`. Заполните все три.

### Phase: ERROR, error «обязательный вход 'market_analysis.txt' не найден»

Положите файл в `Memorandum/incoming/market_analysis.txt` или просто в любую подпапку workspace — оркестратор найдёт рекурсивно.

### Long timeout / нет ответа от LLM

Увеличьте таймаут:

```bash
LLM_TIMEOUT_S=300 python -m lot_orchestrator.cli ...
```

Или используйте более быструю модель:

```bash
ANTHROPIC_MODEL=claude-haiku-4-5-20251001 python -m lot_orchestrator.cli ...
```

### Result.routing.final_report содержит весь ответ, slides пустой

LLM не вставил маркер `<!-- MARP_START -->`. Это не bug пайплайна — посмотрите промпт `02_memorandum_prompt.md` и убедитесь что инструкция требует маркер.

## Связи

- web-сценарий: [[orchestrator-web]].
- архитектура: `obsidian/Architecture/lot-orchestrator.md`.
- спека: `obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md`.
