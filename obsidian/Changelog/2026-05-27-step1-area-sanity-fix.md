# 2026-05-27 — Step 1 fix: sanity-check площади в `01b_ingest_contours.py`

## Контекст

В Step 2 changelog (2026-05-27-step2-surveycontract-infra.md §«Следующие
шаги», п.3) была зафиксирована открытая задача: **«Багфикс: площадь
`network_capture` в `01b_ingest_contours.py`»**. Закрываем.

## Симптом

`01b_ingest_contours.py` слепо ингестит payload из `info["Контур"]`
любого `session_export_*.json` / `snapshot_*.json` / `<cn>.json`.
v8-парсер делает `_payload_area_sane` **только при extract** — но
01b при ingest этого не повторяет. Поэтому:

- Старые session_export'ы (v8.0…v8.3, до появления sanity-check) тащат
  мусор в sidecar.
- `network_capture` особенно хрупок: `NetworkCapture.find_by_cad`
  делает substring-match по properties и в редких случаях возвращает
  extent квартала (площадь ~1.4e15 м²) или геометрию соседнего КН
  (площадь off-by-100x от заявленной).
- Priority alone (network_capture=600) не отфильтровывает такие
  payload'ы — `_should_upgrade` смотрит только на источник + версию.

## Фикс

`parser/scripts/01b_ingest_contours.py`:

1. Константы `MAX_REASONABLE_AREA_SQM=1e10`, `MAX_AREA_RATIO=100.0`,
   `MIN_AREA_RATIO=0.01` — зеркалят v8.
2. Функция `_payload_area_sane(payload) -> (ok, reason)` — defense-
   in-depth gate.
3. `ingest_one` вызывает sanity-check **перед** `_should_upgrade` →
   при провале инкрементит `stats["skipped_insane_area"]` и пропускает
   запись. Гарантия: insane payload **не** затирает существующий
   хороший контур, даже если priority выше.
4. Итоговый отчёт печатает количество и первые 10 пропусков
   (`✗ <cn> [<src>]: <reason>`).

## Тесты

`parser/tests/test_ingest_contours.py` — добавлено 7 регрессионных:

- `test_payload_area_sane_accepts_normal`
- `test_payload_area_sane_rejects_giant_area` (1.4e15 м²)
- `test_payload_area_sane_rejects_ratio_too_high` (100×)
- `test_payload_area_sane_rejects_ratio_too_low` (0.005×)
- `test_payload_area_sane_no_parsed_only_giant_check` (parsed=None)
- `test_e2e_insane_network_capture_skipped`
- `test_e2e_insane_does_not_overwrite_good` (главный инвариант)

Итого: 35/35 ✓ (было 28).

## Файлы

- `parser/scripts/01b_ingest_contours.py` — обновлён
- `parser/tests/test_ingest_contours.py` — обновлён
- `obsidian/Changelog/2026-05-27-step1-area-sanity-fix.md` — этот файл

## Verify

```bash
python3 -m pytest parser/tests/test_ingest_contours.py -v
# → 35 passed
```

## Что НЕ тронуто

- ADR `obsidian/Decisions/2026-05-25-contour-sidecar-architecture.md`
  — schema не изменилась, добавился только gate.
- `parser/scripts/01_parsing_nspd_v8.py` — extract-time sanity-check
  не меняется (оставляем оба слоя для безопасности legacy/новых
  session_export'ов).
- Downstream Steps 2-6 (07_init_project, 052, 03, 04, 08) — не
  затронуты.
