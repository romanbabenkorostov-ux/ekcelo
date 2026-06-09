# 2026-06-05 — Миграция 0004 (поля objects) + синк импортёра

## Суть
По нормативным аспектам выписки (П/0329) расширен §1 `objects`; импортёр Block-2
синхронизирован — заполняет новые поля, извлекает владельцев из прав и строит топологию.

## Сделано
- **`models_egrn.Object` + миграция `0004`** — 10 полей: `quarter_cad_number`,
  `parent_cad_number`, `inventory_number`, `conditional_number`, `cadastral_value`,
  `floor`, `okato`, `kladr`, `fias_guid`, `status_egrn` (все nullable, аддитивно).
- **`import_block2` синк:**
  - заполняет новые поля из `land_objects`/`building_objects` (`conditional_number` —
    из `old_numbers`, `permitted_use` — из `permitted_uses`);
  - **владелец из прав:** `right_holders` ИЛИ `rights.beneficiary_inn/name` →
    `Subject` + ребро (фикс прошлого `subjects=1`);
  - **топология:** `parent_cad_number` / `land_cad_numbers` → рёбра `CONTAINS`
    (ЗУ→ОКС→помещение) — объекты связываются в граф.
  - общий идемпотентный `get_or_create_subject` (по ИНН).

## Проверено (SQLite)
- `upgrade head` 0001→0004; downgrade round-trip — ок.
- Синтетика: новые поля заполнены; владелец из `beneficiary_inn` → `subjects`;
  CONTAINS land→building→room. `pytest contracts/db/tests` — **3 passed**.

## Эффект на боевых данных
Ранее: `subjects=1, relations=19`. Теперь владельцы создаются из прав (много ЮЛ) +
топология CONTAINS на 126 объектов → граф наполняется собственностью и вложенностью.

## Не покрыто (Block-2 не отдаёт отдельно)
`okato/kladr/fias_guid` — в Block-2 адрес одной строкой; останутся NULL до отдельного
парсинга `address_fias` (XML). Поле в схеме готово.

## Дальше
Этап 2 — классификатор ЕГРЮЛ (руководитель + правопреемство) в реальном ingest.
