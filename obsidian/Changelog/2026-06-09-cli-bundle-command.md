# 2026-06-09 — CLI `egrn-parser bundle` + Windows-фикс per-object имён

## Windows-фикс bundle_assembler (по прогону заказчика)
`test_assemble_object_bundle` падал на Windows: `json/objects/<cad>.json` с `:` в КН
→ `WinError 123`. Добавлен `bundle_assembler.mask_cad` (`:`→`_`, `/`→`-`): per-object
файлы пишутся в Windows-safe маске (`61:44:0050706:31` → `61_44_0050706_31.json`).
Тест обновлён.

## CLI-команда `bundle` (item 4 → golden-path) — `cli.py::cmd_bundle`
`egrn-parser bundle --out DIR --kmz project.kmz --db db.sqlite [--kind object|lot]
[--json …] [--objects-json-dir DIR] [--raw …] [--objects КН…] [--primary-cad КН]
[--extract-date YYYY-MM-DD] [--lot-id ID]`:
- при `--lot-id` читает состав лота из `--db` (`lot_assembler.lot_manifest`) →
  `kind=lot`, `objects=members`, lot-фрагмент в manifest;
- флаг `etp_layer_present` — из `--db` (`etp_merge.etp_layer_present`);
- `--objects-json-dir` → `json/objects/<stem>.json`; собирает каталог через
  `bundle_assembler.assemble_bundle`, печатает сводку.
- 10-я команда CLI (рядом с parse/export/…/folders).

## Тесты
- `test_bundle_assembler.py` +`test_cli_bundle_lot_from_db`: CLI читает лот из БД,
  kind=lot, members, etp_layer=True, verify зелёный. **17 passed** (с manifest/lot).

## Файлы
- `parser/egrn_parser/bundle_assembler.py` (+mask_cad)
- `parser/egrn_parser/cli.py` (+cmd_bundle + subparser)
- `parser/tests/test_bundle_assembler.py` (+CLI-тест, masked-путь)
- `docs/specs/SPEC_parser.md` (CLI 10 команд, item 4 ✅)
