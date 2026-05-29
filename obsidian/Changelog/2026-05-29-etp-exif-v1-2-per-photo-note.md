# 2026-05-29 — EXIF v1.1 → v1.2: per-фото `note` (parser-side)

## Итог
Ratify proposal'а CORRESPONDENCE/027 (ack viewer-team в посте 028, 5/5 accept).
Parser-side bump схемы EXIF UserComment + расширение Stage 6 ETL EXIF
агрегацией `note`-полей в `object_etp_profile.extras.notes`.

## Артефакты
- `docs/EXIF_USERCOMMENT_SCHEMA.md` — bump v1.1 → v1.2: добавлено опц. поле
  `note` (string \| null) в payload `kind:"photo"`. Версия в шапке и в
  таблице «История».
- `parser/exporters/etp/etl_exif.py`:
  - `ExifPhotoMeta.note` — новое поле в датаклассе.
  - `scan_directory` сортирует JPG для детерминистичного порядка merge.
  - `enrich_from_exif` собирает уникальные note по cad (preserve insertion
    order) и передаёт в `_apply_exif_to_profile`.
  - `_apply_exif_to_profile(..., notes)` — новый второй позиционный
    параметр. Idempotent gap-fill: новые note добавляются в существующее
    `extras.notes` joined `«; »`, дубликаты пропускаются.
  - Если у JPG нет ни category, ни note — `skipped_reason =
    "no_categories_or_notes_in_exif"`.
  - Если оба уже зафиксированы — `"photo_summary_and_notes_already_present"`.
- `parser/tests/test_etl_exif.py` — +7 тестов v1.2:
  - aggregated_into_extras_notes
  - only_without_category_still_creates_profile
  - merged_with_existing_extras_notes
  - idempotent_no_duplicate
  - truncated_to_1000_chars
  - duplicate_notes_across_jpgs_deduped
  - backward_compat_v11_photo_without_note
  + 2 правки старых тестов под новые строки `skipped_reason`.
- `.gitattributes` — добавлено `viewer/*.html`, `viewer/*.js`,
  `viewer/**/*.js text eol=lf` (просьба viewer-team из 028 §уточнение).

## Поведение
- **v1.1 backward-compat:** JPG без `note` работают как раньше; v1.2-ридер
  на них не падает.
- **`note` ограничивается 1000 символами** (safety: предотвращает
  взрывной рост `extras.notes` от непредвиденных payload'ов).
- **Дедупликация при сборе:** одна и та же строка `note` на нескольких
  JPG → одна строка в БД.
- **Merge с существующим `extras.notes`:** ручной ввод экономиста (`source=osv`)
  сохраняется, EXIF-note добавляется в конец `«; »`. Не перетирается.
- **Параллельно с категориями:** `advantages` («Комплексная фотофиксация:
  …») по-прежнему формируется из category; `notes` — новый параллельный
  канал из note. Оба идемпотентны.

## Тесты (25/25 etl_exif + 206/206 в полном прогоне)

Прежние 18 + 7 новых v1.2. Регрессия по всему ЭТП-набору — без изменений.

## Что viewer-side (отдельный PR от viewer-team)
Согласно посту 028:
- Lightbox-ридер читает `note` из EXIF UserComment payload `kind:"photo"`
  (через `exifr`).
- Если `note` отсутствует/`null` — поле не показывается (v1.1 backward-compat).
- Поле ввода `note` в admin-etp-profile YAML-генераторе — отдельный PR.

## Связи
- CORRESPONDENCE/027 (parser proposal, PR #76, merged).
- CORRESPONDENCE/028 (viewer ack 5/5, в bundle `claude/magical-mccarthy-3ZyU4`).
- Stage 6 PR #67 — расширяемая база.
- ADR-001 §6 — `extras` как часть не-ЕГРН слоя.

## Что осталось
- viewer-side lightbox `note`-ридер (отдельным PR, у viewer-team).
- Поле ввода `note` в admin-etp-profile YAML-генераторе (отдельным PR).
