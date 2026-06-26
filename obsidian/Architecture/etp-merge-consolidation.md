# Консолидация ETL-писателей ЭТП-слоя на единую точку `etp_merge.merge_profile`

> SPEC_parser item 5 (развитие). `egrn_parser/etp_merge.merge_profile` — единая,
> протестированная точка записи в `object_etp_profile` (приоритет/gap-fill/additive).
> Ниже — точный маппинг существующих писателей на стратегии. **Рефактор применять
> там, где прогоняются ETL-тесты** (нужен `pymorphy3`; в среде разработки парсера
> тесты `test_etl_*`/`test_nspd_enricher` не собираются — pymorphy3/`parser.`-namespace).

## Примитив (готов, протестирован — `tests/test_etp_merge.py`, 10 passed)

```python
merge_profile(conn, cad, incoming, *, source, confidence,
              strategy="priority"|"gapfill", append_keys={col:[keys]})
```
- **priority** (по умолч.): источник с приоритетом ≥ ROW-источника перезаписывает
  поля; ниже — gap-fill. Приоритет `manual>osv>nspd>exif>llm`.
- **gapfill**: никогда не затирает существующее (чистое заполнение пустот).
- **append_keys**: аддитивное объединение списков/строк без дублей (для exif).

## Маппинг писателей → вызов

| Писатель | Что пишет | Стратегия | Вызов |
|---|---|---|---|
| `nspd_enricher.merge_nspd_into_profile` | building_extra.{building_type,year_built}, legal_extra.use_type_permitted | **gapfill** (никогда не перезаписывает) | `merge_profile(conn, cad, {"building_extra":{…},"legal_extra":{…}}, source="nspd", confidence=0.8, strategy="gapfill")` |
| `etl_checko` | legal_extra.owner_checko | **gapfill** (skip если есть) | `merge_profile(conn, cad, {"legal_extra":{"owner_checko":payload}}, source=<row source при наличии, иначе настроенный>, confidence, strategy="gapfill")` |
| `etl_exif` | extras.advantages[], extras.notes | **gapfill + append_keys** | `merge_profile(conn, cad, {"extras":{"advantages":[summary],"notes":joined}}, source="exif", confidence=0.7, append_keys={"extras":["advantages","notes"]})` |
| `etl_osv` | все 6 колонок (авторитетная база) | **priority** (рекоменд.) | `merge_profile(conn, cad, {col:val…}, source="osv", confidence, strategy="priority")` |

### Нюансы (требуют решения при рефакторе)
- **`etl_osv` сейчас делает wholesale-UPSERT** (перезаписывает ВСЕ колонки, в т.ч.
  обнуляет непереданные). Это **затирает ручной ввод `manual`**, если он был. Переход
  на `merge_profile(strategy="priority")` это чинит (osv<manual → не затирает manual,
  но перекрывает nspd/exif). **Решение заказчика:** оставить wholesale (osv = чистая
  база) или перейти на priority (безопаснее для manual). Рекомендуется priority.
- **`checko` не ROW-источник** (CHECK schema: osv|exif|manual|nspd|llm). Поэтому
  checko-обогащение НЕ меняет `object_etp_profile.source` (gapfill читает и сохраняет
  текущий source; при создании новой строки — настроенный source писателя).
- Каждый писатель **сохраняет свой report-объект** (`EnrichReport`/`OsvApplyReport`
  и т.п.): `merge_profile` возвращает `{fields_changed, overwrite, created, row_source}`,
  из которого репорт заполняется (поля для совместимости с тестами).

## Порядок рефактора (на машине с ETL-тестами)
1. Перевести `nspd_enricher` и `etl_checko` (чистый gapfill — наименьший риск).
2. `etl_exif` (gapfill+append_keys) — сверить идемпотентность advantages/notes.
3. `etl_osv` — после решения по wholesale vs priority.
4. Прогнать `test_etl_*`, `test_nspd_enricher`, `test_etl_checko` (нужен pymorphy3).

## Статусы
- ✅ Примитив `etp_merge` (стратегии + append_keys + `changed_keys` для репортов) —
  реализован, протестирован (12 тестов).
- ✅ **`nspd_enricher` → `merge_profile(gapfill, commit=False)`** — подтверждено
  прогоном `test_nspd_enricher` у заказчика: 40 passed (4 падения — Windows-only
  `:` в именах файлов, пред-существующие, не связаны с рефактором).
- ✅ **`etl_checko` → `merge_profile(gapfill, commit=False)`** + presence-guard
  (skip по факту owner_checko). Smoke: new/fill-over-manual/idempotent-skip.
- ✅ **`merge_profile(commit=False)`** — транзакцию/rollback (dry-run) контролирует
  CLI (исходные ETL не коммитили внутри записи).
- ✅ **`etl_exif` → `merge_profile(gapfill, append_keys={extras:[advantages,notes]},
  commit=False)`** — smoke: new advantages / preserve-existing / idempotent-skip /
  notes-union. Семантика EXIF (union без дублей) сохранена.
- ✅ **`etl_osv` → `merge_profile(strategy="priority", commit=False)`** (решение
  заказчика) — smoke: insert / update-over-nspd (source→osv, conf→1.0) / **osv НЕ
  затирает manual** (баг wholesale-перезаписи исправлен). Тесты osv совместимы.

## Итог
**Все 4 писателя ЭТП-слоя консолидированы на единую точку `etp_merge.merge_profile`.**
Дублированная read-merge-write логика убрана; приоритет/gap-fill/additive — в одном
месте, протестированном (24 теста etp_merge/lot/bundle). nspd/checko подтверждены
прогоном тестов заказчика; exif/osv — smoke (полные `test_etl_*` — на машине с pymorphy3).
