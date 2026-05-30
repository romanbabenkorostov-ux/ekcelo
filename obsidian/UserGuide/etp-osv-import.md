# Импорт OSV survey-листа в БД

> Как загрузить YAML-survey экономиста (отделка, инженерка, риски) в `object_etp_profile`.

## Когда использовать

После того как ЕГРН разобран и в БД появились объекты с КН. OSV-импорт добавляет «non-EGRN» гэп-поля для генерации развёрнутого описания.

## Формат YAML

Берите шаблон: `parser/exporters/etp/templates/osv_template.yaml`.

Ключевые секции:

```yaml
schema_version: "1.0"
default_source: osv          # osv | exif | manual | nspd | llm
default_confidence: 1.0

profiles:
  - cad_number: "61:44:0050706:31"
    location_extra: { landmark, transport_access, environment_short }
    building_extra: { building_type, year_built, renovation_year, wear_degree,
                      engineering: {electricity, water, ...}, amenities: [...] }
    layout: { layout_type, ceiling_height_m, finish_level, finish_state, ... }
    legal_extra: { use_type_fact, zoning, special_restrictions: [...] }
    risks: { technical_risks, legal_risks, location_risks, other_risks }
    extras: { furniture, advantages, notes }

lots:
  - lot_id: "lot:pirushin:001"
    name: "..."
    platform_targets: [torgi.gov.ru, sberbank-ast.ru]
    procedure_type: "реализации имущества должника в рамках дела о банкротстве"
    deal_type: sale            # sale | lease | other
    primary_cad_number: "61:44:0050706:31"
    items:
      - { cad_number: "61:44:0050706:31", role: room, ord: 1 }
      - { cad_number: "61:44:0050706:7",  role: land, ord: 2 }
```

## Naming

Кладите файлы в `parser/inbox/etp/` с именем `<YYYY-MM-DD>-<slug>.yml`:

- `2026-06-01-pirushin-v1.yml`
- `2026-06-02-sosna-rocha-fix.yml`

## Запуск (поштучно)

```bash
python -m parser.exporters.etp.etl_osv_cli \
    --yaml parser/inbox/etp/2026-06-01-pirushin-v1.yml \
    --db ekcelo.sqlite \
    --export --commit
```

`--export --commit` перегенерируют JSON-экспорт для viewer'а и сделают git-commit.

## Запуск (bulk — вся пачка)

```bash
python -m parser.exporters.etp.etl_pipeline_cli \
    --db ekcelo.sqlite \
    --move-applied \
    --export --commit
```

Это:
1. Найдёт все `*.yml` / `*.yaml` в `parser/inbox/etp/`.
2. Применит в алфавитном порядке.
3. Успешные → `parser/inbox/etp/_applied/<YYYY-MM-DD>/` (если `--move-applied`).
4. Битые останутся в inbox; rc=3 если хотя бы один битый.
5. JSON-экспорт + commit — один раз в конце.

## Что меняется в БД

| Таблица | Изменение |
|---|---|
| `object_etp_profile` | UPSERT по `cad_number` (gap-fill: existing osv/manual fields НЕ перезатираются) |
| `lots` | INSERT новых лотов; existing — игнорируются (см. флаг `--update-lots` для перезаписи) |
| `lot_items` | INSERT записей; existing идемпотентно |

## Troubleshooting

### `FOREIGN KEY constraint failed`

У YAML есть `cad_number`, которого нет в `objects` таблице. Сначала загрузите ЕГРН-выписку (через `egrn_parser`), потом импортируйте OSV.

### `YAML schema_version mismatch: got 2.0, expected 1.0`

Шаблон обновился. Сверьте свой YAML с актуальным `osv_template.yaml`.

### Не вижу свои данные в выгрузке viewer'а

Запустите экспорт вручную:

```bash
python -m parser.exporters.etp.export_json_cli --db ekcelo.sqlite
```

Или используйте `--export` флаг при импорте OSV.

### Хочу обновить уже импортированный лот

По умолчанию повторный импорт того же `lot_id` — no-op. Если хотите перезаписать профиль/лот:

```bash
python -m parser.exporters.etp.etl_osv_cli --yaml ... --db ... --force
```

⚠️ `--force` перезатирает ВСЕ поля профиля, даже `manual`. Используйте с осторожностью.

## Что дальше

- Сгенерировать карточку: [[etp-export]].
- Подтянуть данные о юрлицах: [[etp-checko]].
