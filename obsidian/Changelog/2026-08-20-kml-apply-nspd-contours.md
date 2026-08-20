# 2026-08-20 — новый скрипт: заменить полигоны в KML на контуры НСПД

## Задача
Пользователь дал ранее в сессии KML (ручная разметка площадок "ОЛИМП" в
Yandex Map Constructor, 100 Placemark, 23 уникальных кадастровых номера в
`<description>`, полигоны — от руки, не точные) и спросил, как
воспользоваться парсером, чтобы заменить эти полигоны настоящими
контурами с НСПД.

## Что нашлось (существующий конвейер, парсер уже умел это — частично)
`obsidian/Decisions/2026-05-25-contour-sidecar-architecture.md`
описывает готовый 3-шаговый конвейер сбора контуров:
1. `parser/scripts/01_parsing_nspd_v8.py` — интерактивный Playwright-
   скрейпер НСПД (WFS → PKK → OL-state → screenshot+CV fallback).
   **Требует видимый браузер и доступ к nspd.gov.ru/pkk.rosreestr.ru —
   не выполняется в этой (headless, сетеизолированной) среде, только
   локально у пользователя.**
2. `01b_ingest_contours.py` — консолидирует вывод шага 1 в
   `_data/contours.json` (idempotent upgrade-merge по приоритету
   источника: wfs > pkk > network_capture > ol_state > screenshot_cv).
3. Дальше — но только для сборки KMZ ПОЛНОГО проекта с нуля из
   `structure.json` (`08_build_kmz_*.py`), НЕ для точечной замены
   полигонов в уже существующем произвольном KML.

Шага «взять готовый KML + contours.json → заменить именно те полигоны,
для которых нашёлся кадастровый номер» не было — этого и попросил
пользователь.

## Что сделано
`parser/scripts/kml_apply_nspd_contours.py` (новый) — четвёртый,
недостающий шаг: читает произвольный KML + `contours.json`, для каждого
Placemark с Polygon/MultiGeometry ищет кадастровый номер в
`<description>` тем же форматом, что ключи `contours.json`, и если для
него есть запись с пригодным источником (`wfs|pkk|ol_state|
network_capture|manual` — не `screenshot_cv` без геореференса, та же
граница, что ADR §6), заменяет геометрию на GeoJSON из НСПД. Placemark
без КН, без записи в реестре, или с непригодным источником — не трогает.
name/description/styleUrl не меняются. Одинаковый КН на нескольких
Placemark (ЕЗ — единое землепользование, тот же случай, что уже
задокументирован в VineInvent `sql/02_vineyard.sql`) — заменяются ВСЕ
совпадения.

## Как проверялось
`parser/tests/test_kml_apply_nspd_contours.py` — 8 unit-тестов (замена
при wfs, ЕЗ-дубликат КН, сохранение name/description/style, пропуск
отсутствующего в реестре КН, пропуск screenshot_cv-без-geojson, пропуск
Placemark без КН, Point-плейсмарки не трогаются, MultiPolygon). Плюс
реальный прогон на присланном пользователем KML (100 Placemark) с
синтетическим `contours.json` (2 записи, включая один screenshot_cv-
кейс без geojson) — корректно заменил оба вхождения `23:15:0000000:2267`
(ЕЗ, два Placemark), не тронул остальные 98, вывод — валидный XML.

## Осознанно НЕ сделано
Шаг 1 (`01_parsing_nspd_v8.py`) НЕ запускался в этой сессии — нужен
реальный браузер и доступ к nspd.gov.ru/pkk.rosreestr.ru, которых здесь
нет. Пользователю нужно прогнать его локально по 23 кадастровым номерам
из присланного KML, затем `01b_ingest_contours.py`, затем новый скрипт.

## Канал доставки
git push на `claude/ekcelofotomobile-folders-packages-4tryj0`.
