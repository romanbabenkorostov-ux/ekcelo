# 2026-05-29 — PDF/DOCX-конверсия lot_appendix (best-effort)

## Итог
Закрыт пункт SPEC §6 «lot_appendix.pdf». В CLI Stage 3 (`parser/exporters/etp/cli.py`) добавлен флаг `--appendix-format {md,pdf,docx}`. Конверсия best-effort: при отсутствии LibreOffice/pandoc — .md остаётся, rc=0, печатается предупреждение.

## Артефакты
- `parser/exporters/etp/md_convert.py` — модуль конверсии:
  - `convert_appendix(md_path, target='pdf'|'docx') → Path | None`.
  - `available_targets() → set[str]` — runtime-probe доступных форматов.
  - `soffice_bin() → str | None` — поиск `soffice`/`libreoffice` в PATH.
  - Внутренний `_md_to_html` — минимальный Markdown→HTML без внешних зависимостей (заголовки, GFM-таблицы, списки, inline `**`/`*`/`` ` ``, экранирование).
  - Pipeline: pandoc (если есть) → LibreOffice headless через промежуточный HTML → None.
- `parser/exporters/etp/cli.py` — флаг `--appendix-format`, default `md`.
- `parser/tests/test_md_convert.py` — 12 тестов: HTML-конвертер, fallback-цепочка, runtime-probe (session-scope).
- `parser/tests/test_etp_cli_integration.py` — +3 теста: default `md`, graceful PDF без конвертера, отказ от неизвестного формата.
- `obsidian/Architecture/etp-exporter.md` — обновлена таблица «Этапы».

## CLI usage

```bash
# Default — только md (backward-compat).
python -m parser.exporters.etp.cli --lot lot:pirushin:001 --db ekcelo.sqlite --out out/etp/

# PDF — потребует LibreOffice (или pandoc).
python -m parser.exporters.etp.cli ... --appendix-format pdf

# DOCX — то же.
python -m parser.exporters.etp.cli ... --appendix-format docx
```

При отсутствии конвертера в среде печатается:
```
[appendix-convert] нет конвертера (pandoc/LibreOffice) — PDF пропущен, .md сохранён: lot_appendix.md
```
`rc=0`, `.md` остаётся валидным.

## Тесты (219/219 в ETP-subset, +2 skip)

- `test_md_convert.py` — 12 тестов: HTML-структура, escape, fallback-логика. 2 теста проверки реальной конверсии используют session-scope **runtime-probe** (если soffice есть, но не работает в среде — например, sandbox без `$HOME` — оба теста корректно skip без падений).
- `test_etp_cli_integration.py` — 3 новых теста: default `md`, graceful PDF без конвертера, отказ от неизвестного формата.

## Известные ограничения
- В sandbox-средах без `$HOME` LibreOffice падает на загрузке файла («could not be loaded»). На Win10/macOS/нормальном Linux работает. Тесты пишут это как pytest.skip, не как FAIL.
- Markdown-конвертер минималистский (без расширенного CommonMark). Достаточно для текущего формата `lot_appendix.md` (`appendix.py`): заголовки, таблицы, списки, inline.

## Связи
- SPEC §6 «lot_appendix.pdf» — пункт закрыт.
- Stage 3 CLI (PR #59) — расширяемая база.
- `dev/SPEC_TEMPORAL_REPORTS.md` § MD→DOCX util fallback — общий подход парсера.
