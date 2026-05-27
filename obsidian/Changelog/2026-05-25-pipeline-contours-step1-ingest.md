# 2026-05-25 — pipeline-contours Step 1: sidecar `_data/contours.json` + `01b_ingest_contours.py`

**Цель:** идемпотентно обогащать объекты недвижимости контурами из `info["Контур"]` (v8 NSPD-парсер) и сделать sidecar source-of-truth для downstream-шагов (052_make_structure, 03_enrich, 04_nspd_graph, 08_build_kmz).

## Что сделано

1. **ADR** `obsidian/Decisions/2026-05-25-contour-sidecar-architecture.md` — спецификация:
   - Schema `_data/contours.json` v1.0
   - Priority-based upgrade-merge: `manual > wfs > pkk > network_capture > ol_state > screenshot_cv`
   - Reference-only summary в structure/enriched (без дублирования geojson)
   - Cytoscape simplify ≤32 точек для node-полигонов
   - KMZ Polygon для WGS84-источников + Point+ExtendedData для screenshot_cv
   - Pipeline-roadmap (Steps 1-6)

2. **`parser/scripts/01b_ingest_contours.py`** (новый):
   - Сканирует session_export, snapshot, per-object файлы v8
   - Идемпотентный merge в `_data/contours.json`
   - CLI: `--project DIR`, `--sources GLOB...`, `--dry-run`, `--reset`
   - Спец-токен `__per_object__` для строгой фильтрации через `PER_OBJECT_NAME_RE`
   - Byte-level идемпотентность: `ingested_at` обновляется только при реальном изменении объектов

3. **`parser/tests/test_ingest_contours.py`** — 28 тестов (всего 58/58 ✓):
   - Нормализация КН (canonical, mask→colons, garbage rejection)
   - Priority/alg_version semantics
   - Парсинг session_export / snapshot / per-object форматов
   - End-to-end через CLI: idempotent, upgrade, no-downgrade, reset, dry-run, missing data dir
   - Регрессионные на 6 fix'ов из code-review (см. ниже)

## Code-review (skill `simplify`) — 6 фиксов перед коммитом

1. L288: `f`-prefix в dry-run print.
2. L138: per-object файлы `{<cn>: info}` **полностью игнорировались** snapshot-веткой; добавлена branch с детектом КН на top-level. **Самый критичный fix** — без него весь `_data/nspd_cache/*.json` оставался незаingestнутым.
3. L208: размытый glob `*_*_*_*.json` заменён на spec-token `__per_object__` с строгой фильтрацией через `PER_OBJECT_NAME_RE`.
4. L158: `setdefault("schema_version")` навсегда замораживал старую версию — миграции не работали. Заменено на явный compare-and-upgrade.
5. L195: dry-run не обновлял in-memory sink → последующие файлы видели stale `existing=None` и врали в upgrade-reports. Симуляция теперь полная, пропуск write только в `main()`.
6. L266: top-level `ingested_at` обновлялся всегда → байты sidecar менялись без причины (нарушение ADR §7). Теперь — только при реальном изменении objects.

## Следующий шаг (Step 2)

`07_init_project_v2.1` — добавить `_data/contours.json` в `DIRS`-инициализацию (пустой скелет) + обновить docstring. Step 3-6 — версионирование downstream (052_v2_3, 03_v18, 04_v15, 08_v2_3).

## Файлы

- `obsidian/Decisions/2026-05-25-contour-sidecar-architecture.md` (новый, ADR)
- `obsidian/Changelog/2026-05-25-pipeline-contours-step1-ingest.md` (этот файл)
- `parser/scripts/01b_ingest_contours.py` (новый, +260 строк)
- `parser/tests/test_ingest_contours.py` (новый, +330 строк, 28 тестов)

## Verify

```bash
python3 -m pytest parser/tests/test_ingest_contours.py parser/tests/test_nspd_contour_v8.py
# → 58 passed
```
