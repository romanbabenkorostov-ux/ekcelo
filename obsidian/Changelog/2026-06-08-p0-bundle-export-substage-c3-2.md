# 2026-06-08 — P0.3 Bundle reverse-export sub-stage C3.2

## Что сделал
Реверс-экспорт Bundle: `fmt={db,json,zip}` для `GET /bundles/{id}/download`
(поверх kmz/manifest из C3.1). Round-trip контракт зелёный.

## Файлы
- ✨ `backend/app/services/bundle_export.py` — `export_bundle_db`,
  `export_bundle_json`, `export_bundle_zip`, `BundleExportError`.
- ✨ `backend/tests/test_bundle_export.py` — 12 service-тестов (вкл. round-trip).
- ✏️ `lot_orchestrator_web/main.py` — download-эндпоинт: ветки db/json/zip
  (раньше 501), BundleExportError → 409.
- ✨ `lot_orchestrator_web/tests/test_bundle_export_endpoint.py` — 6 тестов.
- ✏️ `lot_orchestrator_web/tests/test_bundle_storage_endpoint.py` — обновлён
  тест fmt=db (501 → 200).
- ✨ `obsidian/Architecture/p0-bundle-export.md` — снимок C3.2.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — C3.2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 18 новых (12 service + 6 endpoint); +1 обновлён.
- Полный suite в sandbox: **286 passed** (268 + 18).
- Регрессий нет.

## Решения

- **Round-trip = идемпотентный импорт, не байт-идентичность.** sqlite-срез
  физически отличается от исходного db.sqlite (rowid, страницы). Поэтому
  манифест экспорта перегенерируется со свежими sha256/bytes, а round-trip
  проверяется через `import → is_noop`, а не через сравнение файлов. Это
  соответствует SPEC §P0.3 («идемпотентный Bundle, round-trip тест»).
- **Срез по objects[] из манифеста, не вся БД.** Bundle описывает конкретные
  объекты — экспорт берёт только их + связанные строки. Чужие правообладатели
  (ИНН, который встречается только у объектов вне bundle) НЕ попадают в
  entity_registry среза. Это сохраняет «узость» Bundle.
- **BundleExportError → 409 Conflict.** Если объект из манифеста исчез из БД
  (например, его удалили после импорта) — это конфликт состояния, не 404
  (сам bundle найден) и не 500 (ожидаемая ситуация). 409 даёт фронту понять:
  bundle есть, но БД разошлась.
- **fmt=db отдаём как `application/vnd.sqlite3` потоком**, не через временный
  файл на диске эндпоинта — собираем во временной директории, читаем bytes,
  отдаём Response. Чисто, без утечки tmp.
- **kmz в zip только если сохранён.** Если C3.1 импортировал bundle без KMZ
  (или файл потерян) — zip соберётся из manifest+db без project.kmz. Манифест
  не включит KMZ в files[]. Импорт такого zip тоже даст no-op.
- **lots/lot_items в срез пока не включены.** Экспорт оперирует objects[].
  Для kind=lot bundle реэкспортируются объекты-члены; запись самого лота —
  кандидат на расширение в C3.3+, если появится потребность.

## Канал доставки
- Sandbox-proxy блокирует git push — zip-handoff.
- Архив C3.2 доставляется ПОСЛЕ merge C3.1 (зависит от bundle_storage.py +
  download-эндпоинта).

## Следующий шаг
1. Дождаться merge PR C3.1.
2. Применить архив C3.2 на свежей main, открыть PR.
3. **C3.3** (materialization geo) — зависит от parser-team; либо переход к
   следующему P0-треку по решению владельца.
