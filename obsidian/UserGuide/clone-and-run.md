# Клонирование проекта в новую папку + запуск

> Полная инструкция «с нуля до работающего фронт+бэк» в новой папке (например, `E:\Code\ekcelo\ftontback2026-01-02`). Аудитория: пользователь Win10 (PowerShell) или Linux/macOS.

## Что получите

- Полная копия репозитория (parser + lot_orchestrator + lot_orchestrator_web + viewer + obsidian + docs).
- Активное виртуальное окружение Python.
- Работающий backend (FastAPI на http://localhost:8000).
- Работающий frontend-viewer (статический http server на http://localhost:8001).

## Предусловия

- Установлены: **Git**, **Python 3.11+**, **VS Code** (рекомендуется).
- В Win10 — открыта PowerShell (правый клик → Open in Terminal).

## Шаг 1 — Клонирование

### Из VS Code (рекомендуется)

1. Открыть VS Code → меню `View` → `Command Palette` (Ctrl+Shift+P).
2. Команда `Git: Clone`.
3. URL: `https://github.com/romanbabenkorostov-ux/ekcelo.git`.
4. Папка-родитель: `E:\Code\ekcelo\` → имя клона: `ftontback2026-01-02` (или VS Code предложит выбрать только родителя и склонирует с дефолтным именем `ekcelo` — после клона можно переименовать).

Если в Git Clone-диалоге нельзя задать кастомное имя:

```powershell
cd E:\Code\ekcelo
git clone https://github.com/romanbabenkorostov-ux/ekcelo.git ftontback2026-01-02
```

### Из PowerShell (альтернатива)

```powershell
cd E:\Code\ekcelo
git clone https://github.com/romanbabenkorostov-ux/ekcelo.git ftontback2026-01-02
cd ftontback2026-01-02
```

### На Linux/macOS

```bash
mkdir -p ~/Code/ekcelo
cd ~/Code/ekcelo
git clone https://github.com/romanbabenkorostov-ux/ekcelo.git ftontback2026-01-02
cd ftontback2026-01-02
```

## Шаг 2 — Переключение на ветку

По умолчанию клон на `main`. Если нужна актуальная ветка после всех merges:

```powershell
git checkout main
git pull origin main
```

Чтобы посмотреть открытые feature-ветки (на момент 2026-05-30 это #90, #92, #93):

```powershell
git fetch --all
git branch -r | findstr orchestrator   # Win10
git branch -r | grep orchestrator      # Linux/macOS
```

Для bleeding-edge сборки (с непрослеженными PR):

```powershell
git checkout orchestrator/cycle-11-12-httpx2-migration
```

## Шаг 3 — Открытие в VS Code

```powershell
code .
```

Принять предложения расширений (Python, Pylance). Выбрать Python-интерпретатор после Шага 4.

## Шаг 4 — Виртуальное окружение + зависимости

```powershell
# Win10 PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python -m venv .venv
source .venv/bin/activate
```

Если PowerShell ругается на execution policy:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Установка зависимостей. Базовый набор (только parser + smoke):

```powershell
pip install -e .
```

Полный набор (backend + redis + dev-инструменты):

```powershell
pip install -e ".[dev]"
```

> Внимание: `pyproject.toml` с extras появится в main только после merge PR #92. До этого момента ставьте конкретные пакеты вручную:
> ```powershell
> pip install fastapi "uvicorn[standard]" jinja2 python-multipart httpx2 pydantic anthropic pyyaml pymorphy3 pymorphy3-dicts-ru redis fakeredis pytest pytest-cov
> ```

## Шаг 5 — Smoke-проверка

```powershell
python -m parser.exporters.etp.smoke_cli
```

Ожидаемый вывод: `smoke: 33/33 passed`. Если что-то падает — см. секцию Troubleshooting ниже.

## Шаг 6 — Запуск backend (FastAPI)

### Базовый dev-режим

```powershell
uvicorn lot_orchestrator_web.main:app --reload --port 8000
```

После старта откройте в браузере:

- http://localhost:8000/ — главная страница с перечнем endpoints.
- http://localhost:8000/docs — Swagger UI (интерактивная документация).
- http://localhost:8000/redoc — ReDoc.

### После merge PR #92 — через console script

```powershell
ekcelo-orchestrate-web --reload --port 8000
```

С persistence (runs переживают рестарт):

```powershell
ekcelo-orchestrate-web --persistence-db .\runs.sqlite
```

С Basic Auth (после PR #93):

```powershell
ekcelo-orchestrate-web --auth-users "alice:secret"
```

## Шаг 7 — Запуск frontend (viewer)

Viewer — статический сайт, работает через любой HTTP-сервер:

```powershell
# Win10/Linux/macOS — встроенный Python server
cd E:\Code\ekcelo\ftontback2026-01-02   # из корня репо
python -m http.server 8001
```

Открыть в браузере: http://localhost:8001/viewer/index.html

Через UI «Загрузить KMZ» загрузите любой `.kmz` из `parser/scripts/` или собранный по [[golden-path]].

> Если используете VS Code расширение **Live Server** (Ritwick Dey):
> 1. Установить расширение Live Server.
> 2. Правый клик на `viewer/index.html` → `Open with Live Server`.
> 3. Откроется на http://localhost:5500/viewer/index.html (порт настраивается).

## Шаг 8 — Проверка end-to-end

Терминал 1: backend

```powershell
uvicorn lot_orchestrator_web.main:app --reload --port 8000
```

Терминал 2: frontend

```powershell
python -m http.server 8001
```

Терминал 3: smoke

```powershell
.\.venv\Scripts\Activate.ps1
python -m parser.exporters.etp.smoke_cli
curl http://localhost:8000/openapi.json | findstr "paths"
curl http://localhost:8001/viewer/index.html -o NUL -w "%%{http_code}\n"
```

Ожидаемо: smoke=`33/33 passed`, openapi=6 paths, viewer=200.

## Troubleshooting

### `pip install -e .` ругается `setuptools <68 required`

Обновите setuptools: `python -m pip install -U pip setuptools wheel`.

### `ModuleNotFoundError: parser.exporters.etp.auto_export`

Не закончилась установка. Перезапустите `pip install -e .`. Если репродуцируется — `python -m parser.exporters.etp.smoke_cli` напишет, какой именно модуль не импортируется.

### `uvicorn: command not found`

Виртуальное окружение не активировано. Win10: `.\.venv\Scripts\Activate.ps1`. Linux: `source .venv/bin/activate`.

### `address already in use` при `python -m http.server 8001`

Порт занят. Используйте другой: `python -m http.server 8002`.

### `pdfplumber` / `openpyxl` отсутствуют при тестах

Это extras для `egrn_parser` (полный парсер PDF/XLSX). Если они вам не нужны — игнорируйте. Если нужны: `pip install pdfplumber openpyxl python-docx piexif Pillow` или после merge PR #92: `pip install -e ".[egrn-full]"`.

### Виртуальное окружение в VS Code не подхватывается

Ctrl+Shift+P → `Python: Select Interpreter` → выбрать `.venv\Scripts\python.exe` (Win10) или `.venv/bin/python` (Linux).

### Хочу bleeding-edge с непрослеженными PR

Список открытых PR: см. https://github.com/romanbabenkorostov-ux/ekcelo/pulls. Каждая feature-ветка содержит свои изменения; merge их локально через `git merge orchestrator/...`.

Безопаснее: ждите официального merge через GitHub UI.

## Что дальше

- Полный «золотой путь» от ЕГРН до KMZ: [[golden-path]].
- Установка зависимостей с подробностями: [[install]].
- Веб-сценарии меморандума: [[orchestrator-web]].
- CLI-сценарии меморандума: [[orchestrator-cli]].
- Импорт OSV survey-листов: [[etp-osv-import]].
