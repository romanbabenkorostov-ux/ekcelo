# 2026-06-09 — KMZ/NSPD: переход на NetworkCapture (WFS даёт 403)

## Диагностика заказчика
`kmz --nspd` через браузер → WFS-эндпоинт NSPD отдаёт **403** (16/16 комбинаций),
геометрия 0/3. Но карта NSPD **показывает контур** (URL с `active_layers=36048&
selectedCard=…`). Вывод: NSPD сменил API — WFS закрыт, карта грузит геометрию
другим (текущим) эндпоинтом.

## Решение — NetworkCapture (как PRIMARY в v8)
`geo_nspd_browser` переписан: вместо WFS — **пассивный перехват** geometry из
сетевых ответов карты (`v8.NetworkCapture`). На каждый КН:
- `goto map?query=КН&active_layers={ЗУ+ОКС}` → карта сама грузит контур(ы);
- poll `capture.find_by_cad(cad)` (точное>substring) до timeout → геометрия ЗУ;
- `_maybe_reproject_to_wgs84` (3857→WGS84);
- ОКС в границах ЗУ — из перехваченных feature, фильтр centroid-in-polygon.
Переиспользованы проверенные `NetworkCapture`/`find_by_cad`/`_maybe_reproject` из v8.

## CLI
- `kmz --nspd` — браузер + NetworkCapture (умолч.). Диагностика: сколько ЗУ/ОКС/
  перехвачено feature; при 0 — подсказка `--nspd-headful`.
- `--nspd-headful` — **видимый браузер** (анти-бот NSPD часто требует headful).
- `--nspd-http` — лёгкий urllib (403, запасной).

## Статус
- Тесты geo (офлайн-ядро) → 17 passed; cli импортируется.
- Браузерный путь **проверяется на машине заказчика** (нужны playwright+chromium+сеть;
  в среде закрыто). Если `--nspd` (headless) даст 0 — пробовать `--nspd-headful`.
  Если и так пусто — прислать вывод (captured feature count + последние URL карты),
  доработаю фильтр/слои/триггер карточки.

## Файлы
- `parser/egrn_parser/geo_nspd_browser.py` (NetworkCapture), `cli.py` (--nspd-headful)
