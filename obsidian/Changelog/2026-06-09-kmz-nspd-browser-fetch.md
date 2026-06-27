# 2026-06-09 — KMZ: геометрия из NSPD через БРАУЗЕР (анти-бот) + диагностика

## Проблема (по прогону заказчика)
`kmz --nspd` дал «с границей: 0» — лёгкий HTTP-путь (urllib) **блокируется анти-ботом
NSPD/ПКК**, а ошибки молча глушились. Рабочий v8-парсер ходит в NSPD **через
Playwright** (браузерная сессия с куками) именно поэтому.

## Решение — `geo_nspd_browser.py` (надёжный путь)
- `fetch_parcels(cads, discover=True)` — через Playwright: открывает карту NSPD
  (сессия/анти-бот), геометрию ЗУ берёт **проверенными функциями v8**
  (`_fetch_geom_via_wfs` → `_fetch_geom_via_pkk`), ОКС в границах ЗУ — WFS BBOX через
  `page.request` (session-aware) + фильтр centroid-in-polygon.
- Возвращает `{cad: {polygon, buildings[]}}`. Нет playwright/сети → понятная ошибка.
- `geo_nspd.wfs_bbox_url`/`features_in_polygon` вынесены и переиспользуются (urllib и браузер).

## CLI
- `kmz --nspd` теперь = **браузерный путь** (Playwright, обходит анти-бот) — умолчание
  для NSPD. Печатает, сколько ЗУ/ОКС получено; при недоступности — честно сообщает и
  предлагает `--nspd-http`/предзагрузку.
- `kmz --nspd-http` — прежний лёгкий HTTP (urllib), оставлен как запасной.
Интеграция: браузер даёт границу ЗУ + ОКС (источник 2), остальное добирается из БД
(источник 1) и `--building-cads` (источник 3).

## Тесты
- `test_geo_nspd.py` (+2): `wfs_bbox_url`, `features_in_polygon`. **17 passed** (geo).
- Браузерный путь — **проверяется на машине заказчика** (нужен playwright + chromium +
  сеть; в среде закрыто).

## Ответ на вопрос «должен ли парсить сайт NSPD»
Да — и теперь парсит **через браузер** (как v8). Лёгкий HTTP оставлен флагом
`--nspd-http` (часто блокируется). Реальный прогон:
`python -m egrn_parser kmz --parcels … --db проект.sqlite --out objects.kmz --nspd`
(один раз: `pip install playwright; playwright install chromium`).

## Файлы
- `parser/egrn_parser/geo_nspd_browser.py` (новый), `geo_nspd.py` (helpers),
  `cli.py` (kmz --nspd браузер / --nspd-http), `tests/test_geo_nspd.py`
