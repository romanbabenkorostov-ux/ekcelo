# Установка ekcelo

## Системные требования

- **Python 3.11+** (3.13 рекомендуется).
- Windows 10/11 или Linux. macOS — не тестировался, может работать.
- **Git** — для клонирования.
- **SQLite 3.37+** — обычно идёт с Python.

## Базовая установка (только ЭТП-экспортёр)

```bash
git clone https://github.com/romanbabenkorostov-ux/ekcelo.git
cd ekcelo
pip install -e .
```

Проверка:

```bash
python -m parser.exporters.etp.smoke_cli
# Должен вывести "smoke: 32/32 passed" и rc=0.
```

## Дополнительные модули (extras)

| extras | Что включает | Когда нужен |
|---|---|---|
| `[orchestrator]` | Pydantic + anthropic SDK + pyyaml — backend оркестратора (CLI) | Если используете меморандум-пайплайн |
| `[orchestrator-web]` | FastAPI + Jinja2 + uvicorn + python-multipart — web-UI | Если экономист работает через браузер |
| `[orchestrator-redis]` | + redis-клиент для multi-worker production deploy | Production-инсталляция на нескольких worker'ах |
| `[dev]` | pytest + pytest-cov + httpx — для разработчиков | Если запускаете тесты |

Установка с конкретным extras:

```bash
pip install -e ".[orchestrator]"             # backend оркестратора
pip install -e ".[orchestrator-web]"         # + web
pip install -e ".[orchestrator,orchestrator-web,orchestrator-redis]"  # full prod
```

## Конфигурация (для оркестратора)

Создайте `.env` в корне проекта:

```dotenv
# Обязательно для production:
ANTHROPIC_API_KEY=sk-ant-...

# Опционально (значения по умолчанию):
ANTHROPIC_MODEL=claude-sonnet-4-6
LLM_TIMEOUT_S=120
LLM_RETRIES=3
FUZZY_MATCH_THRESHOLD=0.7
AUTO_YES=false

# Только для production multi-worker:
# REDIS_URL=redis://localhost:6379/0
# PERSISTENCE_DB=./runs.sqlite
```

`.env` НЕ коммитится в git (см. `.gitignore`).

## Troubleshooting

### `ModuleNotFoundError: No module named 'parser.exporters.etp.auto_export'`

После `git pull` могли появиться новые модули. Перезапустите установку:

```bash
pip install -e .
```

Если не помогает — запустите smoke-test, он подскажет какие модули не импортируются:

```bash
python -m parser.exporters.etp.smoke_cli
```

### `ANTHROPIC_API_KEY не задан` (при работе оркестратора)

Положите ключ в `.env` или экспортируйте в shell:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Linux/Mac
$env:ANTHROPIC_API_KEY="sk-ant-..."   # Windows PowerShell
```

Для smoke-теста ключ не нужен — используйте `--mock-llm` или `--dry-run`.

### `openpyxl/pdfplumber not found` при `pytest parser/`

Это extras для `egrn_parser`, не для ЭТП-экспортёра. Если они вам не нужны — игнорируйте; основные тесты пройдут без них.

Если нужны — установите:

```bash
pip install openpyxl pdfplumber
```

## Что дальше

- Базовый сценарий: [[etp-osv-import]] → [[etp-export]].
- Полный пайплайн с меморандумом: [[orchestrator-cli]] или [[orchestrator-web]].
