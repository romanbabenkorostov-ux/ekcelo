# 2026-05-25 — viewer/multi-kmz-timeline-phase1 (B2)

**Что:** реализована **Phase 1 multi-extract dropdown UI** для viewer'а. При загрузке ≥2 KMZ одного проекта появляется select «текущая дата T» в шапке; пользователь переключается между snapshot'ами, на карте виден только выбранный, граф iframe srcdoc обновляется на graph.html выбранного KMZ.

**Триггер активации:** PR #37 (parser/dev/multi_extract_sample/) — синтетический batch из 3 KMZ за `2026-01-15`/`2026-04-15`/`2026-08-01` с `<Data extract_date>` + `_data/documents.json` (включая overlay `nr_demo01` со снятием ареста).

**Контракт:** не расширяется (только использование уже-зафиксированных в 2.12.0 полей). §3 UI/UX, viewer-домен, без shared-ratification. Договорено CORRESPONDENCE/014 §A / 016 §5 / 019 §3 / 022.

**Сделано:**

1. **`parseKML` — capture `<Document><ExtendedData>` direct-child `<Data>`** в `parsedData.docExtData` (~13 строк). Ранее парсилось только placemark-level ExtendedData; document-level extract_date пропадал.

2. **Cascade `extract_date` resolver** в `loadKMZFromFile` (контракт 2.12.0 §5):
   - `<Document><ExtendedData><Data name="extract_date">` (приоритет 1, true source-of-truth).
   - filename regex `_(\d{4}-\d{2}-\d{2})\.kmz$` (приоритет 2, convention 015 §4).
   - `null` (KMZ показывается в dropdown с меткой «—»).
   ISO-формат `YYYY-MM-DD` валидируется regex'ом.

3. **Per-layer storage** `kmlLayers[i].graphHtml` + `kmlLayers[i].extractDate` (новые поля). Передаются через `_loadKMLFromText(extras)`. `_kmzGraphHtml` остаётся как singleton-зеркало активного слоя (минимум diff в 6 read-сайтах).

4. **`_activeLayerIdx` (module-level)** — индекс активного слоя; default `-1`, обновляется при KMZ load до `kmlLayers.length-1` (последний загруженный активен), и через dropdown.

5. **`setActiveKMZLayer(idx)`** — переключение:
   - Для каждого `kmlLayers[i]`: `map.addLayer(L.layerGroup)` + `visible=true` если `i===idx`; иначе `removeLayer` + `visible=false`.
   - `_kmzGraphHtml = kmlLayers[idx].graphHtml`.
   - `_refreshGraphTab()` (показывает/скрывает sidebar tab «Граф»).
   - Если граф iframe открыт — обновляет `srcdoc`.
   - `renderList()` — обновление sidebar marks.

6. **`_refreshKmzDateSwitch()`** — построение `<select id="kmz-date-switch">`:
   - Hidden при `kmlLayers.length < 2`.
   - Sort: по `extractDate` ISO восходяще; KMZ без даты — в конец.
   - Label option: `"YYYY-MM-DD — filename.kmz"` или `"— — filename.kmz"` если даты нет.
   - Selected: `_activeLayerIdx`.

7. **HTML dropdown** в шапке после `#share-btn`: `<select id="kmz-date-switch" onchange="setActiveKMZLayer(+this.value)">`. Стиль монохромный, соответствует существующим control'ам.

8. **`clearAll`** — reset `_activeLayerIdx=-1` + `_refreshKmzDateSwitch()`.

**Что не вошло в Phase 1 (явно):**

- **Plyавный slider (Phase 2)** — отдельный PR `viewer/multi-kmz-timeline-phase2` ждёт ratification `CONTRACT_TIMELINE.md` v1.0 (CORRESPONDENCE/019). Сейчас slider дискретный — выбор из списка KMZ, переключение через addLayer/removeLayer (не client-side apply delta-effects).
- **`clearKMZLayer(i)` для одиночного удаления слоя** — не реализован; `clearAll` сбрасывает все. Single-layer-remove не существует в текущем коде.
- **Сохранение `_activeLayerIdx` в localStorage** — при reload браузера активный слой не восстанавливается; пользователь выбирает заново через dropdown.
- **Применение `delta_effects` из `documents.json`** между snapshot'ами — Phase 2, требует `timeline.json` sidecar.

**Инварианты:**

- `node --check` чист, inline-script = **500197 chars** (+5076 vs B1+B3 baseline 495121).
- Дефолт single-KMZ — байт-в-байт прежний: dropdown hidden, `_kmzGraphHtml` поведение как было, существующие read-сайты (5068, 5075, 6188, 6197) работают без изменений.
- При single-KMZ `_activeLayerIdx` = 0 (последний загруженный), set автоматически в `loadKMZFromFile`.
- Backward-compat KMZ 2.11.0 (без `<Data extract_date>`) — fallback на filename → «—» в dropdown.

**Smoke-test на PR #37 batch:**

1. Open `viewer/index.html`.
2. Load all 3 KMZ из `parser/scripts/dev/multi_extract_sample/`.
3. Dropdown в шапке появляется: «2026-01-15 — demo-multi-extract_2026-01-15.kmz», «2026-04-15 …», «2026-08-01 …».
4. Switch dropdown → виден только выбранный KMZ на карте, остальные скрыты.
5. Граф iframe (sidebar tab) обновляется при переключении (если у parser-side был сгенерирован per-KMZ graph.html; в текущем sample может быть один общий — fallback корректен).
6. `clearAll` → dropdown скрывается, всё сбрасывается.

**Файлы:**

- `viewer/index.html` — +127 / −7 строк (8 точечных правок: parseKML docExtData, loadKMZFromFile cascade + extras, _activeLayerIdx + setActiveKMZLayer + _refreshKmzDateSwitch, HTML dropdown, clearAll reset).

**Ветка:** `viewer/multi-kmz-timeline-phase1`.
