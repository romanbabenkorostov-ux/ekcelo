# §8 — Геометрия из выписок ЕГРН (`egrn_contour`)

**Миграция:** `schema/migrations/0006_egrn_geometry.sql` · **Канон:** `schema/egrn_current_schema.sql` §8
**ADR:** [[ADR-007-msk-to-wgs84]] · **Связанные:** [[geo-entities-7]], [[ADR-002-geo-entities]]
**Код:** `parser/egrn_parser/parsers/xml_geometry.py` (извлечение), `xml_geometry_db.py` (запись)
**Вход:** `parser/scripts/01d_egrn_xml_to_db.py`

## Где этот слой стоит среди остальных

| Слой | Что это | Восстанавливается из выписок |
|---|---|---|
| §1..§5 | Слепок ЕГРН: объекты, права, выписки, ограничения | да |
| §6 | ЭТП-профиль (ОСВ экономиста, EXIF, NSPD, LLM) | **нет** |
| §7 `geo_entity` | Гео не-ЕГРН: ручная обводка, KMZ, НСПД | **нет** |
| **§8 `egrn_contour`** | **Контуры из XML-выписки, подписанной ЭП** | **да** |

§8 и §7 намеренно не слиты в одну таблицу. Смешать «что сказал Росреестр» и
«что мы сами обвели по снимку» — значит потерять возможность пересобрать слепок
ЕГРН с нуля, а это базовый инвариант проекта (CLAUDE.md §3, ADR-001).

Отсюда же отсутствие `confidence`, который есть в §6 и §7: у документа
Росреестра нет «уверенности». У него есть **заявленная погрешность съёмки** —
`accuracy_m` (`delta_geopoint` выписки): 0.1 м у свежей съёмки, 2.5 м у
пересчёта из старых материалов. Это характеристика документа, а не наша оценка.

## Правило, которое нарушают первым

```sql
-- НЕВЕРНО: площадь лота с двойным учётом
SELECT SUM(area_computed_sqm) FROM egrn_contour WHERE cad_number = ?;

-- ВЕРНО
SELECT SUM(area_computed_sqm) FROM v_egrn_parcel_contour WHERE cad_number = ?;
```

Контуры участка (`kind='parcel'`) и контуры его частей — ЧЗУ (`kind='part'`) —
лежат в одной таблице, потому что структура строки у них совпадает полностью.
Но ЧЗУ (охранная зона ЛЭП, водоохранная полоса) находится **внутри** участка, и
сумма даёт площадь больше фактической. Представление `v_egrn_parcel_contour`
заведено ровно затем, чтобы правильный запрос был короче неправильного.

## Две площади в одной строке — не дублирование

`area_computed_sqm` (по координатам, формулой шнурования в метрах МСК) и
`area_declared_sqm` (из `params/area/value` той же выписки) хранятся обе
намеренно. Их расхождение — единственная проверка, которую парсер может
выполнить без обращения к внешним источникам, и она ловит неверные параметры
зоны МСК. А неверная зона не падает — она даёт правдоподобный контур не в том
месте (ADR-007 §2). Стереть одну из колонок = лишить базу возможности себя
перепроверить.

Готовый ответ — `v_egrn_geometry_summary.area_check_ok` (допуск 1% либо 1 м²,
повторяет `xml_geometry.AREA_TOLERANCE_*`; при изменении менять оба места).

## Куда ещё пишется геометрия

`xml_geometry_db.write_geometry` кладёт контур в три места:

| Таблица | Роль | Кто читает |
|---|---|---|
| `egrn_contour` | источник, все признаки выписки | KML, эссе, карточка |
| `object_geometries` | витрина, MultiPolygon + WKT, `geom_source='egrn_xml'` | `xlsx_exporter`, `graph_json` |
| `land_contours` | раскладка ЗУ/МКУ/ЕЗП (ADR-005) | `land_db`, будущий viewer |

`object_geometries` пишется только если таблица есть (она из схемы парсера);
`land_contours` создаётся `land_db.ensure_schema` при первой записи. Запись
идёт через существующий `upsert_geometry_contours` — он сам классифицирует
ЗУ/МКУ и не понижает уже известный ЕЗП. Своя логика раскладки здесь не
заводится: она разъедется с той.

## Идемпотентность

Ключ — `(cad_number, kind, COALESCE(part_number,''), contour_no)`, и он вынесен
в **выражение-индекс**, а не в табличный `UNIQUE`. Причина: у контуров участка
`part_number` равен NULL, а в SQLite `NULL <> NULL` — табличный `UNIQUE` их не
склеил бы, и каждая повторная загрузка той же выписки плодила бы дубли.

Реквизиты документа (`source_extract_number`, `extract_date`, `source_file`)
обновляются через `COALESCE`: повторный разбор без явно переданного номера не
стирает уже известный. Тот же приём — в `land_db.upsert_contours`.

## Типовые запросы

```sql
-- Контуры объекта для KML (по одному Placemark на строку)
SELECT contour_no, geom_geojson, area_computed_sqm, accuracy_m
  FROM v_egrn_parcel_contour WHERE cad_number = ? ORDER BY contour_no;

-- ЧЗУ со связью с ограничением: мнемоника содержит реестровый номер зоны
SELECT c.part_number, c.part_mnemonic, c.area_computed_sqm, r.description
  FROM egrn_contour c
  LEFT JOIN object_restrictions r
         ON c.part_mnemonic LIKE r.registry_number || '%'
 WHERE c.cad_number = ? AND c.kind = 'part';

-- Объекты, у которых площадь не сошлась (записаны через --force)
SELECT * FROM v_egrn_geometry_summary WHERE area_check_ok = 0;

-- Обособленные участки ЕЗП
SELECT contour_no, contour_cad FROM v_egrn_parcel_contour
 WHERE cad_number = ? AND contour_cad IS NOT NULL;
```

## Чего в §8 нет и не будет

- **Геометрии ОКС.** Выписка на здание (`extract_about_property_build`) координат
  не содержит вообще — это свойство формата, а не пробел разбора. Здание
  привязано к земле через `cad_links/land_cad_numbers`, и геометрия берётся у
  участка.
- **Контуров из НСПД/ПКК.** Они идут своим путём — `01c_contours_to_db.py` →
  `land_contours` с `geom_source='nspd:*'`. §8 — только про выписки.
