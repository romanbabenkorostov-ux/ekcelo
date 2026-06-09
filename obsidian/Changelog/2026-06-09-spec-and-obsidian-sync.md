# 2026-06-09 — Синхронизация SPEC + obsidian с фактическим состоянием

После подключения МКУ/ЕЗП к ingest и миграции 0005 — привёл документацию в
соответствие с кодом.

## SPEC_parser.md
- **§11 (ЗУ/ЕЗП/МКУ)**: отмечено сделанным — МКУ-контуры из геометрии
  (`split_geometry_contours` + `upsert_geometry_contours`, ЕЗП не понижается),
  ingest подключён (`land_ingest.py` + CLI `01c_contours_to_db.py`: sidecar →
  `land_contours`, текст выписки → ЕЗП). Сверка с офлайн-ядром NSPD-парсера v8.
- **§12 (агро-слой)**: миграция `0005_agro_layer.sql` отмечена написанной
  (agro_parcel/agro_crop_cycle/agro_event/agro_attribute_dict; ADR-006 §I — цикл
  sow→harvest, season_year=год уборки, план/факт+§F). Парсер техкарты — ждёт образец.

## obsidian/Architecture/parallel-parsers-map.md
- Добавлен раздел «Пайплайн земли: NSPD → sidecar → БД» с цепочкой
  `01_parsing_nspd_v8 → 01b_ingest_contours → 01c_contours_to_db` и мостом
  `land_ingest.py`.

## Согласованность ADR (уже сделано ранее)
- ADR-005 — актуален (контуры ЗУ/ЕЗП/МКУ).
- ADR-006 §I — DECIDED (agro_crop_cycle, season_year=год уборки, план/факт+§F).

## Файлы
- `docs/specs/SPEC_parser.md`
- `obsidian/Architecture/parallel-parsers-map.md`
