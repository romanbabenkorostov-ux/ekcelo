# C2 — дорожная карта после тестирования

> Что сделано (этап 0) и что дальше. Старт этапа 2 — **после** приёмки экономистом
> (см. `obsidian/UserGuide/db-testing-economist.md`). Версия: 2026-06-04.

## Этап 0 — фундамент C2 (СДЕЛАНО)
- [x] C2-схема §1–§12: `models.py` + `models_egrn.py`, миграции `0001..0003` (33 таблицы).
- [x] Сид `relation_types` (30 кодов, домены/категории, вкл. `corporate`).
- [x] Импорт Block-2 БД → C2 (ЕГРН-слой: объекты, права, субъекты, геометрия, цепочки).
- [x] Единый граф-эмиттер `relations → graph.json` (с `confidence`).
- [x] Инструкция экономисту + pytest-замки.

## Ворота: приёмка
Экономист прогоняет шаги из `db-testing-economist.md` на боевой БД парсера и
подтверждает: число `objects` совпало, есть `owns@1.0`, граф собирается. Только
после этого — этап 2.

---

## Этап 1 — закрыть импорт Block-2 (по итогам теста, мелкие правки)
- [ ] Доимпорт остатка Block-2: `company_groups` → `entities(business_asset)` + рёбра
      `GROUPS`; `business_units` → `entities(bu)`; `valuations` → факты стоимости;
      `object_events` → `assertions/evidences` (события жизненного цикла).
- [ ] Битемпоральность прав: `rights.valid_from/valid_until` (Block-2) → `relations.
      valid_from/valid_to` (сейчас пишем в `meta.since`, поднять в колонки).
- [ ] Обработка `stub`-объектов (упомянут, выписки нет) → `entities.meta.stub=true`.

## Этап 2 — классификатор документов (новое ядро)
- [ ] Стадия `parser/.../classify.py` + `core/pipeline.py: classify_folder(path)` по
      `DOC_CLASSIFIER_SPEC`. Декларативный реестр `contracts/db/doc_registry.yaml`.
- [ ] Маршрутизация фактов: документ → `doc_links` (target_table.target_field) +
      `assertions/evidences` с `source_type`+`weight`.
- [ ] Источники сверх ЕГРН (питают граф):
  - **ОСВ** → домен `accounting` (`ON_BALANCE_OF` 01.01, `LEASED_IN_BALANCE` 01.03/01.К);
  - **EXIF-фото** → `geometries(POINT)` + `DEPICTS` + разметка `object_etp_profile` (LLM);
  - **NSPD** → `geometries` контуры (weight 0.6);
  - **ЕГРЮЛ/ЕГРИП** → `subjects`/`subject_kpp`/`ip_status_periods` + `FOUNDER_OF/MANAGES`.
- [ ] Резолвер конкурирующих assertions (active = max confidence; ручной override асесора).

## Этап 3 — лот, снапшот, выгрузки
- [ ] `LotSnapshot`-генератор: заморозка состава при «Договор/Счёт».
- [ ] Композер `lot_to_kmz.py`: `LotSnapshot → подграф → KMZ` (SCHEMA_SPEC §11):
      роль-подмена третьих сторон (C6), значения связей + `confidence` в подписи рёбер,
      документы на дату, геометрия МСК-61 → 4326.
- [ ] УПД-XML из снапшота (правило `USN_VAT ⇒ статус 1`, контроль `xsd_version`).
- [ ] Сюрвей-преза из снапшота.

## Этап 4 — согласование контрактов и масштаб
- [ ] PR в C4 `viewmodel.schema.json`: `graphNode.kind += accessory, device, state_body,
      flow_node, demarcation_point, business_asset, lot, order`.
- [ ] Прогон миграций на **PostgreSQL** (сейчас проверено на SQLite; убедиться в `0003`
      `ALTER TYPE`, JSONB, Uuid native).
- [ ] Перенос канонической C2-схемы в `ekcelo` как источник истины + синк в `ekcelo-parser`.
- [ ] Технологический граф (этап ядра): `MOVED_TO/FEEDS/TRANSFORMS_TO`, `flow_events`,
      узлы-накопители (`current_level` из событий), точки разграничения из договоров снабжения.

---

## Зависимости / решения, ожидающие заказчика
- Гранулярность ЭТП-слоя §6 (JSON vs нормализованные таблицы) — `PARSER_VOCAB_MAP`/SCHEMA_SPEC §0.
- Битемпоральность прав: as-of vs valid-from/to (этап 1 поднимает в колонки).
- Где живёт каноническая C2 (рекомендация: `contracts/db/` в `ekcelo`).
