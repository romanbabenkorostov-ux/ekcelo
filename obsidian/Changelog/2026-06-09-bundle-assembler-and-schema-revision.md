# 2026-06-09 — Bundle-оркестратор каталога + ревизия db/schema.sql ↔ C2 (item 3/4)

ETL-консолидация подтверждена заказчиком: **98 passed, 0 failed**.

## Bundle-оркестратор (item 4, завершён) — `egrn_parser/bundle_assembler.py`
- `assemble_bundle(out_dir, kmz, db, json_files, objects_json, raw_files, kind,
  objects, lot?, …)` — собирает каталог по BUNDLE_SPEC:
  `project.kmz` + `db.sqlite` + `json/<...>` + `json/objects/<cad>.json` +
  опц. `raw/<...>`, пишет `manifest.json` (через `bundle_manifest`, отсортированный
  files[], детерминированно по содержимому).
- `verify_bundle(out_dir)` — целостность: manifest валиден, файлы есть, sha256 сходятся.
- Lot-фрагмент — из `lot_assembler.lot_manifest`; флаг §6 — `etp_merge.etp_layer_present`.
- Тесты `test_bundle_assembler.py` (+5): object/lot-бандл, детерминизм sha256
  (разный generated_at → те же хеши файлов), детект порчи, kind=lot требует lot-блок.
  16 passed (с bundle_manifest/lot_assembler).

## Ревизия db/schema.sql ↔ C2 (item 3, задокументирована)
`obsidian/Architecture/schema-pkg-vs-c2-drift.md`:
- **Два разных модели**, не дрейф: пакет (`egrn_parser/db/schema.sql`, 24 табл.,
  building_objects/land_objects раздельно) vs C2 (`schema/egrn_current_schema.sql`,
  8 табл., унифицированная `objects` + §6 ЭТП).
- Только в C2: objects/object_restrictions/lots/lot_items/object_etp_profile.
- Общие по имени (entity_registry/extracts/rights) — расходятся по колонкам
  (пакет богаче; extracts/rights структурно различны).
- **Рекомендация:** C2 — канон обмена (ADR-001); пакет — parser-internal, обязан
  *экспортировать* §1–§5 в C2-форму (слой exporters), не совпадать по таблицам.
  Реконсиляция — отдельный ADR «pkg-schema ↔ C2 export mapping», не прямое слияние
  (риск для контракта C2 с backend/viewer).

## Файлы
- `parser/egrn_parser/bundle_assembler.py` (новый)
- `parser/tests/test_bundle_assembler.py` (новый)
- `obsidian/Architecture/schema-pkg-vs-c2-drift.md` (новый)
- `docs/specs/SPEC_parser.md` (item 3 ✅ сверка, item 4 ✅ оркестратор)
