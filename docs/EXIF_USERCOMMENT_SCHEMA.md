# EXIF UserComment схема (JPG-документы и фото от парсера ekcelo)

**Статус:** parser-internal **стабильная** схема. Версия: `1.2` (с 2026-05-28, добавлено опц. поле `note` для per-фото заметок экономиста; v1.1 — с 2026-05-25, контракт KMZ 2.12.0 §5; v1 — с 2026-05-19, контракт KMZ 2.11.0 §5).
**Эмитент:** `parser/scripts/pirushin_sosn_rocha_07_init_project_v1.py`
(меню 2: PDF/DOC→JPG; меню 3: сортировка `Не_распределено/`).
**Потребители (необязательные):**
- viewer (S6+ `viewer/exif-lightbox-routing` — UX «открыть документ ↔ перейти на узел графа»);
- `08_build_kmz_v2.py` сейчас НЕ читает EXIF (использует `description`/`ExtendedData`);
- внешние диагностические инструменты.

## Scope (важно: контракт-like, но НЕ wire-инвариант KMZ)

Формат JSON-payload внутри EXIF `UserComment` JPG-файлов, попадающих в
`docs/<f>` и `images/<f>` финального KMZ-архива. **Не часть wire-формата KMZ**
(см. контракт §5 «(2.11.0+, информативно — parser-internal, НЕ контрактный
инвариант)»). Wire-инварианты от этого поля **не зависят**: viewer/GE Pro
полноценно работают без чтения EXIF.

Эта схема — **стабильное соглашение** между 07-генератором и его потребителями.
Парсер обязуется сохранять backward-compatibility: новые поля добавляются
аддитивно (никогда не удаляются и не переименовываются), потребители
fail-safe игнорируют неизвестные ключи.

## Где лежит payload

```
EXIF (TIFF) → Exif IFD → 0x9286 UserComment
  → Encoding: "unicode" (см. piexif.helper.UserComment.dump)
  → Body: JSON-сериализованный объект, UTF-8, ensure_ascii=False
```

Запись: `parser/scripts/07_init_project_v1.py:write_exif()` (PDF→JPG)
и `:annotate_photo_exif()` (фото из `Не_распределено/`).

Чтение (пример Python):
```python
import piexif
from piexif.helper import UserComment
import json

exif = piexif.load(str(jpg_path))
raw = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment)
if raw:
    payload = json.loads(UserComment.load(raw))
```

Чтение (пример JavaScript для viewer'а — через `exifr` или `piexifjs`):
```js
import * as piexifjs from "piexifjs";
const exif = piexifjs.load(jpegBinaryString);
const uc = exif?.Exif?.[piexifjs.ExifIFD.UserComment];
if (uc) {
  // UserComment начинается с 8-байтового encoding header ("UNICODE\0").
  // Парсим UTF-16LE / ASCII / Undefined по первым 8 байтам, body — JSON.
  const body = decodeUserComment(uc);            // см. piexif spec §4.6.4
  const payload = JSON.parse(body);
  if (payload.app === "ekcelo") { /* use payload */ }
}
```

## Схема payload (стабильно с v1)

Все поля **опциональны** на стороне потребителя. Парсер эмитит все известные;
неизвестное на стороне 07 → `null`.

| Ключ              | Тип             | Описание                                                  |
|-------------------|------------------|-----------------------------------------------------------|
| `app`             | string           | Всегда `"ekcelo"`. Маркер «наш payload»; обязательная проверка перед использованием остальных полей. |
| `kind`            | string           | Категория JPG. Для документов: `"egrul"`/`"egrip"`/`"egrn"`/`"svid"`/`"tehpasp"`/`"tehplan"`/`"doc"`. Для фото из меню-3: `"photo"`. |
| `cad`             | string \| null   | Кадастровый номер (`61:44:0050706:31` или с частью `/N`), если документ/фото привязаны к КН. |
| `inn`             | string \| null   | ИНН ЮЛ/ИП (10 или 12 цифр) — для ЕГРЮЛ/ЕГРИП документов или owner-фото. |
| `ogrn`            | string \| null   | ОГРН/ОГРНИП — для ЕГРЮЛ/ЕГРИП. |
| `obj_id`          | string \| null   | `cadastre_objects[].id` из `structure.json` (parser-internal). |
| `bu_id`           | string \| null   | `business_units[].id` из `structure.json` (parser-internal). |
| `object_type`     | string \| null   | Категория объекта: `"land"`/`"building"`/`"room"`/`"structure"`/`"ons"`. |
| `extract_number`  | string \| null   | Номер КУВИ выписки ЕГРН (например `КУВИ-001/2026-…`). |
| `doc_date`        | string \| null   | Дата документа в ISO `YYYY-MM-DD`, если распознана. |
| `xml_matched`     | bool             | `true` если рядом с PDF лежал парный XML и данные взяты из него. |
| `xml_extract_date`| string \| null   | Дата выгрузки из XML (ISO). |
| `src`             | string           | Имя исходного файла (PDF/DOC/JPG). |
| `src_ext`         | string           | Расширение исходника (`"pdf"`/`"doc"`/`"docx"`/`"jpg"`). |
| `page`            | int              | Номер страницы (1-based). |
| `page_count`      | int              | Общее число страниц в источнике. |
| `center_lat`      | float \| null    | Широта центра объекта (продублирована в GPS-секции EXIF). |
| `center_lon`      | float \| null    | Долгота центра объекта. |
| `height_m`        | float \| null    | Высота объекта над землёй (метры). |
| `altitude_amsl_m` | float \| null    | Абсолютная высота AMSL (на будущее, обычно `null`). |
| **`graph_node_id`** | string \| null | **Ключ узла в `graph.html`** (см. контракт KMZ 2.11.0 §5 + 2.12.0 §5). Регекс: `^[A-Za-z0-9_:/-]{1,256}$`. Формулы: `<cn>` / `bu::<sha1>` / `eq::<id>` / `legal::inn::<inn>` / `legal::ogrn::<ogrn>` / `doc::<doc_id>` (v1.1+). |
| **`doc_id`**      | string \| null   | **(v1.1+)** Идентификатор документа в `<project>/_data/documents.json` (sidecar реестра, схема — `dev/SPEC_TEMPORAL_REPORTS.md` §4.2). Формат: `<kind-prefix>_<sha8>` (например `ee_a1b2c3d4` для ЕГРН-выписки). Используется viewer-lightbox для group-by (несколько JPG одного документа = одна логическая группа в навигации) и для resolve формулы `doc::<doc_id>` графа. Если sidecar `documents.json` отсутствует — поле `null` (старая семантика). |
| `ts`              | string           | UTC-таймстемп записи EXIF в ISO-8601 `…Z`. |

Для `kind:"photo"` (меню 3 — миграция фото) набор немного отличается:

| Ключ           | Тип            | Описание                                       |
|----------------|----------------|------------------------------------------------|
| `app`          | `"ekcelo"`     | то же                                          |
| `kind`         | `"photo"`      | то же                                          |
| `cad`          | string \| null | КН-привязка фото                               |
| `category`     | string \| null | Подкатегория `Фасад`/`Кровля`/`Интерьер`/…     |
| `semantic`     | string \| null | Семантическая привязка (`Сооружение`/…)        |
| **`note`**     | string \| null | **(v1.2+)** Per-фото заметка экономиста (свободный текст, ≤1000 символов). Если несколько заметок — разделять `; `. Stage 6 ETL EXIF собирает `note`-поля по КН в `object_etp_profile.extras.notes`. Опционально; `null` или отсутствие = старая семантика (v1.1-фото). |
| `source`       | string         | Исходный путь файла (из `Не_распределено/…`)   |
| `graph_node_id`| string \| null | То же, что выше; для фото = КН-узел            |
| `migrated_at`  | string         | UTC-таймстемп миграции (ISO-8601 `…Z`)         |

GPS, `DateTimeOriginal` и другой EXIF от оригинала **сохраняется** — 07 не
перетирает съёмочные таймстемпы и координаты камеры (только дописывает
`ImageDescription` и `UserComment`).

## Резолв `graph_node_id` (стабильно с v1; v1.1+ — добавлена формула документ-узлов)

```python
def resolve_doc_graph_node_id(meta, gidx):
    # v1.1+: документ-узел приоритетнее (если doc_id известен — узел документа
    # стабильно резолвится формулой doc::<doc_id>, не требует sidecar).
    doc_id = meta.get("doc_id")
    if doc_id:
        return f"doc::{doc_id}"

    cad = meta.get("cad")
    if cad:
        return gidx.get("by_cad_number", {}).get(cad) or cad
    inn = meta.get("inn")
    if inn:
        return gidx.get("by_ben_inn", {}).get(str(inn)) or f"legal::inn::{inn}"
    ogrn = meta.get("ogrn")
    if ogrn:
        return gidx.get("by_ben_ogrn", {}).get(str(ogrn)) or f"legal::ogrn::{ogrn}"
    return None
```

`gidx` — sidecar `_data/graph_node_index.json` от `04_nspd_graph_v14.py`.
Если sidecar не найден — fallback на formula (cn/inn/ogrn/doc_id).

**Стабильность формулы `doc::<doc_id>`** (v1.1+): формула гарантирует
client-side resolve без новых полей в KMZ `<ExtendedData>` photoPin'ов —
viewer строит nodeId документа из `payload.doc_id` напрямую
(договорено CORRESPONDENCE/014 §C / 015 §1 / 016 §1; контракт KMZ
2.12.0 §6).

## Backward-compatibility policy

- **Аддитивно:** новые ключи могут появляться. Потребители игнорируют незнакомые.
- **Без переименований:** существующие ключи не переименовываются и не меняют тип.
- **Без удалений:** ключи помечаются `DEPRECATED` в этом файле, эмитируются `null`,
  но не выпиливаются. Удаление = новая major-версия схемы (v2), о которой
  парсер сообщит постом в `docs/CORRESPONDENCE/`.
- **Версионирование:** схема не имеет явного `version`-поля в payload
  (избыточно — `app === "ekcelo"` + стабильный набор ключей). Если в будущем
  потребуется major-bump — добавим `schema: 2` опционально.

## Известные потребители

- `08_build_kmz_v2.py` — НЕ читает (использует `description`/`ExtendedData`).
- viewer (S6+ `viewer/exif-lightbox-routing`) — планируется чтение
  `graph_node_id` из открытого в lightbox JPG для UX «к узлу графа».
  Чтение остальных полей — на усмотрение viewer-team.

## История

| Версия | Дата       | Что                                                      |
|--------|------------|----------------------------------------------------------|
| 1      | 2026-05-19 | Первичная редакция. `graph_node_id` добавлен в эту же v1 в рамках контракта KMZ 2.11.0 §5 (информативный пункт). До 2.11.0 поле отсутствовало — viewer должен это учитывать (fallback: документ без `graph_node_id` → UX «к узлу» недоступен). |
| 1.1    | 2026-05-25 | Аддитивно: поле `doc_id` (ссылка на запись в `documents.json` sidecar — `dev/SPEC_TEMPORAL_REPORTS.md` §4.2); формула резолва `graph_node_id` расширена `doc::<doc_id>` для документ-узлов графа. Контракт KMZ 2.12.0 §5 + CORRESPONDENCE/014-016. Backward-compatible: JPG v1 без поля `doc_id` остаются валидными — viewer fail-safe ignore (старая семантика `cad/inn/ogrn` сохранена). |
| 1.2    | 2026-05-28 | Аддитивно: опц. поле `note` (string \| null) в payload `kind:"photo"` для per-фото заметок экономиста. Stage 6 ETL EXIF (`parser/exporters/etp/etl_exif.py`) собирает `note`-поля по `cad_number` в `object_etp_profile.extras.notes` (joined `«; »`, idempotent gap-fill). CORRESPONDENCE/027 (parser proposal) + 028 (viewer ack 5/5). Контракт KMZ не затрагивается. Backward-compatible: v1.1-фото без `note` рендерятся как раньше; v1.2-ридер на старых фото не падает. |
