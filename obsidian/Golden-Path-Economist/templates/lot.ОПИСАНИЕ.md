# Описание шаблона: определение лота

**Файл:** `lot_TEMPLATE.yaml` · **Формат:** YAML · **→** `lots` / `lot_items`

## Что это
Что входит в лот (единицу продажи/оценки) и роли членов.

## Поля
- `lot_id`, `name`, `deal_type` (sale|lease|other), `procedure_type`, `primary_cad_number`,
  `platform_targets` (площадки).
- **Отбор состава** `include` (и опц. `exclude`): по `cads` (явные КН), `globs`
  (маска квартала, напр. `00:00:0000000:*`) или `types` (land/building/…).
- `items[]`: роли — `role ∈ land|building|room|equipment|structure`, порядок `ord`.

## Как загрузить
Через `etl_osv` (секция `lots`) ИЛИ командой `egrn-parser bundle --lot-id <id>`
(состав соберётся из БД правилами отбора).
