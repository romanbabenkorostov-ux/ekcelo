# 2026-05-28 — ЭТП-экспортёр Stage 4b: JSON-экспорт БД для viewer

## Итог
Закрыт второй trigger viewer-team из их roadmap: экспорт `object_etp_profile` /
`lots` / `lot_items` в JSON по предсказуемому пути в репо. Формат байт-в-байт
совпадает с фикстурой Phase 1 — viewer переключает fetch одной строкой.

## Артефакты
- `parser/exporters/etp/export_json.py` — `build_export_payload(conn, *, project_slug)` + `write_export(conn, out_root, *, project_slug)`.
- `parser/exporters/etp/export_json_cli.py` — CLI `python -m parser.exporters.etp.export_json_cli --db <path> [--out <dir>] [--project <slug>]`.
- `parser/exports/etp/` — новый каталог; baseline экспорт `object_etp_profile.json` сгенерирован из template (3.8 КБ).
- `parser/exports/etp/EXPORT_NOTES.md` — контракт пути + workflow + ссылки.
- `parser/inbox/etp/README_INBOX.md` — конвенция «куда класть YAML survey-листы».
- `parser/inbox/etp/_applied/.gitkeep` — каталог для apply-архива.
- `parser/tests/test_export_json.py` — 13 тестов (формат, project-фильтр, CLI).
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы», «Использование» (новый Stage 4b CLI + полный пайплайн «экономист → ЭТП»), «Гэпы».

## Ответы viewer-team на 2 вопроса
1. **Где экспорт окажется доступен:** `parser/exports/etp/[<project_slug>/]object_etp_profile.json` (в репо; GitHub Pages читает напрямую).
2. **`<project>` ID:** соответствует второму сегменту `lot_id` шаблона `lot:<slug>:NNN`. Фильтр опционален — без `--project` экспортируется всё.

## Workflow «экономист → ЭТП»
```
1. YAML  →  parser/inbox/etp/<date>-<slug>.yml
2. etl_osv_cli       →  БД (UPSERT профилей/лотов)
3. export_json_cli   →  parser/exports/etp/object_etp_profile.json (для viewer)
4. cli (Stage 3)     →  out/etp/<lot>/description.{short,full}.txt + appendix.md (для оператора ЭТП)
```

## Тесты (13/13 pass)
- 4 build_export_payload (global, project filter, no-match, metadata).
- 3 формат совместим с фикстурой (profile/lot keys, JSON columns deserialized).
- 3 write_export (default path, project subdir, creates dirs).
- 3 CLI (writes file, project filter, missing-db exit).

Полный прогон ЭТП-набора: **111/111 pass** (предыдущие 98 + 13 новых).

## Следующий шаг
- viewer-team: запуск работ над `admin/etp-profile/<cad_number>` (два trigger'а закрыты).
- parser-A: NSPD-enrichment, ETL EXIF → БД, Jinja-grammar refactor.

## Связи
- PR #62 (Stage 4 ETL, dependency).
- viewer roadmap: `obsidian/Changelog/2026-05-28-etp-viewer-roadmap.md` (PR #63).
- CORRESPONDENCE/026 (PR #60, merged).
- write-API контракт: `obsidian/Architecture/etl-osv.md`.
