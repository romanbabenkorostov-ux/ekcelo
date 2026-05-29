# 2026-05-28 — Windows фиксы (auto-commit, goldens CRLF) + справочник зависимостей

## Итог
Закрыты два Windows-баги пользовательского репорта + создан канон-документ
зависимостей в obsidian.

## Закрытые баги

### 1. `auto_export.py` — двойная склейка путей `--commit`

**Симптом:**
```
[commit-skipped] git add failed: warning: could not open directory
  'parser/exports/etp/parser/exports/etp/': No such file or directory
fatal: pathspec 'parser\exports\etp\object_etp_profile.json' did not match
```

**Причина:** `_git_commit_export` использовал `cwd=out_path.parent` И передавал относительный `out_path` как pathspec. На Windows git склеивал cwd + pathspec.

**Фикс:** `cwd` не переопределяем; путь к файлу — абсолютный (`out_path.resolve()`). Git ищет .git автоматически от текущего cwd процесса.

### 2. `test_text_render` — golden mismatches на Windows-checkout

**Симптом:** 6 из 8 голден-тестов FAILED после `git pull` на Windows (CRLF вместо LF).

**Причина:** git `autocrlf=true` на Windows конвертировал LF→CRLF при checkout, render возвращает строки с `\n`, файл прочитывался с `\r\n`.

**Фикс (двойной):**
1. **`.gitattributes`** — фиксирует LF для goldens, фикстур, шаблонов, миграций, Python: при checkout всегда LF независимо от `core.autocrlf`.
2. **`_read_golden(path)`** в тестах — нормализует `\r\n→\n` при чтении (страховка для пользователей, у которых файлы уже на диске с CRLF).

## Артефакты

- `parser/exporters/etp/auto_export.py` — fix `_git_commit_export` пути.
- `.gitattributes` — фиксация LF для текстовых артефактов.
- `parser/tests/test_text_render.py` — нормализация `\r\n→\n` через helper.
- `parser/tests/test_etp_cli_integration.py` — то же для CLI golden-сверки.
- `parser/tests/test_auto_commit_hook.py` — новый тест `test_commit_works_with_relative_out_path` (регрессия Windows-бага).
- `obsidian/Architecture/dependencies.md` — справочник зависимостей: Python ≥3.10, runtime (8 пакетов), optional (`fastapi`/`uvicorn`), dev (pytest), viewer-side.

## Тесты (199/199 pass)
- Auto-commit suite расширен с 6 до 7 тестов (новый — relative path).
- test_text_render все 18 проходят на Linux; на Windows ожидаемо после
  `git rm --cached parser/tests/golden/etp/*.txt && git add` + `.gitattributes`
  или прямого pull после мерджа этого PR.

## Связанная dependency-документация

Зафиксировано в `obsidian/Architecture/dependencies.md`:
- Все 8 runtime-пакетов: `pdfplumber`, `python-docx`, `openpyxl`, `jinja2`, `pyyaml`, `piexif`, `Pillow`, `pymorphy3` (+ `pymorphy3-dicts-ru`).
- Optional `api` группа.
- Dev-инструменты (`pytest`).
- Viewer-side (`vis-network`).
- Когда добавляется новая зависимость — обновляется и этот документ.

## Связи
- PR #73 (auto-commit hook) — бэг попал в main.
- PR #74 (morphology + pymorphy3) — добавил pymorphy3 deps.
- `obsidian/Architecture/dependencies.md` — новый sticky-документ.
