# 2026-05-28 — Auto-commit hook для ETL CLI

## Итог
Расширение auto-export hook (PR #69). Все три ETL CLI получили флаги `--commit` / `--commit-author`. После `--export` записи JSON хук дополнительно делает `git add` + `git commit` — workflow «YAML → БД → JSON → commit» теперь one-liner.

## Артефакты
- `parser/exporters/etp/auto_export.py` — расширен helper:
  - `add_export_args()` регистрирует `--commit` + `--commit-author`.
  - `run_export_if_requested(..., source_label)` принимает метку источника для commit message.
  - `_git_commit_export()` — безопасный subprocess-вызов `git add` + `git commit`.
  - Проверки: каталог внутри git-репо, есть ли изменения (no-op если diff пуст), есть ли git в PATH.
- `parser/exporters/etp/etl_osv_cli.py` — передаёт `source_label="osv"`.
- `parser/exporters/etp/nspd_enrich_cli.py` — передаёт `source_label="nspd"`.
- `parser/exporters/etp/etl_exif_cli.py` — передаёт `source_label="exif"`.
- `parser/tests/test_auto_commit_hook.py` — 6 тестов в изолированных git-репо.
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы» и «Auto-export / commit hook».

## Поведение `--commit`
- Без `--commit` → backward-compat (только экспорт).
- `--commit` + ничего не изменилось → `[commit-noop]` (нет пустого коммита).
- `--commit` вне git-репо → `[commit-skipped] не внутри git-репо` (не падает).
- `--commit` + `--dry-run` → пропускается вместе с экспортом.
- Commit message: `chore(etp): auto-export object_etp_profile.json from osv` (или `nspd`/`exif`).

## Тесты (6/6 pass)
- Создаёт коммит в репо.
- No-op при повторном прогоне без изменений.
- Skip без падения вне git-репо.
- `--dry-run` подавляет коммит.
- `--commit-author` override работает.
- Без флага `--commit` — коммита нет.

Тесты используют env-override `GIT_CONFIG_*` чтобы подавить глобальный gpg-sign, иначе в CI среде с обязательной подписью init-commit'ы падали.

Полный прогон ЭТП-набора: **183/183 pass**.

## Workflow

**Было:**
```bash
python -m parser.exporters.etp.etl_osv_cli --yaml ... --db ... --export
git add parser/exports/etp/object_etp_profile.json
git commit -m "..."
```

**Стало:**
```bash
python -m parser.exporters.etp.etl_osv_cli --yaml ... --db ... --export --commit
```

`git push` остаётся ручным — экономист видит дельту перед публикацией.

## Связи
- PR #69 (auto-export hook) — этот PR расширяет.
- Не меняет контракт `etl-osv.md` (флаги дополнительные).
- Безопасное поведение: пропускает скип-сценарии вместо падения.

## Что осталось
- Морфология русского (pymorphy3) — отдельный PR.
- EXIF v1.2 per-photo заметки — требует bump схемы EXIF.
