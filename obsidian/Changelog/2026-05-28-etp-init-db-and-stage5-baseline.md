# 2026-05-28 — init-db CLI + Stage 5 поля в baseline

## Итог
Закрыты два пункта одного цикла:
1. **Блокер `db not found`** — добавлен `init_db_cli` для bootstrap dev-БД одной командой.
2. **Test plan PR #71 от viewer-team** — baseline `parser/exports/etp/object_etp_profile.json` теперь содержит Stage 5 поля (`building_type`, `year_built`, `use_type_permitted`). После merge PR #71 viewer покажет «Конструкция» / «Разрешённое использование» в карточке без отдельного NSPD прогона.

## Артефакты
- `parser/exporters/etp/init_db_cli.py` — `python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite [--with-template] [--force]`.
- `parser/exporters/etp/templates/osv_template.yaml` — добавлены 3 поля в baseline профиль `:31`:
  - `building_extra.building_type: "кирпичное"`
  - `building_extra.year_built: 1975`
  - `legal_extra.use_type_permitted: "административно-офисные помещения; деловые услуги"`
- `parser/exports/etp/object_etp_profile.json` — регенерирован через init+template+export, теперь содержит Stage 5 поля.
- `parser/tests/test_init_db_cli.py` — 6 тестов (create new, baseline objects, with-template, force, exists guard, Stage 5 fields).
- `obsidian/Architecture/etp-exporter.md` — секция «CLI: инициализация dev-БД».

## Workflow смоук-теста (один файл инструкции)

```powershell
# Windows
cd E:\Code\ekcelo\code
python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite --with-template
python -m parser.exporters.etp.export_json_cli --db ekcelo.sqlite
# теперь parser/exports/etp/object_etp_profile.json свежий — viewer fetch покажет Stage 5 поля
python -m http.server 8000
# открыть: http://localhost:8000/viewer/admin-etp-profile.html?cad=61:44:0050706:31
```

## Тесты (70/70 pass из задействованного подмножества)
- 6 init_db_cli.
- Регрессия etl_osv / export_json / build_lot_context / text_render — без изменений.

## Связи
- PR #71 (viewer Stage 5/6 поля) — этот baseline обновляется ради их test plan.
- PR #62 / #64 / #65 / #67 / #69 — пайплайн ETL → JSON-экспорт без изменений.
- ADR-001 — `source` / `confidence` модель сохраняется (template = `osv` / `1.0`).
