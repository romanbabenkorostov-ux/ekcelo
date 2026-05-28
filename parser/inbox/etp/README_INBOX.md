# Inbox: ОСВ survey-листы экономиста

Сюда экономист (или admin/etp-profile/<cad_number> UI viewer-team) кладёт
YAML survey-листы для импорта в БД.

## Naming

`<YYYY-MM-DD>-<slug>.yml`, где `<slug>` — kebab-case (например, имя проекта
или ФИО экономиста). Примеры:
- `2026-06-01-pirushin-v1.yml`
- `2026-06-02-sosna-rocha-fix.yml`

## Workflow

1. Положить YAML в этот каталог.
2. Parser-A (или CI-хук) запускает:
   ```bash
   python -m parser.exporters.etp.etl_osv_cli --yaml <input> --db <db>
   python -m parser.exporters.etp.export_json_cli --db <db>
   ```
3. После применения файл переносится в `parser/inbox/etp/_applied/`
   (история сохраняется в репо для аудит-trail).

## Контракт

Формат YAML: `obsidian/Architecture/etl-osv.md`.
Шаблон: `parser/exporters/etp/templates/osv_template.yaml`.

## Не для коммита

Только YAML-файлы (`.yml`/`.yaml`) и этот README.
