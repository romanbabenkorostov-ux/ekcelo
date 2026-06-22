# 2026-06-22 — FE-3.1 hotfix: сырой .kml (Yandex Map Constructor)

## Проблема
Пользователь перетащил реальный `.kml` (Yandex Map Constructor, винодельня
«Олимп», 45 точек + полигоны) → **«Ошибка KMZ: invalid zip data»**. Причины:
1. `.kml` — сырой XML, не ZIP; адаптер звал `unzipSync` → падал.
2. cad_number у Yandex сидит в `<description>` текстом
   («Поле 23:15:0000000:2267 · …»), а не в `<ExtendedData>`.
3. `<name/>` у полигонов пустой self-closing.

## Что сделал (3 пункта)
1. **Принимаем .kml + .kmz.** `parseGeoFile(file)` диспетчеризует по
   расширению: `.kml` → `parseKmlFile` (текст, без распаковки), иначе →
   `parseKmzFile` (ZIP). Drop-зона `accept=".kml,.kmz"`.
2. **cad_number из description regex.** Если нет `ext.cad_number` — берём
   первый `\d+:\d+:\d+:\d+` из description, затем из name. Метка полигона с
   пустым `<name/>` — первый сегмент description до «·» (без `<br/>`).
3. **Список объектов после загрузки.** Под drop-зоной — кликабельный список
   объектов с кадастром (дедуп по cad) → `#/objects/{cad}`.

## happy-dom фиксы (тест-среда)
- `<name/>` self-closing happy-dom не закрывал → вкладывал соседей внутрь.
  `normalizeKml()` разворачивает `<name/>`/`<description/>` в парные теги
  (CDATA не трогаем; реальный браузерный XML-парсер корректен и без этого).
- `cdataText` теперь собирает ТОЛЬКО прямые text/cdata/comment узлы (раньше
  `node.textContent` мог вернуть текст ошибочно вложенных элементов).
- `childTag` fallback на scoped `getElementsByTagName` (если `.children`
  обрезан CDATA-соседом).

## Файлы
- ✏️ `ekcelo-site/src/adapters/kmz.ts` — parseKmlFile/parseGeoFile,
  normalizeKml, cad-from-description, cdataText/childTag устойчивость.
- ✏️ `ekcelo-site/src/main.ts` — accept .kml/.kmz, parseGeoFile, список
  объектов (`renderKmzObjects`).
- ✏️ `ekcelo-site/src/styles.css` — `.kmz-objects` список.
- ✨ `ekcelo-site/tests/kml-yandex.test.ts` — 7 тестов на реальной фикстуре.
- ✨ `ekcelo-site/tests/fixtures/yandex_olimp.kml` — реальный экспорт «Олимп».

## Тесты
- **73 vitest** (66 + 7 FE-3.1). TypeScript strict 0. ESLint 0.
- Build: main 27.7KB (11.4KB gz) + leaflet chunk lazy.

## Канал доставки
Sandbox-proxy блокирует push — zip-handoff (после merge FE-3).
