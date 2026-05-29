# 2026-05-29 — Bulk-pipeline CLI: вся пачка YAML из inbox одной командой

## Итог
Добавлен `etl_pipeline_cli.py` — обработка всех YAML из `parser/inbox/etp/` одной командой с auto-export/auto-commit и опц. перемещением применённых файлов в `_applied/<YYYY-MM-DD>/`.

## Артефакты
- `parser/exporters/etp/etl_pipeline_cli.py` — bulk-CLI:
  - `--db <path>` — обязательный.
  - `--inbox <dir>` (default: `parser/inbox/etp/`) — откуда брать YAML.
  - `--dry-run` — только валидация, БД и inbox не меняются.
  - `--move-applied` — успешные YAML → `<inbox>/_applied/<YYYY-MM-DD>/`.
  - `--export` / `--commit` / `--export-out` / `--export-project` / `--commit-author` — общие auto-export флаги (как у поштучных CLI).
- `parser/tests/test_etl_pipeline_cli.py` — 10 тестов.
- `parser/inbox/etp/README_INBOX.md` — секция Workflow обновлена: поштучно vs bulk, с примерами.

## Поведение
- Сортировка YAML по имени файла (детерминистичный порядок применения).
- Партиальные ошибки: один битый файл не останавливает остальные. Failed → `[FAIL]` в stderr с причиной, остаётся в inbox. RC=3 если хотя бы один failed.
- `--move-applied` перемещает только успешные. С коллизией имени (`a.yml` уже в `_applied/`) добавляется суффикс `.1`, `.2`, ….
- `--export` дёргается ОДИН раз в конце (не на каждый YAML), даёт `source_label="osv-bulk"`.
- `--dry-run` обнуляет всё, в т.ч. экспорт и перемещение.

## Workflow (новый, one-liner для типичной операции)

```bash
# Экономист сложил несколько YAML в parser/inbox/etp/
python -m parser.exporters.etp.etl_pipeline_cli \
    --db ekcelo.sqlite \
    --move-applied \
    --export --commit
```

После прогона:
- БД содержит все profiles/lots/lot_items из YAML'ов.
- `parser/exports/etp/object_etp_profile.json` обновлён.
- Успешные YAML → `parser/inbox/etp/_applied/<YYYY-MM-DD>/`.
- Один автоматический commit в репо с message `chore(etp): auto-export object_etp_profile.json from osv-bulk`.
- Остаётся ручной `git push` (по принципу 069: экономист видит дельту перед публикацией).

## Тесты (10/10 pass)
- empty inbox → rc=0 («no-yaml»).
- 2 файла применяются в алфавитном порядке (БД содержит 2 профиля).
- Битый YAML не блокирует остальные → rc=3, корректные применены.
- `--dry-run` ничего не меняет (БД пустая, экспорт пропущен).
- `--move-applied` перемещает успешные в `_applied/<today>/`.
- `--move-applied` + битый файл → битый остаётся в inbox.
- `--export` после bulk создаёт JSON.
- Missing db → rc=2.
- Missing inbox → rc=2.
- Только `.yml/.yaml` берутся; `README.md` пропускается.

## Связи
- PR #69 (auto-export hook), #73 (auto-commit hook) — переиспользуем `auto_export.py`.
- PR #62 (Stage 4 ETL OSV) — основа.
- `parser/inbox/etp/README_INBOX.md` — обновлён.
