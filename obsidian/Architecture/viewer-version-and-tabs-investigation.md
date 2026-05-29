# Investigation: viewer на GitHub Pages показывает v2.10, нет вкладки «Метки»

> Дата: 2026-05-28. По репорту пользователя:
> `https://romanbabenkorostov-ux.github.io/ekcelo/` показывает `v2.10`,
> ожидается `v2.11+`. Вкладка «Метки» в sidebar якобы отсутствует.

## TL;DR (root cause)

1. **Title не bump'ался** — `<title>EkceloFoto v2.10.0</title>` оставался статичным с момента релокации viewer (`55aca1a S3.viewer: relocate viewer unit to viewer/`), несмотря на мерж CONTRACT_KMZ 2.11.0 (PR #16) и 2.12.0 (PR #31). Версия в tab браузера читалась как «v2.10», создавая впечатление, что viewer вообще не обновлялся.
2. **Вкладка «Метки» в коде ЕСТЬ** — `viewer/index.html:1265`:
   ```html
   <button class="sb-tab" data-tab="marks"
           onclick="switchSidebarTab('marks')">🏷 Метки</button>
   ```
   Если пользователь её не видит на GitHub Pages — это **кэш браузера** (старый HTML до S5 PR-C `90a0799`, когда вкладка была добавлена).
3. **Service Worker не виноват** — `viewer/sw.js` кэширует только запросы к `nspd.gov.ru` (см. `CACHE_HOST`), а не сам viewer HTML/JS.

## Что фиксится

| Файл | Было | Стало |
|---|---|---|
| `viewer/index.html` | `<title>EkceloFoto v2.10.0</title>` | `<title>EkceloFoto v2.12.0</title>` |
| `viewer/sw.js` | `// sw.js v2.10.0` | `// sw.js v2.12.0` |

Выбран **2.12.0** — соответствует текущему `CONTRACT_KMZ.md` (PR #31, merged). Title теперь честно отражает версию контракта, который понимает viewer.

## Что не фиксится (cache-invalidation)

Браузерный кэш — клиентский, мы не можем его очистить за пользователя. Минимально полезные варианты:

- **Пользователю:** `Ctrl+F5` (hard reload). На Win10: `Ctrl + Shift + R`. После этого title должен сразу показать новую версию.
- **Альтернатива:** добавить cache-busting query string в `<link>`/`<script>` теги при следующем bump'е. Сейчас inline-JS, проблема ограниченна `index.html`.

## Текущая структура sidebar tabs

`viewer/index.html:1262-1266`:
```html
<nav id="sidebar-tabs">
  <button class="sb-tab active" data-tab="photos"
          onclick="switchSidebarTab('photos')">📸 Фото</button>
  <button class="sb-tab" data-tab="marks"
          onclick="switchSidebarTab('marks')">🏷 Метки</button>
  <button class="sb-tab" data-tab="graph" id="sb-tab-graph"
          onclick="switchSidebarTab('graph')" style="display:none">🕸 Граф</button>
</nav>
```

- 📸 Фото — всегда видна, активна по умолчанию.
- 🏷 Метки — всегда видна.
- 🕸 Граф — скрыта (`style="display:none"`), показывается через JS при наличии `graph.html` в KMZ-проекте (S5+ CONTRACT_KMZ 2.11.0).

## Версия контрактов в коде viewer

`viewer/index.html` сейчас полностью поддерживает:
- `CONTRACT_KMZ.md` 2.11.0 — мост маркер↔узел графа (`graph_node_id`, PR #16).
- `CONTRACT_KMZ.md` 2.12.0 — `<Data extract_date>`, sidecar `_data/documents.json`, формула `doc::<doc_id>` (PR #31).
- `EXIF_USERCOMMENT_SCHEMA.md` v1.1 — `doc_id`-resolving lightbox (PR #32).
- Phase 1 ЭТП-профиль read-only (PR #56, post-Stage 5/6 поля в PR #71).
- Stage 5/6 поля `building_type`/`year_built`/`use_type_permitted` (PR #71).

Title `v2.12.0` точно отражает максимально совместимую wire-формат версию.

## Связи
- `viewer/index.html` — основной артефакт.
- `viewer/sw.js` — version-header sync.
- `docs/CONTRACT_KMZ.md` — текущая 2.12.0.
- `obsidian/Architecture/etp-exporter.md` — отдельная ЭТП-плоскость.
