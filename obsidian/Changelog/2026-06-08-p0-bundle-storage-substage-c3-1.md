# 2026-06-08 — P0.3 Bundle storage sub-stage C3.1

## Что сделал
Sidecar-хранилище Bundle'ов + расширение import-эндпоинта + новый
download-эндпоинт (KMZ + manifest).

## Файлы
- ✨ `schema/migrations/0002_bundles.sql` — DDL `bundles` sidecar-таблицы.
- ✨ `backend/app/services/bundle_storage.py` — `compute_bundle_id`,
  `ensure_bundles_schema`, `store_bundle`, `get_bundle`, `BundleRecord`.
- ✨ `backend/tests/test_bundle_storage.py` — 14 service-тестов.
- ✏️ `lot_orchestrator_web/main.py` — `+bundles_dir` параметр в `create_app`
  (env `EKCELO_BUNDLES_DIR`), расширение `POST /bundles/import` (возвращает
  `bundle_id` + кладёт KMZ), `+GET /bundles/{bundle_id}/download?fmt=`.
- ✨ `lot_orchestrator_web/tests/test_bundle_storage_endpoint.py` — 11 тестов.
- ✨ `obsidian/Architecture/p0-bundle-storage.md` — снимок C3.1.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — C3.1 ✅, C3.2 план, C3.3 план.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 25 новых (14 service + 11 endpoint).
- Полный suite в sandbox: **268 passed** (243 + 25).
- Регрессий нет.

## Решения

- **bundle_id формат**: sha256 hex от каноничного `manifest.model_dump_json(
  exclude_none=True)`. Стабилен → идемпотентность повторного импорта.
  Альтернативу (UUID в манифесте от парсера) не выбрал — это потребовало бы
  расширения C3-контракта; sha256 покрывает идемпотентность даром.
- **Sidecar отдельно от bundle.py**: импортёр БД (`bundle.py`) остаётся
  чистым — мутирует только §1..§6/§ЭТП. Storage — отдельный модуль,
  оркеструется на уровне endpoint. ADR-001 §6 не нарушен.
- **KMZ на ФС, не в SQLite BLOB**: большие Bundle'ы могут содержать KMZ
  на десятки МБ — BLOB в sqlite даст медленное чтение и раздутый файл.
  ФС-хранилище простое и совместимо с будущей миграцией на S3 (C4).
- **`bundles_dir` опциональный**: если env/factory не задаёт — `POST
  /bundles/import` всё равно успешно импортирует, но `bundle_id=null` в
  payload, KMZ не сохраняется. Это позволяет deploy'нуть C3.1 без выделения
  диска и включать storage позже. Download в этом случае → 503.
- **Миграция 0002 запускается лениво** через `ensure_bundles_schema` при
  первом обращении к storage (как 0001 в `bundle.py`). Не требует
  отдельной шагалки.
- **fmt=db/json/zip → 501 (не 422/404)**: фронт сможет различить «не
  поддерживается ВООБЩЕ» (422) и «пока не реализовано» (501) и подстроиться.
- **Default fmt=kmz**: соответствует основному use-case (фронт показывает
  ссылку «Открыть в Google Earth»).

## Канал доставки
- Sandbox-proxy блокирует git push — продолжаем zip-handoff.
- Архив C3.1 будет доставлен после подтверждения, что PR C2 смержен.

## Следующий шаг
1. Дождаться merge PR C2.
2. Применить архив C3.1 на свежей main, открыть PR.
3. Старт **C3.2** — реверс-экспорт `fmt={zip,db,json}` (round-trip Bundle).
