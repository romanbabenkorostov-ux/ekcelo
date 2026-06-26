# 2026-06-09 — Консолидация ETL шаги 3-4: etl_exif + etl_osv → merge_profile (ЗАВЕРШЕНО)

Все 4 писателя ЭТП-слоя §6 теперь пишут через единую точку `etp_merge.merge_profile`.

## Подтверждение шага 2 (checko)
`test_etl_checko` у заказчика: **8 passed**. (4 падения в общем прогоне — те же
Windows-only `:`-имена в nspd directory/CLI-тестах, не связаны с рефактором.)

## Шаг 3 — `etl_exif._apply_exif_to_profile` → merge_profile
- `strategy="gapfill"` + `append_keys={"extras": ["advantages", "notes"]}` —
  аддитивное объединение без дублей (точная семантика EXIF: advantages-список,
  notes joined «; »). `commit=False`.
- report.extras_filled/profile_created из `changed_keys`/`created`;
  `photo_summary_and_notes_already_present` при отсутствии изменений.
- **Smoke (4):** new advantages / preserve-existing-advantages / idempotent-skip /
  notes-union. Семантика сохранена.

## Шаг 4 — `etl_osv._apply_profile` → merge_profile (priority, решение заказчика)
- `strategy="priority"`, `commit=False`. Убрана wholesale-перезапись всех колонок.
- **Smoke (3):** insert (source=osv, conf=1.0) / update-over-nspd (source→osv,
  conf→1.0, поле перекрыто) / **osv НЕ затирает manual** (priority: osv<manual) —
  исправлен баг старого wholesale-UPSERT (затирал ручной ввод).
- Тесты osv (`test_apply_inserts_profile`/`test_apply_updates_existing_profile`)
  совместимы (проверено по асертам).

## Итог консолидации
| Писатель | Стратегия | Статус |
|---|---|---|
| nspd_enricher | gapfill | ✅ (test_nspd_enricher 40 passed у заказчика) |
| etl_checko | gapfill + presence-guard | ✅ (test_etl_checko 8 passed) |
| etl_exif | gapfill + append_keys | ✅ (smoke) |
| etl_osv | priority | ✅ (smoke; + manual защищён) |

Дублированная read-merge-write логика убрана из 4 модулей; приоритет/gap-fill/
additive — в одном протестированном месте (`etp_merge`, 24 теста с lot/bundle).

## Файлы
- `parser/exporters/etp/etl_exif.py` (рефактор + append_keys)
- `parser/exporters/etp/etl_osv.py` (рефактор + priority)
- `obsidian/Architecture/etp-merge-consolidation.md` (итог)

## Проверка на машине заказчика (pymorphy3)
`cd parser; pytest tests/test_etl_exif.py tests/test_etl_osv.py -q`
