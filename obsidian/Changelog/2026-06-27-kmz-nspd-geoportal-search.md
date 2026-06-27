# 2026-06-27 — KMZ/NSPD: переход на geoportal-search (контур наконец парсится)

## Симптом
`kmz --nspd` ловил **0 feature**, хотя карта NSPD **показывала** контур после
клика по лупе («вывелся объект с контуром и описанием, но не спарсилось»).

## Диагноз (по сохранённой странице заказчика)
Страница = Vite module-federation SPA; сам map-бандл и XHR-ответ с геометрией в
«Save as» **не попали**. Но улика нашлась в логике v8: `NetworkCapture`
**пропускает любой URL c `/search/`** (правило «search = extent квартала» — из
эпохи ПКК). Современный NSPD отдаёт геометрию объекта именно эндпоинтом
`https://nspd.gov.ru/api/geoportal/v2/search/geoportal` (его и дёргает лупа) →
реальный ответ молча отбрасывался.

## Фикс — `geo_nspd_browser.py` переписан
- **Активный** session-aware запрос через `page.request.get` к geoportal-search
  (наследует cookies/Referer открытой карты → проходит анти-бот там, где голый
  urllib даёт 403). Варианты: `?query=КН` и `?thematicSearchId=1&query=КН`.
- Парс ответа терпим к обёрткам (`{data:{features}}` / FeatureCollection /
  Feature); КН берётся в т.ч. из `properties.options.cad_num`.
- Геометрия в EPSG:3857 → репроекция в WGS84 (inline, формула из v8).
- Доп. **разрешающий** слушатель ответов (НЕ режет `/search/geoportal`) копит
  feature карты → обнаружение ОКС в границах ЗУ (centroid-in-polygon) + fallback.
- Контракт `fetch_parcels` неизменен: `{cad:{polygon,buildings,captured}}`.

## CLI
- Диагностика переименована: «feature от geoportal», подсказка `--nspd-headful`.

## Тесты
- Новый `tests/test_geo_nspd_browser.py` (+7): extract/обёртки, репроекция
  3857→WGS84 (даёт Краснодарский край для 23:15), выбор ЗУ по точному КН,
  КН из вложенного `options`, обнаружение ОКС. **Итого geo: 24 passed.**
- Браузерный `_run` проверяется на машине заказчика (нужны playwright+chromium+сеть).

## Версия 2: закрытие модалей и ретрай
После 1-го тестирования (`геометрия по 1/3`) добавлена логика:
- `_close_modals(page)` — закрывает видимые диалоги (X, overlay, ESC).
- Увеличена задержка после page.goto (2.5s + close + 1s) вместо 1.5s.
- `_search_geoportal` повторяет запрос до 3 раз с задержками.

## Проверка на машине заказчика
```
python -m egrn_parser kmz --parcels 23:15:0000000:2267,23:15:0303000:1562,23:15:0303000:1130 \
  --db проект.sqlite --out objects.kmz --nspd --nspd-headful
```
Ждём: «геометрия по 3/3 ЗУ». Если <3 — прислать вывод логирования.

## Файлы
- `parser/egrn_parser/geo_nspd_browser.py` (переписан),
  `parser/egrn_parser/cli.py` (диагностика),
  `parser/tests/test_geo_nspd_browser.py` (новый).
