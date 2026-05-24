# 2026-05-24 — viewer/exif-doc-id-readers (B1 + B3 объединённо)

**Что:** реализованы B1 (EXIF UserComment v1.1 `doc_id` reader) и B3 (lightbox lookup в `_data/documents.json` sidecar). Договорено CORRESPONDENCE/014-018; контракт KMZ 2.12.0 + EXIF UserComment v1.1 на main.

**Контракт:** не расширяется. §3 UI/UX, viewer-домен, без shared-ratification.

**Сделано:**

1. **`parseEkceloUserComment(exif)`** — новый парсер EXIF UserComment payload'а `app === "ekcelo"` (v1.1). Возвращает payload as-is (`{app, doc_id, kind, doc_date, graph_node_id, extract_number, ...}`) или `null`. Изолирован от `parseGPPUserComment` (схемы не пересекаются), но обе функции теперь используют общий `_decodeUserCommentJSON()` для декода raw EXIF bytes.

2. **`p.docMeta` populated** на 3 путях загрузки фото:
   - `addLocalPhoto` — drag-drop JPG.
   - `loadSingleRemotePhoto` — Yandex/GDrive/S3.
   - **KMZ media loop** — ранее `experimentData: null` для всех KMZ-фото (регрессия с 2.10.x). Теперь `exifr.parse` на `fileBlob` извлекает и GPP, и ekcelo payload. Чинит обе карточки (📋 опыт + 📄 документ) для KMZ-фото.

3. **`_data/documents.json` extraction** в `loadKMZFromFile` после blob-map. Path-regex `/^(.*\/)?_data\/documents\.json$/i` — поддержка префикса от `08_build_kmz_v2_2`. Содержимое → `Map<doc_id, document>` → передаётся в `_loadKMLFromText(text, name, handle, {documentsIndex})` → сохраняется per-layer в `kmlLayers[i].documentsIndex`.

4. **`_lookupDocument(docId)`** — глобальный хелпер, итерация всех `kmlLayers`. First-hit wins (фаза 1, без cross-layer merge).

5. **Lightbox 📄 секция** в `buildRows(p)` — рендерится только если `p.docMeta?.doc_id`. Содержит:
   - Заголовок «📄 Документ» с иконкой 🕸 (postMessage `doc::<doc_id>` в graph iframe через существующий `_openGraphFor`).
   - `doc_id`, `kind`, `doc_date`, `extract_number` из EXIF UserComment.
   - При наличии `documents.json` lookup: 🔗 «Открыть» — `external_url` из `artifacts[*]` (первое попадание).
   - `notes` из документа если `doc_date` отсутствует в EXIF.

6. **Deeplink `#p=<имя>&d=<doc_id>`** — расширение S6+ v1:
   - `_setLightboxFragment(name, docId)` — пишет `&d=...` если docMeta есть.
   - `_readLightboxFragment()` — возвращает `{name, doc_id}` (раньше только name).
   - `_tryOpenFromFragment` стал `async` — если фото по имени не найдено и есть `doc_id`, ищем `external_url` в `documents.json`, fetch через `loadSingleRemotePhoto`, потом re-open lightbox. Toast если ничего не найдено.
   - `copyShareLink()` — дописывает `&d=...` если активное фото имеет `docMeta.doc_id`.

7. **`ENRICHABLE`** — добавлен `'docMeta'` в список enrich-полей для безопасного re-import'а.

**Идентификатор графа для документа:** `doc::<doc_id>` (стабильная формула, EXIF schema v1.1 §Резолв; контракт 2.12.0 §6). Никаких новых wire-полей в KMZ `<ExtendedData>` photoPin'ов не требуется.

**Инварианты:**
- `node --check` инлайн-скрипта чист (495121 chars; +4868 vs S6+ v1 baseline 490253).
- Дефолтное поведение для KMZ без `ekcelo` EXIF и без `_data/documents.json` — байт-в-байт прежнее (документ-секция в lightbox не рендерится, 📄 кнопки нет, deeplink ведёт себя как S6+ v1).
- Контракт KMZ 2.12.0 не расширяется; viewer fail-safe ignore при невалидном `documents.json`, при отсутствии любого поля, при невалидном `doc_id` в hash.

**Что НЕ вошло в этот PR (явно):**

- **B2 (multi-kmz-timeline-phase1)** — dropdown «текущая дата T», `<Document><ExtendedData>` extract_date capture, per-layer `graphHtml` refactor. Отдельный PR, ~100-130 строк.
- **Group-by по doc_id** в фото-списке sidebar — отложено.
- **Cross-layer merge `documentsIndex`** при конфликте `doc_id` — фаза 1 берёт first-hit.
- **Schema-validation `documents.json`** — fail-safe ignore при невалидном JSON.
- **Восстановление `documentsIndex` при storage rehydration** (`_loadKMLFromText` от localStorage) — `documentsIndex` живёт только пока KMZ загружен из файла; reload браузера потеряет, нужно перезагрузить KMZ.

**Файлы:**

- `viewer/index.html` — +103 / −14 строк суммарно (12 точечных правок: `_decodeUserCommentJSON`, `parseEkceloUserComment`, `_lookupDocument`, addLocalPhoto, loadSingleRemotePhoto, KMZ-loop, ENRICHABLE, `_loadKMLFromText` signature, KMZ-call site, sidecar extraction, `buildRows` document-section, `_setLightboxFragment`/`_readLightboxFragment`/`_tryOpenFromFragment`/`copyShareLink`).

**Ветка:** `viewer/exif-doc-id-readers`.
