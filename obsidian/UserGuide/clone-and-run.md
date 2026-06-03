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

> ⚠️ **Важно**: venv должен быть создан **внутри корня клона** (`ftontback2026-01-02\.venv\`), а не в соседнем проекте. Активация venv из чужого проекта приводит к `ModuleNotFoundError: No module named 'backend'` — у того venv нет нужных зависимостей и Python ищет пакет не там.

```powershell
# Win10 PowerShell — обязательно ВНУТРИ ftontback2026-01-02\
cd E:\Code\ekcelo\ftontback2026-01-02
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
cd ~/Code/ekcelo/ftontback2026-01-02
python -m venv .venv
source .venv/bin/activate
```

После активации проверьте: `where python` (Win10) или `which python` (Linux) должен показывать путь внутри `.venv\Scripts\` или `.venv/bin/`. Если показывает другой путь — деактивируйте чужой venv (`deactivate`) и активируйте свой.

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

### Рекомендуемый способ — через `serve.py`

```powershell
python serve.py
```

Этот лаунчер:
- Выставляет `PYTHONPATH=<корень_клона>`, чтобы `uvicorn --reload` корректно находил `backend.*` (без него падает `ModuleNotFoundError: No module named 'backend'`).
- Предупреждает, если активен venv из другого проекта.
- Включает auto-reload по умолчанию (`--no-reload` для отключения).

Дополнительные флаги:

```powershell
python serve.py --port 9000                 # кастомный порт
python serve.py --host 0.0.0.0              # listen на всех интерфейсах
python serve.py --no-reload                 # выключить watcher
python serve.py --log-level debug
```

После старта откройте в браузере:

- http://localhost:8000/ — главная с перечнем endpoints.
- http://localhost:8000/docs — Swagger UI.
- http://localhost:8000/redoc — ReDoc.

### Альтернатива — uvicorn напрямую

Если не хотите использовать лаунчер — добавьте `--app-dir .`:

```powershell
uvicorn --app-dir . backend.app.main:app --reload --port 8000
```

Без `--app-dir .` Python не найдёт пакет `backend` — это та же ошибка, что бросает прямой `uvicorn backend.app.main:app`.

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

> ⚠️ **Откройте именно `/viewer/index.html`**, а не корень `/`. `http.server` отдаёт листинг папки на `/`, что выглядит как «сайт пустой».

Прямые ссылки:

- http://localhost:8001/viewer/index.html — главная карта + KMZ-загрузчик.
- http://localhost:8001/viewer/admin-etp-profile.html — редактор ЭТП-профиля.

Через UI «Загрузить KMZ» загрузите любой `.kmz` из `parser/scripts/` или собранный по [[golden-path]].

> Если используете VS Code расширение **Live Server** (Ritwick Dey):
> 1. Установить расширение Live Server.
> 2. Правый клик на `viewer/index.html` → `Open with Live Server`.
> 3. Откроется на http://localhost:5500/viewer/index.html (порт настраивается).

## Шаг 8 — Проверка end-to-end

Терминал 1: backend

```powershell
python serve.py --port 8000
```

Терминал 2: frontend

```powershell
python -m http.server 8001
# Откройте http://localhost:8001/viewer/index.html
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

### `ModuleNotFoundError: No module named 'backend'` при запуске uvicorn

uvicorn запущен из активного venv, но текущий каталог не добавлен в `sys.path`. С `--reload` это ещё хуже: reloader-подпроцесс не наследует sys.path-изменения родителя.

Три способа починить (в порядке предпочтения):

```powershell
# 1. (рекомендуется) — лаунчер выставляет PYTHONPATH автоматически:
python serve.py --reload

# 2. передать --app-dir в uvicorn:
uvicorn --app-dir . backend.app.main:app --reload

# 3. вручную выставить env-переменную:
$env:PYTHONPATH = "."
uvicorn backend.app.main:app --reload
```

### Активирован чужой venv (`E:\Code\...\другой_проект\venv`)

Симптом: `python serve.py` пишет `WARNING: активный venv находится вне корня репо` или после `pip install` всё равно `ModuleNotFoundError`.

Причина: пользователь активировал venv из соседнего проекта (`сoder_exif` и т.п.). У того venv свои зависимости и Python ищет пакеты не там.

Фикс:

```powershell
deactivate                                # выйти из чужого venv
cd E:\Code\ekcelo\ftontback2026-01-02
python -m venv .venv                      # создать свой
.\.venv\Scripts\Activate.ps1              # активировать его
pip install fastapi "uvicorn[standard]" jinja2 python-multipart httpx2 pydantic anthropic pyyaml pymorphy3 pymorphy3-dicts-ru
python serve.py                           # запуск
```

### `http.server` показывает листинг папки на http://localhost:8001/

Это нормально для встроенного сервера Python — `/` отдаёт листинг текущего каталога. Откройте полный путь до viewer'а: **http://localhost:8001/viewer/index.html**.

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
