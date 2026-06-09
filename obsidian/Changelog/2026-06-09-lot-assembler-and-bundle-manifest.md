# 2026-06-09 — Lot-сборщик (C5) + Bundle-manifest эмиттер (C3)

Заход в смежный трек SPEC_parser (item 4 Bundle / item 6 Lot-сборщик).

## Lot-сборщик (C5, item 6) — `egrn_parser/lot_assembler.py`
- `select_members(conn, include, exclude, as_of)` — отбор из `objects`:
  - правила include/exclude = `{cads:[], globs:[], types:[]}` (явные КН / маски
    fnmatch / по object_type); exclude вычитается;
  - `as_of` (YYYY-MM-DD) — снимок: отсекает объекты с `updated_at > as_of`;
  - детерминированный порядок (сортировка по cad_number).
- `assemble_lot(...)` — запись `lots` (upsert) + `lot_items` (чистая пересборка,
  роль по object_type: land/building/construction→structure/flat→room/equipment,
  переопределение через `roles`); возвращает фрагмент `manifest.lot`.
- `lot_manifest(...)` — `{lot_id, as_of_date, include, exclude, members[]}` по
  контракту `bundle.schema.json`. Идемпотентно/детерминированно (round-trip = тот
  же members[]).

## Bundle-manifest эмиттер (C3, item 4) — `egrn_parser/bundle_manifest.py`
- `sha256_file`/`file_entry` — `files[] {path, sha256, bytes}` (sha256 байт, потоково).
- `build_manifest(kind, files, objects, lot?, …)` — manifest по
  `contracts/bundle/bundle.schema.json` (только allowed-keys, conditional lot).
- `validate_manifest` — лёгкая проверка формы: required, semver, sha256 hex64,
  `kind=lot ⇒ блок lot`, extract_date YYYY-MM-DD, lot.members/as_of_date.
- Сборку каталога (kmz/db/json) оставляет golden-path; здесь — детерминированный
  манифест + валидатор.

## Тесты
- `tests/test_lot_assembler.py` (+6): globs/types, exclude>include, as_of-фильтр,
  запись lots/lot_items + manifest, идемпотентность, override роли.
- `tests/test_bundle_manifest.py` (+5): sha256/file_entry, object-manifest,
  lot end-to-end (assemble→manifest), отлов ошибок формы, запрет лишних ключей.
- 11 passed (трек), полный прогон зелёный.

## Файлы
- `parser/egrn_parser/lot_assembler.py` (новый)
- `parser/egrn_parser/bundle_manifest.py` (новый)
- `parser/tests/test_lot_assembler.py`, `parser/tests/test_bundle_manifest.py` (новые)
- `docs/specs/SPEC_parser.md` (items 4/6 ✅)

## Остаток (Bundle полный)
Оркестрация каталога бандла (project.kmz+db.sqlite+json/ + запись manifest.json) —
golden-path стадия после 08; ядро (manifest+хеши+lot-состав) готово.
