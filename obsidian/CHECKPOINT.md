# CHECKPOINT — 2026-06-08 (P0.3 sub-stages C1/C2/C3.1 done · zip-handoff)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox):** `backend/p0-bundle-storage-c3-1` (C3.1 поверх C2 поверх C1).
- **Подэтап:** P0.3 ViewModel + Storage — **C1 + C2 + C3.1** закрыты локально.
- **Тесты:** 268 passed в sandbox (191 baseline + 28 C1 + 24 C2 + 25 C3.1).
- **main на:** PR #104 (A+B Bundle importer).
- **PR C1:** открыт (#105 по сообщению пользователя), готов к merge.
- **Канал доставки:** zip-handoff. Архивы:
  - C1: доставлен ранее (`#105`).
  - C2: доставлен ранее (ждёт merge C1).
  - C3.1: готов к доставке (ждёт merge C2).

## Сделано

### C1 (см. `obsidian/Architecture/p0-viewmodel.md`)
- `backend/app/services/viewmodel.py` — Pydantic + `build_catalog` +
  `build_object_viewmodel`.
- `lot_orchestrator_web/main.py` — `+GET /catalog`, `+GET /objects/{cad}`,
  `+ekcelo_db` параметр, `+_require_ekcelo_db`.
- 28 тестов (18 + 10).

### C2
- Тот же `viewmodel.py` — +`build_lot_viewmodel`, `build_object_graph`,
  `LotNotFound`, `_OBJECT_TYPE_TO_NODE_KIND`.
- `main.py` — `+GET /lots/{lot_id}`, `+GET /objects/{cad}/graph`.
- 24 теста (16 + 8). Граф: `has_right`, `held_by`; узлы object=cad,
  right=`right:<id>`, beneficiary=`inn:<inn>`.

### C3.1 (см. `obsidian/Architecture/p0-bundle-storage.md`)
- ✨ `schema/migrations/0002_bundles.sql` — sidecar table.
- ✨ `backend/app/services/bundle_storage.py` — `compute_bundle_id`,
  `store_bundle`, `get_bundle`, `ensure_bundles_schema`.
- `main.py` — `+bundles_dir` параметр + расширение `POST /bundles/import`
  (возвращает `bundle_id`, кладёт KMZ) + `+GET /bundles/{bundle_id}/download`.
- 25 тестов (14 + 11). KMZ хранится на ФС `<bundles_dir>/<bundle_id>.kmz`.

## В процессе / не закончено

- **C3.2** — реверс-экспорт `fmt={zip,db,json}` (round-trip Bundle из БД).
  Требует генерации manifest.json + slicing db.sqlite по objects[] из manifest.
- **C3.3** — materialization `geo` (KMZ → objects.geo_*). Зависит от
  parser-team (KMZ-parser → DB pipeline ещё не написан).
- `ownership.graph` в `build_object_viewmodel` остаётся `None` — граф
  через отдельный endpoint.
- Push из sandbox в GitHub не работает — продолжаем zip-handoff.

## Следующий конкретный шаг

После merge C1 (#105):
1. Применить архив C2 (`backend/p0-viewmodel-c2`), открыть PR, прислать номер.

После merge C2:
2. Применить архив C3.1 (`backend/p0-bundle-storage-c3-1`), открыть PR.

После merge C3.1:
3. Старт **C3.2** (реверс-экспорт).

## Открытые PR

- ✅ #104 (A+B Bundle importer) — смержен.
- 🟡 #105 (C1 ViewModel) — открыт пользователем, ждёт merge.
- 🟡 Готов локально C2 (24 теста), zip доставлен — ждёт merge C1.
- 🟡 Готов локально C3.1 (25 тестов), zip готов — ждёт merge C2.

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Подэтап-снимки:
  - `obsidian/Architecture/p0-viewmodel.md` (C1+C2)
  - `obsidian/Architecture/p0-bundle-storage.md` (C3.1)
  - `obsidian/Architecture/p0-bundle-importer.md` (A+B)
- Спека: `docs/specs/SPEC_backend.md`
- Контракты:
  - `contracts/api/viewmodel.schema.json` + `openapi.yaml`
  - `contracts/bundle/bundle.schema.json`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
