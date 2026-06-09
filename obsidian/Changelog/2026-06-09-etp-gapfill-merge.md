# 2026-06-09 — ЭТП-слой §6: единый gap-fill merge (SPEC_parser item 5)

Консолидирован приоритет-aware merge в `object_etp_profile` (раньше — разрозненные
ETL-писатели etl_osv/etl_checko/etl_exif/nspd_enricher, каждый «заполняет пустое»
в свою колонку без единой приоритетной модели).

## Реализовано (`egrn_parser/etp_merge.py`)
- **`SOURCE_PRIORITY`**: `manual(100) > osv(90) > nspd(50) > exif(40) > llm(30)`
  (checko — field-level в legal_extra, не ROW-источник по CHECK схемы).
- **`merge_profile(conn, cad, incoming, source, confidence)`** — gap-fill merge:
  - источник с приоритетом **≥ текущего ROW** — может перезаписывать значения;
  - источник **ниже** — только заполняет пустоты (ручной ввод экономиста цел);
  - пустые входные значения игнорируются; глубокий merge по 6 JSON-колонкам
    (location_extra/building_extra/layout/legal_extra/risks/extras), вложенно;
  - ROW source/confidence = авторитетнейший из вкладчиков; идемпотентно.
- **`etp_layer_present(conn)`** — флаг наличия §6 для `manifest.etp_layer_present`
  (ADR-001: §6 при пересоздании БД из выписок не восстанавливается).

## Тесты (`tests/test_etp_merge.py`, +7)
- gap-fill без перезаписи (nspd не затирает manual, пустое поле заполняется);
- высший источник перезаписывает низший (manual > nspd);
- идемпотентность (повтор → 0 изменений);
- вложенный gap-fill (engineering.heating manual сохранён, water добавлен);
- пустой вход игнорируется; неизвестный source отклонён; etp_layer_present.
- 18 passed (с lot_assembler/bundle_manifest).

## Файлы
- `parser/egrn_parser/etp_merge.py` (новый)
- `parser/tests/test_etp_merge.py` (новый)
- `docs/specs/SPEC_parser.md` (item 5 ✅)

## Связь
`etp_layer_present` → `bundle_manifest.build_manifest(etp_layer_present=…)`.
Существующие ETL (osv/exif/checko/nspd) можно перевести на `merge_profile` как
единую точку записи — отдельным рефактором (по запросу).
