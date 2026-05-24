# multi-extract sample KMZ batch (smoke-fixture для B2)

**Назначение:** активация `viewer/multi-kmz-timeline-phase1` (B2 dropdown
«текущая дата»). Минимальный synthetic batch для smoke-теста — viewer-team
запросили в посте 022 «хоть 2 KMZ, даже синтетические».

## Файлы

| Файл | extract_date | sha256 |
|---|---|---|
| `demo-multi-extract_2026-01-15.kmz` | 2026-01-15 | `ddc59554...8f21` |
| `demo-multi-extract_2026-04-15.kmz` | 2026-04-15 | `c62ed127...ed67` |
| `demo-multi-extract_2026-08-01.kmz` | 2026-08-01 | `26e35695...291e84` |

Каждый KMZ:
- Содержит **`<Document><ExtendedData><Data name="extract_date">YYYY-MM-DD</Data>`**
  (контракт KMZ 2.12.0 §5).
- Содержит **sidecar `_data/documents.json`** (контракт KMZ 2.12.0 §5
  reserved path) с тремя записями: 2 ЕГРН-выписки (`ee_demo01` 2026-01-15,
  `ee_demo02` 2026-04-15) + 1 overlay-документ (`nr_demo01` снятие ареста
  2026-03-01 с `external_url`-полем — для B3 lightbox lookup).
- Содержит одинаковую базовую KMZ-структуру (1 ЗУ + 1 здание + 1 квартира
  + 1 БУ + 1 EQ + 1 бенефициар + 3 photoPin'а) — это базовый mini-fixture
  с PR-A #18 + `--with-overlay`.

## Различие между snapshot'ами

Поле `restrictions` объекта `c2` (здание 61:44:0050706:31) в
`_data/structure.json` меняется между snapshot'ами (имитация юр.факта
«арест → снятие»):

| Snapshot | `c2.restrictions` |
|---|---|
| 2026-01-15 | `[{type:"арест", basis:"Постановление суда от 2025-12-01", since:"2025-12-01"}]` |
| 2026-04-15 | `[]` (снят) |
| 2026-08-01 | `[]` |

**Важно:** этот diff живёт в `structure.json` parser-internal, **не в
KML**. KML/wire-формат показывает только geometry/object_type/cad_number;
restrictions — bookkeeping. Viewer для timeline-UI читает только
`<Data extract_date>` + filename + EXIF — этого достаточно для B2
dropdown.

## Как viewer-team использует

```
1. Загрузить все три KMZ через drag-drop (либо `<input type="file" multiple>`).
2. viewer определяет даты:
   - В первую очередь — из `<Document><ExtendedData><Data extract_date>`.
   - Fallback на имя файла (regex `_(\d{4}-\d{2}-\d{2})\.kmz$`) если
     `<Data>` не найден.
   - Fallback на EXIF photoPin'и (резервный) — для очень старых KMZ
     без convention.
3. dropdown «текущая дата T» с 3 пунктами (2026-01-15 / 2026-04-15 /
   2026-08-01).
4. Переключение между датами — re-render layer (per-layer `graphHtml`
   refactor); zoom/pan state сохраняется в parent UI.
```

## Регенерация

Если sample потребует обновления (например, viewer хочет другой
filename convention или другие даты):

```bash
python3 parser/scripts/dev/make_mini_fixture.py /tmp/multi_extract \
    --extract-dates "2026-01-15,2026-04-15,2026-08-01" \
    --project-slug "demo-multi-extract" \
    --with-overlay

cp /tmp/multi_extract/kmz-kml/demo-multi-extract_*.kmz \
   parser/scripts/dev/multi_extract_sample/
```

Параметры:
- `--extract-dates "ISO1,ISO2,...,ISON"` — список дат через запятую (ISO `YYYY-MM-DD`).
- `--project-slug` — префикс filename (default `demo`).
- `--with-overlay` — добавить `_data/documents.json` (рекомендуется
  для smoke B3 lookup).

## Что НЕ покрывает sample

- **Realistic data:** все 3 KMZ имеют одну и ту же geometry/наименования
  (только restrictions меняется). Для UI/UX smoke этого достаточно;
  для full-cycle тестов viewer-team может попросить parser-team
  сгенерить batch на основе реальных выписок.
- **Phase 2 timeline.json sidecar:** этот sample — для Phase 1 dropdown.
  Phase 2 потребует `<project>/timeline.json` рядом с KMZ-набором
  (см. CORRESPONDENCE/019 §2.1).
