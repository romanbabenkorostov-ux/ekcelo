# §9 — Ручные контуры и конфликты (`manual_contour`, `contour_conflict`)

**Миграция:** `schema/migrations/0007_manual_contours_and_layout.sql` · **Канон:** §9
**ADR:** [[ADR-008-manual-contours-and-conflicts]] · **Связанные:** [[egrn-geometry-8]], [[geo-entities-7]]
**Код:** `parser/egrn_parser/parsers/manual_contours.py` · **Вход:** `parser/scripts/01f_manual_contours.py`

## Где слой стоит

| Слой | Что | Восстанавливается из выписок | Есть `confidence` |
|---|---|---|---|
| §8 `egrn_contour` | контуры из выписки ЕГРН | да | нет (есть `accuracy_m`) |
| **§9 `manual_contour`** | **обводка человеком по карте** | **нет** | **да** |
| §7 `geo_entity` | прочее не-ЕГРН гео (KMZ, НСПД) | нет | да |

§8 и §9 не сливаются в одну таблицу намеренно: §8 воспроизводится из выписок
целиком, и ручная обводка, попав туда, ломает этот инвариант.

## Единственный правильный вопрос к базе

```sql
-- Какой контур считать текущим по объекту
SELECT * FROM v_object_contour_current WHERE cad_number = ?;
```

Прямое чтение `egrn_contour` или `manual_contour` в обход этого представления
даёт контур, который может быть не тем: при открытом конфликте текущим остаётся
ручной, при решении `use_egrn` — из выписки.

Логика представления словами:

- есть контур ЕГРН и (ручного нет ИЛИ конфликт решён как `use_egrn` ИЛИ ручной
  отозван) → текущий из выписки;
- иначе есть живой ручной → текущий ручной (в том числе пока конфликт в
  `pending`);
- иначе объект без геометрии.

## Жизненный цикл конфликта

```
ручная обводка загружена        приходит выписка с контуром
        │                                │
        ▼                                ▼
 manual_contour                  egrn_contour (§8)
        └──────────── detect_conflicts ──┘
                        │
                contour_conflict (resolution='pending')
                        │            текущий = РУЧНОЙ
          ┌─────────────┴─────────────┐
   'keep_manual'                  'use_egrn'
   текущий = ручной               текущий = ЕГРН
   §8 не тронут                   ручной → retired_at (не удалён)
```

## Типовые запросы

```sql
-- Что ждёт решения человека
SELECT * FROM v_contour_conflicts_open;

-- История решений по объекту
SELECT resolution, resolved_by, resolved_at, resolution_note
  FROM contour_conflict WHERE cad_number = ? ORDER BY detected_at;

-- Объекты, живущие на ручной обводке (в отчёте помечать)
SELECT cad_number, area_computed_sqm, confidence
  FROM v_object_contour_current WHERE contour_source = 'manual';

-- Отозванные обводки — на них могли ссылаться подписанные акты
SELECT cad_number, retired_at, retired_reason, source_file, author
  FROM manual_contour WHERE retired_at IS NOT NULL;
```

## Раскладка участка (`egrn_contour.land_layout`)

`ЗУ` — один контур; `МКУ` — несколько контуров под одним КН, неотделимых;
`ЕЗП` — единое землепользование, где каждый контур сам объект учёта со своим
номером в `contour_cad`. Признак ЕЗП — собственный КН у контура, а не их число:
многоконтурный ЕЗП и МКУ по числу контуров неотличимы.

## Чего в §9 нет

- **Автоматического разрешения конфликта.** Это решение человека по
  определению — см. ADR-008 §2.
- **Удаления.** Ни обводка, ни контур выписки не стираются никогда: на них
  ссылаются уже сданные работы.
