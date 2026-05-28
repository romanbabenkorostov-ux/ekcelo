# 2026-05-28 — ЭТП-экспортёр Stage 6: ETL EXIF → БД

## Итог
Закрыт последний пункт roadmap'а data-плоскости: EXIF UserComment → `object_etp_profile.extras`. Парсер теперь автоматически добавляет в профиль строку «Комплексная фотофиксация: …» на основании реально снятых фото объекта.

## Артефакты
- `parser/exporters/etp/etl_exif.py` — `scan_directory(dir) → list[ExifPhotoMeta]` + `enrich_from_exif(conn, photos) → list[ExifEnrichReport]` + `read_userComment(path) → dict | None`.
- `parser/exporters/etp/etl_exif_cli.py` — CLI `python -m parser.exporters.etp.etl_exif_cli --db ... --photos <dir> [--dry-run]`.
- `parser/tests/test_etl_exif.py` — 18 тестов (с реальной генерацией JPG через piexif+Pillow).
- `parser/pyproject.toml` — `piexif>=1.1`, `Pillow>=10.0` в deps.

## Поведение
- Источник — JPG-файлы с EXIF UserComment v1.1 (см. `docs/EXIF_USERCOMMENT_SCHEMA.md`).
- Принимаются только `app="ekcelo"` + `kind="photo"` (документы `kind="egrn"/"doc"` отфильтрованы).
- Группировка по `cad`. Для каждого КН — сводка категорий («Фасад», «Кровля», «Интерьер»…) в `extras.advantages[]` как строку `"Комплексная фотофиксация: <list>."`.
- **Никогда не перезаписывает существующие advantages** — добавляет элемент. Идемпотентно: повторный прогон с тем же набором фото → skip с `photo_summary_already_present`.
- Новые записи: `source='exif'`, `confidence=0.7`.
- FK к `objects` → skipped с `fk_error` (не падает на всём батче).

## Тесты (18/18 pass)
- 4 `read_userComment` (valid, no-exif, non-ekcelo payload, corrupted file).
- 2 `scan_directory` (recurses, skips non-ekcelo).
- 7 `enrich_from_exif` (create new, preserve existing advantages, idempotent, skip no-category, skip non-photo kind, group by cad, FK error).
- 5 CLI (writes, dry-run, empty dir, missing db, missing photos dir).

Полный прогон ЭТП-набора: **163/163 pass** (145 предыдущих + 18 новых; включая Stage 5 в локальной ветке).

## Что закрыто Stage 6
- ✅ ETL EXIF UserComment → БД (автообогащение из фото).

## Что осталось
- Auto-export hook (после `etl_*_cli` дёргать `export_json_cli` + коммит).
- Per-photo заметки экономиста (нужен bump EXIF UserComment схемы v1.1 → v1.2 — отдельный correspondence-цикл).
- Jinja-grammar refactor.

## Связи
- Source-of-truth для EXIF v1.1: `docs/EXIF_USERCOMMENT_SCHEMA.md`.
- Эмитент JPG: `parser/scripts/pirushin_sosn_rocha_07_init_project_v*.py`.
- ETP-направление: SPEC §7, ADR-001 (`source=exif`).
- ETL OSV (Stage 4, PR #62) + NSPD-enrichment (Stage 5, PR #65) — параллельные источники профиля.
