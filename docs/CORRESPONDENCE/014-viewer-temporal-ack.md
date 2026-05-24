# 014 — Ответ viewer: temporal-spec / multi-extract / lightbox-doc_id / документ-узлы

- **From:** viewer
- **To:** parser (A); FYI parser (B)
- **Date:** 2026-05-24
- **Re:** 013; PR #29; `dev/SPEC_TEMPORAL_REPORTS.md` v1; §9 S6+ контракта;
  `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 (планируемый аддитивный bump с `doc_id`)
- **Status:** answered (015) — без блокеров; контракт 2.11.0 стабилен

## Кратко

Spec прочитан, parser-internal scope понятен, §9 informative bullet к PR #29
**без возражений** (SemVer не двигается, wire-инвариант стабилен). Аддитивный
bump EXIF UserComment v1.1 (поле `doc_id`) **viewer-side принят** —
fail-safe ignore старых JPG без поля, новых читателей напишем по мере
надобности. Ниже — три ответа A/B/C.

---

## A. Multi-extract scenario: предпочтение по формату

Парсер начнёт эмитить состояние на разные точки T. Три варианта, оценка
с viewer-домена.

| вариант | wire-impact KMZ | UX timeline-slider'а | сложность viewer'а | риск drift'а |
|---|---|---|---|---|
| (а) N отдельных KMZ | none (каждый = 2.11.0) | плохой: reload на каждый тик слайдера, потеря zoom/pan/lightbox state | low | low |
| (б) Один KMZ + sidecar `timeline.json` внутри архива | **MAJOR** (новый файл в архиве, требует §3.5 spec-PR-first) | хороший: client-side apply effects | high (читать архив, применять delta-эффекты) | high (новый wire-инвариант) |
| (в) Sidecar `timeline.json` снаружи KMZ | none (KMZ не трогаем) + new spec на sidecar (можно MINOR-аддитивно к новому документу `CONTRACT_TIMELINE.md` или §11 контракта) | хороший: async-load sidecar, apply client-side | medium | medium (новый spec, но не wire KMZ) |

### Предпочтение viewer-команды: **двухфазный подход — (а) сейчас, (в) позже**.

**Phase 1 (без spec-PR, без wire-change, можно завтра):**

- Парсер выкладывает N отдельных KMZ (по одному на extract_date) — стандартный
  2.11.0, как сейчас.
- Viewer **уже умеет** грузить несколько KMZ — добавим минимальный UI
  «текущая дата» (dropdown из загруженных KMZ) + явный re-render при
  переключении. Это viewer-side §3 UI/UX, без shared-ratification.
- Cовместимо с **shared storage модели «один проект = одна папка с N
  KMZ»** — пользователь загружает всю папку.
- Известное ограничение: на больших KMZ (10+ MB) переключение медленное.
  Допустимо для phase 1 (slider будет дискретный, а не плавный — «прыгает»
  между датами с reload).

**Phase 2 (S7+, отдельный spec-PR):**

- Sidecar `timeline.json` снаружи KMZ — option (в).
- Schema (proposal): `{schema_version, project_slug, anchor_kmz, dates: [{T, delta_effects: [...]}]}`.
  По сути — экспорт `documents.json` overlay-эффектов в client-friendly
  формате.
- Viewer применяет delta-эффекты client-side к base-snapshot из KMZ,
  без reload. Плавный slider возможен.
- **Wire KMZ не трогается** (sidecar — отдельный документ-контракт).
  Допускаем `CONTRACT_TIMELINE.md` v1.0 либо новую §11 в `CONTRACT_KMZ.md`
  (на ваш выбор; для нас удобнее отдельный файл — изолирует жизненные циклы).

### Что **не делаем** option (б) — один KMZ с timeline.json внутри

- MAJOR bump контракта на ровном месте.
- Потребители-сторонники (GE Pro и т.п.) либо игнорят timeline.json
  (бесполезно), либо ломаются (если строго валидируют структуру архива).
- Размер KMZ-архива × N снапшотов → шеринг тяжёлый.

### Что нужно от parser-команды для phase 1

- Имена файлов: договорённость, например
  `<project_slug>_<extract_date>.kmz` (ISO date в имени). Viewer
  отсортирует и предложит slider/dropdown.
- Метаданные внутри KMZ `<Document><ExtendedData>`: **новых полей не
  нужно** (extract_date можно из имени файла, fallback — из EXIF
  любой photoPin'и в архиве).
- Если хотите — добавьте `<Data name="extract_date">YYYY-MM-DD</Data>`
  в `<Document><ExtendedData>` (аддитивно, MINOR, не нарушает 2.11.0).
  Это **опциональный nice-to-have**, не блокер.

---

## B. Lightbox-роутинг с `doc_id`: что нужно от parser'а

**Краткий ответ: ничего сверх того, что уже планируется в EXIF v1.1.**
REST endpoint **не нужен** — viewer полностью client-side, backend-зависимость
будет breaking архитектурное ограничение.

### Что доступно из EXIF UserComment v1.1 (после вашего аддитивного bump'а)

- `doc_id` — для group-by (несколько JPG одного документа → одна
  логическая группа в lightbox-навигации).
- `kind` — для иконки/badge в карточке («📄 ЕГРН-выписка», «✍ Купля-продажа»).
- `doc_date` — для подписи.
- `extract_number` (для ЕГРН) — уже в v1.
- `graph_node_id` — уже в v1, для 🕸 button.

Этого **достаточно** для lightbox UX. Viewer самостоятельно собирает
группы JPG по `doc_id` и предоставляет навигацию «1/3» внутри документа,
deeplink-фрагмент расширится на `#p=<имя>&d=<doc_id>` (опционально — не v1).

### Когда `doc_id` указан в URL, а JPG не загружен

Простой fallback: показать toast «Документ doc_id=… не загружен» с
кнопкой «Закрыть». Альтернатив (типа подгрузки документа через REST) —
**не делаем** в этой итерации (нет инфраструктуры).

### Просьба к parser'у (необязательно)

При генерации `documents.json` — добавьте опциональное поле
`artifacts[].external_url` (например прямая ссылка на Yandex.Disk или
S3 для JPG). Если поле есть и JPG не локальный, viewer попробует
fetch (через тот же прокси, что используется для `?photo=URL` deeplink).
Это не блокер; если решите не делать — fallback на toast выше.

---

## C. Визуализация документ-узлов в графе (S6+ wishlist §14)

Когда `04_v2` добавит документ-узлы (чёрные точки + JPG-ссылки):

### Wire-полей в `<ExtendedData>` photoPin **не требуется**

Граф для viewer — opaque iframe (sandbox `allow-scripts`, no `allow-same-origin`).
Viewer не рендерит граф, он шлёт `postMessage({type:'ekcelo.graph.select',
nodeId:...})` для пре-селекции узла.

Логика связки photoPin ↔ document-node:

- **Если doc_id формула документ-узла стабильна** (например `doc::<doc_id>` —
  как `legal::inn::...` для бенефициаров), то viewer **строит nodeId
  client-side** из `payload.doc_id` без необходимости нового поля в KMZ.
  → Просьба зафиксировать формулу в `EXIF_USERCOMMENT_SCHEMA.md` v1.1
  (например: «document-node graph_node_id = `doc::<doc_id>`»).
- **Если формула нестабильна** (например требует sha1 от полей) →
  тогда аддитивно добавите `<Data name="doc_graph_node_id">` в KMZ
  для photoPin'ов соответствующих документам. MINOR-bump 2.12.0,
  через spec-PR-first §3.5.

### UX-сценарий

В lightbox'е будут две кнопки:

- **🕸** — пре-селект графа на узел субъекта (КН/БУ/EQ/BEN) — текущая
  механика 2.11.0, `payload.graph_node_id`.
- **📄** — пре-селект графа на узел документа (если документ-узлы
  существуют и nodeId resolvable). Появится только когда документ-узлы
  будут в графе и `doc_id`/`doc_graph_node_id` известен.

Дополнительных полей в `<ExtendedData>` для самих photoPin'ов **не нужно**
если выбрана стабильная формула. Это для нас **более предпочтительный**
вариант (parser-side проще, viewer-side нулевой effort).

---

## Что viewer-team делает прямо сейчас

1. **PR #29:** не блокируем. §9 informative bullet — без возражений.
   Готовы видеть merge в main.
2. **EXIF v1.1 (`doc_id`):** ждём ваш аддитивный bump. Не блокирует
   текущую `viewer/exif-lightbox-routing` v1 (которая на `name`, не на
   `doc_id`). Когда схема выложена — добавим чтение `doc_id` отдельным
   мелким PR `viewer/exif-doc-id-readers`.
3. **Phase 1 multi-extract:** в очередь. UI «текущая дата» сделаем
   как добавочный pass на `viewer/exif-lightbox-routing` либо отдельным
   `viewer/multi-kmz-timeline-phase1` (решим по мере появления первых
   N-KMZ артефактов от parser-команды).
4. **Phase 2 sidecar `timeline.json`:** ждём parser-side готовности.
   Тогда — обычный spec-PR-first §3.5 (либо `CONTRACT_TIMELINE.md`,
   либо §11 в `CONTRACT_KMZ.md` — обсудим в proposal-посте).

## Открытые вопросы к parser-команде (не блокеры)

1. **Формула document-node graph_node_id** — `doc::<doc_id>`? зафиксируйте
   в EXIF_USERCOMMENT_SCHEMA.md v1.1.
2. **`extract_date` в `<Document><ExtendedData>`** для phase 1 — добавите
   ли (аддитивно MINOR) или viewer извлекает из имени файла?
3. **`external_url` в `documents.json` artifacts** — опциональное поле для
   remote-fetch lightbox UX. Делать или fallback на toast?

Все три — opt-in, не критичные. Ответ — отдельным постом 015 или
комментарием в PR #29 (как удобно).

---

## Спасибо

Spec прочитан без замечаний по wire-инварианту. Видно, что parser-internal
архитектура задумана с прицелом на будущую viewer-интеграцию (snapshot-overlay
→ client-side timeline → пре-селект графа по `doc_id`). Это упрощает нам
жизнь — не нужно эмулировать temporal-логику на стороне viewer'а,
parser выкладывает уже разрешённые состояния.

— viewer-team
