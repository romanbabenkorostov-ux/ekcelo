# 2026-09-12 — Контуры выписок в БД: §8 `egrn_contour` (шаг 2/3)

**Ветка:** `claude/gifted-hamilton-3s65de` · **ADR:** [[ADR-007-msk-to-wgs84]]
**Схема:** [[egrn-geometry-8]] · **Предыдущий шаг:** [[2026-09-12-egrn-xml-contours-msk]] (PR #142, смержен)

## Что сделано

Шаг 1 извлекал контуры в память. Теперь они доезжают до базы.

| Файл | Что |
|---|---|
| `schema/migrations/0006_egrn_geometry.sql` | §8: `egrn_contour` + `v_egrn_parcel_contour` + `v_egrn_geometry_summary` |
| `schema/egrn_current_schema.sql` | зеркало §8 в канон (как §7 зеркалит 0003) — **дополнение в конец файла, существующее не тронуто** |
| `parser/egrn_parser/parsers/xml_geometry_db.py` | Запись: `egrn_contour` + витрины `object_geometries` и `land_contours` |
| `parser/egrn_parser/parsers/xml_geometry.py` | +`to_geojson()`, `centroid_wgs84()`, реквизиты выписки (`extract_number`, `extract_date`) |
| `parser/scripts/01d_egrn_xml_to_db.py` | CLI по образцу соседнего `01c_contours_to_db.py` |
| `parser/tests/test_xml_geometry_db.py` | 19 тестов |

`cli.py` не трогался: вход сделан отдельным скриптом, как `01b`/`01c`.

## Проверено сквозным прогоном

```
python3 scripts/01d_egrn_xml_to_db.py --xml <папка> --db egrn.db
  ✓ 26:29:130106:382: контуров 1, ЧЗУ 2; 1985.6 м² против 1986 м² — сходится
  ✓ 26:29:130106:334: контуров 1, ЧЗУ 1; 4415.6 м² против 4416 м² — сходится
  ✗ 26:29:110104:105: в выписке нет геометрии; привязан к 26:29:130106:72, 26:29:130322:7
файлов: 3; записано: 2; контуров: 2; чзу: 3; пропущено: 1
```

Повторный прогон не создаёт дублей: 5 строк (2 контура + 3 ЧЗУ) остаются 5.
Витрины заполняются: `object_geometries` (MultiPolygon + WKT, `geom_source='egrn_xml'`),
`land_contours` (через существующий `upsert_geometry_contours`).

Тесты: 19 новых, `62 passed` вместе со всей геометрией и ADR-005.

## Три решения, за которые придётся отвечать позже

1. **Гейт по площади включён по умолчанию.** Выписка с несошедшейся площадью
   НЕ пишется; `--force` / `strict=False` снимает гейт, но результат остаётся
   виден как `v_egrn_geometry_summary.area_check_ok = 0`. Причина в ADR-007 §2:
   неверная зона МСК не падает, а врёт красиво.
2. **ЧЗУ лежат в одной таблице с контурами участка**, различаются `kind`.
   Складывать их площади нельзя никогда — ЧЗУ внутри участка. Для этого и
   заведено `v_egrn_parcel_contour`: правильный запрос короче неправильного.
3. **DDL написан дважды** (миграция + канон), как и §7. Расхождение ловит тест
   `test_canonical_schema_mirrors_migration` — иначе оно всплыло бы на фронте
   через полгода.

## Следующий шаг (3/3)

Экспорт KML по `docs/CONTRACT_KMZ.md` 2.13.0 (префикс `cad_zu_*`, папка
«Земельные участки», `<description>` парами `Ключ: значение; `, `kml_schema_version`),
эссе `.md` по выписке и PySide6-оболочка поверх обоих.
