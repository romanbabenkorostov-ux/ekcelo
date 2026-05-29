# Inbox: ОСВ survey-листы экономиста

Сюда экономист (или admin/etp-profile/<cad_number> UI viewer-team) кладёт
YAML survey-листы для импорта в БД.

## Naming

`<YYYY-MM-DD>-<slug>.yml`, где `<slug>` — kebab-case (например, имя проекта
или ФИО экономиста). Примеры:
- `2026-06-01-pirushin-v1.yml`
- `2026-06-02-sosna-rocha-fix.yml`

## Workflow

### Поштучно (один файл)

```bash
python -m parser.exporters.etp.etl_osv_cli \
    --yaml parser/inbox/etp/2026-06-01-<slug>.yml \
    --db ekcelo.sqlite \
    --export --commit
```

### Bulk (вся пачка одной командой)

```bash
python -m parser.exporters.etp.etl_pipeline_cli \
    --db ekcelo.sqlite \
    --move-applied \
    --export --commit
```

После прогона успешно применённые YAML переезжают в `_applied/<YYYY-MM-DD>/`
(история в репо для аудит-trail). Битые YAML остаются в inbox для разбора —
exit code 3 сигнализирует partial failure.

`--export --commit` обновляют viewer-JSON один раз в конце и коммитят
автоматически.

## Контракт

Формат YAML: `obsidian/Architecture/etl-osv.md`.
Шаблон: `parser/exporters/etp/templates/osv_template.yaml`.

## Не для коммита

Только YAML-файлы (`.yml`/`.yaml`) и этот README.
