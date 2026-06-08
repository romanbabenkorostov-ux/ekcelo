# CHECKPOINT — 2026-06-08 (P0.3 sub-stages C1 + C2 done · zip-handoff)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox C1):** `backend/p0-viewmodel` (1 коммит C1, доставлено).
- **Ветка (sandbox C2):** `backend/p0-viewmodel-c2` (планируется поверх main
  после merge C1; локально в sandbox C2 уже накодено).
- **Подэтап:** P0.3 ViewModel — **sub-stages C1 + C2** закрыты локально.
- **Тесты:** 243 passed в sandbox (191 baseline + 28 C1 + 24 C2).
- **main на:** PR #104 смержен (P0.2 A+B Bundle importer + cleanup gitignore).
- **PR C1:** открыт пользователем (после фикса misplacing commit в main).
- **Канал доставки:** zip-handoff. Архивы:
  - C1: `ekcelo-p0-viewmodel-substage-C1-2026-06-08.zip` (доставлен).
  - C2: `ekcelo-p0-viewmodel-substage-C2-2026-06-08.zip` (готов к доставке).

## Сделано на C1 (см. `obsidian/Architecture/p0-viewmodel.md`)

- `backend/app/services/viewmodel.py` — Pydantic ViewModel/CatalogCard +
  `build_catalog`, `build_object_viewmodel`.
- `lot_orchestrator_web/main.py` — `+GET /catalog`, `+GET /objects/{cad}`,
  `+ekcelo_db` параметр в `create_app` (env `EKCELO_DB`), `+_require_ekcelo_db`.
- 28 тестов (18 service + 10 endpoint).

## Сделано на C2

- Тот же `backend/app/services/viewmodel.py` — +`LotNotFound`,
  `build_lot_viewmodel`, `build_object_graph`, `_OBJECT_TYPE_TO_NODE_KIND`.
- `lot_orchestrator_web/main.py` — `+GET /lots/{lot_id}`,
  `+GET /objects/{cad}/graph`.
- 24 теста (16 service + 8 endpoint).
- Графовый узел id-формат: object=cad, right=`right:<id>`,
  beneficiary=`inn:<inn>`. Edge kinds: `has_right`, `held_by`.

## В процессе / не закончено

- **Sub-stage C3** — KMZ-storage (`bundles/<id>.kmz`) + `GET /bundles/{id}/download`
  + материализация `geo` геометрии. Не начат.
- `ownership.graph` в `build_object_viewmodel` остаётся `None` — граф
  доступен через отдельный endpoint `/objects/{cad}/graph` (в C3 может
  агрегироваться обратно через `?include=graph`).
- Push из sandbox в GitHub не работает — продолжаем через zip-handoff.

## Следующий конкретный шаг

После merge C1 на стороне пользователя:

1. Распаковать архив C2 на свежей main.
2. Создать ветку `backend/p0-viewmodel-c2`, скопировать `files/`, commit, push.
3. Открыть PR + сообщить номер.
4. Старт C3.

## Открытые PR

- ✅ #104 (sub-stages A+B Bundle importer) — смержен.
- 🟡 PR C1 (sub-stage C1) — открыт пользователем, ожидает merge.
- 🟡 Локально готово C2 (24 теста), zip готов, push после merge C1.

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Подэтап-снимок (C1+C2): `obsidian/Architecture/p0-viewmodel.md`
- Предыдущий снимок (A+B): `obsidian/Architecture/p0-bundle-importer.md`
- Спека: `docs/specs/SPEC_backend.md`
- Контракт ViewModel: `contracts/api/viewmodel.schema.json` + `openapi.yaml`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
