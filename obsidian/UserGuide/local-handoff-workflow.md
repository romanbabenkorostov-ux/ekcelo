# Локальный workflow передачи: zip-архив → push через VS Code

> Резервный канал доставки, когда git-push из sandbox через прокси не проходит
> (см. сессию 2026-06-03: «Invalid username or token» на обоих PAT). Использовать,
> пока не починен прямой push. Применяется к любому подэтапу.

## Принцип

1. AI (Claude) собирает архив с **только новыми/изменёнными** файлами по их
   относительным путям от корня репо.
2. Пользователь распаковывает в корень своего клона (`E:\Code\ekcelo\ftontback2026-01-02\`).
3. Пользователь создаёт ветку, коммитит, пушит через `git` в VS Code.
4. Открывает PR по URL, который GitHub печатает после `git push`.

## Что лежит внутри архива

```
<archive_root>/
├── HANDOFF.md          # инструкция для этого конкретного подэтапа
├── files/              # все новые/изменённые файлы по относительным путям
│   └── <repo-relative>/
└── manifest.json       # список файлов + sha256 + базовая ветка + имя новой
```

`HANDOFF.md` всегда указывает: какая ветка, какие тесты ожидаются, какой
commit-message использовать, какой текст PR.

## Procedure (Win10 PowerShell + VS Code)

### Шаг 1 — Распаковать архив

```powershell
cd C:\Users\Соня\Downloads
# Распаковка средствами Windows (правый клик → Extract All) ИЛИ:
Expand-Archive -Path .\ekcelo-<subtask>-<YYYY-MM-DD>.zip -DestinationPath .\ekcelo-handoff -Force
cd .\ekcelo-handoff
# Прочитать HANDOFF.md перед копированием!
notepad HANDOFF.md
```

### Шаг 2 — Скопировать файлы в клон

```powershell
# Из распакованного архива → в корень клона.
# `files/` повторяет структуру репо, поэтому копируем СОДЕРЖИМОЕ files/ в корень.
Copy-Item -Recurse -Force -Path .\files\* -Destination "E:\Code\ekcelo\ftontback2026-01-02\"
```

### Шаг 3 — Открыть в VS Code

```powershell
cd E:\Code\ekcelo\ftontback2026-01-02
code .
```

В VS Code → панель Source Control (Ctrl+Shift+G) — увидите список изменённых
файлов. Сверьте с `manifest.json` из архива.

### Шаг 4 — Создать ветку, коммит, push

В VS Code открыть встроенный терминал (`` Ctrl+` ``):

```powershell
# Активировать venv (на случай если будете прогонять тесты локально):
.\.venv\Scripts\Activate.ps1

# Опц. локально проверить тесты:
python -m pytest backend/tests/ lot_orchestrator/tests/ lot_orchestrator_web/tests/ -q
python -m parser.exporters.etp.smoke_cli   # 33/33

# Команды из HANDOFF.md (имя ветки и commit-message — оттуда):
git checkout main
git pull origin main
git checkout -b <branch-from-HANDOFF>
git add -A
git commit -m "<commit-message-from-HANDOFF>"
git push -u origin <branch-from-HANDOFF>
```

После `git push` GitHub печатает URL вида:
```
remote: Create a pull request for '<branch>' on GitHub by visiting:
remote:      https://github.com/romanbabenkorostov-ux/ekcelo/pull/new/<branch>
```

### Шаг 5 — Открыть PR в GitHub UI

Открыть URL из вывода `git push`. На странице:
- **Title:** взять из HANDOFF.md «PR title».
- **Description:** скопировать содержимое HANDOFF.md «PR body» секции.
- **Base:** `main` (по умолчанию).
- Нажать «Create pull request».

### Шаг 6 — Сообщить мне номер PR

В чате: «открыл PR #NNN». Я сверю, что всё применилось правильно, и продолжу
с следующим подэтапом.

## Troubleshooting

### `git pull origin main` → conflict с моими файлами

Если на main кто-то параллельно мерджил такое же — `git status` покажет conflict.
Решите его в VS Code (3-way merge view) или верните мне `git diff` — я подскажу.

### `git push` → 403 / auth fail

Это **не наша проблема** в этом workflow — push идёт с вашей машины с вашими
GitHub-кредами, обычно работает. Если не работает:
- GitHub Desktop вместо CLI git
- VS Code → Source Control → ... → «Push» (использует ваши credentials helper)

### Распакованный архив затёр незакоммиченные локальные правки

`Copy-Item -Force` тихо перезаписывает. Перед распаковкой убедитесь, что у
вас нет несохранённых правок в репо: `git status`. Если есть — сначала
`git stash`, потом распаковка + копирование, потом `git stash pop`.

### Тесты падают локально

Установите extras: `pip install -e ".[dev]"`. Если падает только smoke
`test_required_modules_list_matches_package` — значит у вас старая копия
`smoke_cli.py`; распакуйте архив повторно или возьмите из main: `git
checkout main -- parser/exporters/etp/smoke_cli.py`.

## Что в архиве НЕ лежит

- **Удалённые файлы** (если были) — указаны в `HANDOFF.md` как «удалить вручную».
- Файлы вне корня репо (никогда не должно быть).
- Бинарные артефакты (`.pyc`, `__pycache__/`).

## Связи

- `obsidian/Architecture/handoff-onboarding.md` — въезд новой команды.
- `obsidian/CHECKPOINT.md` — текущая точка разработки.
- `.claude/skills/checkpoint/SKILL.md` — процедура AI при завершении подэтапа.
- `obsidian/UserGuide/clone-and-run.md` — первичный клон + запуск.
