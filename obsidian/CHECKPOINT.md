# CHECKPOINT — 2026-06-08 (P0.3 sub-stage C1 done · zip-handoff)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox):** `backend/p0-viewmodel` (1 коммит: sub-stage C1)
- **Подэтап:** P0.3 ViewModel — **sub-stage C1** закрыт (catalog + object-VM).
- **Тесты:** 219 passed в sandbox (baseline 191 + 28 новых C1).
- **main на:** PR #104 смержен (P0.2 A+B Bundle importer + cleanup gitignore).
- **Канал доставки:** zip-handoff (sandbox proxy не пропускает push в GitHub).
  Архив: `ekcelo-p0-viewmodel-substage-C1-2026-06-08.zip`. См. `HANDOFF.md`
  внутри + `obsidian/UserGuide/local-handoff-workflow.md`.

## Сделано (на этой ветке)

### Sub-stage C1 — ViewModel ядро + 2 эндпоинта
- `backend/app/services/viewmodel.py` (~340 LOC): Pydantic-зеркало
  `viewmodel.schema.json` (Physical/Ownership/Geo/Temporal + CatalogCard),
  `build_catalog(db, q?, kind?)`, `build_object_viewmodel(db, cad, as_of?)`.
  Безопасно работает на БД без lots/extracts/etp таблиц.
- `backend/tests/test_viewmodel.py` — 18 service-тестов.
- `lot_orchestrator_web/main.py` — `GET /catalog`, `GET /objects/{cad}`,
  helper `_require_ekcelo_db`, новый параметр `ekcelo_db=` в `create_app`
  (читается из env `EKCELO_DB` если не передан; 503 если не сконфигурирован).
- `lot_orchestrator_web/tests/test_viewmodel_endpoint.py` — 10 endpoint-тестов.

### Документация
- `obsidian/Architecture/p0-viewmodel.md` — снимок C1.
- `obsidian/Architecture/roadmap-2026-06.md` — пункт C1 ✅.
- `obsidian/Changelog/2026-06-08-p0-viewmodel-substage-c1.md`.

## В процессе / не закончено

- **Sub-stage C2** — `GET /lots/{lot_id}` + `GET /objects/{cad}/graph`. Не начат.
- **Sub-stage C3** — KMZ-storage + `GET /bundles/{id}/download?fmt=`. Не начат.
- `geo` в ViewModel — stub (геометрия будет материализована в C3 после
  KMZ-парсера → `objects.geo_*` колонок или sidecar-таблицы).
- Push из sandbox в GitHub не работает — продолжаем через zip-handoff.

## Следующий конкретный шаг

После применения архива C1 на стороне пользователя:

1. Распаковать `ekcelo-p0-viewmodel-substage-C1-2026-06-08.zip` в
   `C:\Users\Соня\Downloads\ekcelo-handoff-C1\`.
2. Скопировать содержимое `files/` в `E:\Code\ekcelo\ftontback2026-01-02\`.
3. По инструкции `HANDOFF.md`: создать ветку `backend/p0-viewmodel`, коммит,
   push, открыть PR.
4. Сообщить мне номер PR. Я начну sub-stage C2.

## Открытые PR

- ✅ #104 (sub-stages A+B) — смержен.
- 🟡 Готов локально: sub-stage C1 (28 тестов). PR ещё не открыт (zip-handoff).

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Подэтап-снимок (C1): `obsidian/Architecture/p0-viewmodel.md`
- Предыдущий снимок (A+B): `obsidian/Architecture/p0-bundle-importer.md`
- Спека: `docs/specs/SPEC_backend.md`
- Контракт ViewModel: `contracts/api/viewmodel.schema.json` + `openapi.yaml`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
