# ЭТП-экспорт для viewer

Артефакты экспорта `object_etp_profile` / `lots` / `lot_items` из БД в формате,
байт-в-байт совместимом с фикстурой
`parser/tests/fixtures/etp/object_etp_profile_sample.json`.

## Контракт пути

Viewer на GitHub Pages читает экспорт через fetch по предсказуемому пути:

| Сценарий | Путь | Применение |
|---|---|---|
| Глобальный экспорт | `parser/exports/etp/object_etp_profile.json` | Все профили и лоты из БД. Stage 4b default. |
| Project-фильтр | `parser/exports/etp/<project_slug>/object_etp_profile.json` | Только лоты `lot:<project_slug>:*` + их КН. |

Имя файла — `object_etp_profile.json` (не меняется).

## Регенерация

```bash
# Глобально:
python -m parser.exporters.etp.export_json_cli --db path/to/ekcelo.sqlite

# Project-specific:
python -m parser.exporters.etp.export_json_cli --db path/to/ekcelo.sqlite --project pirushin
```

Выходной путь печатается в stdout. Файл коммитится в репо вручную после
проверки экономистом.

## Формат

См. `obsidian/Architecture/etl-osv.md` и `parser/tests/fixtures/etp/FIXTURE_NOTES.md` —
один и тот же контракт.

Топ-уровневые `$schema_version` / `$source` / `$project_slug` — метаданные;
viewer их игнорирует. Основные массивы:

```json
{
  "$schema_version": "1.0",
  "$source": "parser/exporters/etp/export_json.py",
  "$project_slug": "pirushin" | null,
  "object_etp_profile": [...],
  "lots": [...],
  "lot_items": [...]
}
```

## Workflow

1. Экономист правит YAML (`parser/inbox/etp/<YYYY-MM-DD>-<slug>.yml`) — через
   admin/etp-profile/<cad_number> UI viewer-team либо вручную.
2. Parser-A прогоняет ETL:
   `python -m parser.exporters.etp.etl_osv_cli --yaml <input> --db <db>`.
3. Parser-A регенерирует экспорт:
   `python -m parser.exporters.etp.export_json_cli --db <db>`.
4. Коммит экспорта в репо → viewer fetch автоматически подхватывает.

## Связи

- `obsidian/Architecture/etl-osv.md` — write-API контракт (YAML → БД).
- `parser/tests/test_export_json.py` — 13 тестов формата экспорта.
- CORRESPONDENCE/026 (PR #60) — согласование с viewer-team.
- viewer roadmap: `obsidian/Changelog/2026-05-28-etp-viewer-roadmap.md`.
