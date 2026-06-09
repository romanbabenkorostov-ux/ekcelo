# ADR-005 (proposed): ЗУ / ЕЗП / МКУ — многоконтурность + технологические свойства контуров

**Статус:** Proposed · **Дата:** 2026-06-08 · **Автор:** parser-team
**Связанные:** [[2026-05-25-contour-sidecar-architecture]], [[ADR-001-etp-profile-extension]],
`parser/scripts/01b_ingest_contours.py`, `egrn_parser/db/schema.sql`
(`land_objects`/`object_geometries`/`linked_objects`)
**Источник:** `ЗУ_ЕЗП_МКУ_в_ЕСПД.md` (онтология Росреестр/НСПД).

## Контекст

Земельные участки в ЕГРН/НСПД представлены тремя способами, и это меняет
топологию, кадастровую иерархию и жизненный цикл:

| | ЗУ | ЕЗП (архивный) | МКУ (современный) |
|---|---|---|---|
| Контуров | 1 | ≥2 | ≥2 |
| КН | 1 | главный + дочерние КН | 1 (на весь объект) |
| Контуры | сплошной полигон | дочерние = самостоятельные ЗУ с КН | порядковые `:КН(1)`,`:КН(2)`, без своих КН |
| Маркер | — | текст `(Единое землепользование)` после КН | нумерация контуров |

**Проблема.** Текущая модель хранит геометрию как ОДИН `MultiPolygon` на объект
(`object_geometries.geom_geojson`, sidecar `contours.json.полигоны[]`). У отдельного
контура нет ни идентичности, ни собственных атрибутов. Заказчику нужно, чтобы
**у каждого контура были свои технологические свойства** (сорт винограда,
обработки, климат) — текущая модель это не несёт.

## Решение (предложение)

### A. Тип представления — на родительском объекте

`land_objects` += `land_layout_type TEXT` ∈ {`ЗУ`,`ЕЗП`,`МКУ`} (детект):
- `ЕЗП` — если в КН/семантике есть `(Единое землепользование)` ИЛИ есть дочерние КН;
- `МКУ` — если ≥2 несвязных контуров и один КН без дочерних;
- `ЗУ` — иначе (1 контур).
Существующие `nested_objects`, `predecessor/successor_cad_numbers`,
`transformation_*` остаются (history/реорг).

### B. Контур как сущность — новая таблица `land_contours`

Поднимаем контур из «кольца в MultiPolygon» до адресуемой строки:

```sql
CREATE TABLE land_contours (
    contour_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_cad      TEXT NOT NULL,              -- КН родителя (ЗУ/ЕЗП/МКУ)
    contour_no      INTEGER NOT NULL,           -- 1..N (порядок, :КН(1)…)
    contour_cad     TEXT,                       -- дочерний КН (ЕЗП) | NULL (МКУ/ЗУ)
    geom_geojson    TEXT,                       -- Polygon контура
    area_sqm        REAL,
    centroid_lon    REAL, centroid_lat REAL,
    geom_source     TEXT,                       -- wfs|pkk|manual|… (приоритет ADR contour-sidecar)
    graph_node_id   TEXT GENERATED ALWAYS AS ('contour_' || parent_cad || '_' || contour_no) VIRTUAL,
    UNIQUE(parent_cad, contour_no)
);
```

Маппинг трёх типов в одну модель:
- **ЗУ** → 1 строка `land_contours`, `contour_cad = parent_cad`.
- **МКУ** → N строк, `contour_cad = NULL` (своего КН нет), `contour_no = 1..N` (`:КН(i)`).
- **ЕЗП** → N строк, `contour_cad = дочерний КН` (каждый — самостоятельный ЗУ; при
  желании заводится и собственная строка `land_objects` + связь, см. C).

`object_geometries` остаётся для совокупной геометрии (MultiPolygon на КН, для
KMZ/обзора); `land_contours` — нормализованный поконтурный слой.
Sidecar `contours.json` расширяется: каждому элементу `полигоны[]` — `contour_no`,
`contour_cad?`, и блок `tech` (см. D).

### C. Схема связей (граф)

Через существующий `linked_objects` (primary↔linked, `link_type`):
- **ЕЗП:** `link_type='ezp_child'` — главный КН → дочерний КН (каждый дочерний
  тоже узел `land_objects`). Двухуровневый узел в графе (родитель-кластер + дети).
- **МКУ:** контуры — НЕ отдельные КН → узлы `land_contours` (`graph_node_id =
  contour_<КН>_<no>`), `link_type='mku_contour'` от родителя к контуру (или
  под-узлы внутри кластера родителя, как группы в company graph).
- **Реорг/преобразование:** `predecessor/successor_cad_numbers` →
  `link_type='reorg_predecessor'|'reorg_successor'` (аналогично юрлицам в
  `entity_relations`, но для земель — `linked_objects`).
- Viewer: ЗУ — один силуэт; ЕЗП/МКУ — кластер контуров (multi-polygon силуэт +
  раскрытие на под-контуры по клику).

### D. Технологическая схема — поконтурный §6-слой

> **Уточнено [[ADR-006-agro-layer-parcels-harvest-treatments]]:** поля экономиста
> (уч.519) НЕ совпадают с кадастровыми контурами и меняются по сезонам, поэтому
> технологический слой вынесен в независимую `agro_parcel` + `agro_event`
> (события+JSON), а не в жёсткий `contour_tech_profile` ниже. Привязка к контуру —
> мягкая (`agro_parcel.land_cad/contour_no`). Блок ниже оставлен как первоначальный
> вариант (superseded ADR-006 §A,C).

Агрономия/технология — НЕ ЕГРН (ADR-001 §6), у контура свои значения:

```sql
CREATE TABLE contour_tech_profile (
    parent_cad   TEXT NOT NULL,
    contour_no   INTEGER NOT NULL,
    crop         TEXT,          -- культура (виноград)
    variety      TEXT,          -- сорт
    treatments   TEXT,          -- JSON[]: {тип, дата, препарат, норма}
    climate      TEXT,          -- JSON: {зона, сумма_темп, осадки, заморозки}
    soil         TEXT,          -- JSON: {тип, pH, бонитет}
    planting     TEXT,          -- JSON: {год, схема_посадки, подвой}
    extras       TEXT,          -- JSON
    source       TEXT NOT NULL CHECK (source IN ('osv','exif','manual','nspd','llm')),
    confidence   REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    updated_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (parent_cad, contour_no)
);
```

- Зеркалит `object_etp_profile` (§6: source+confidence, gap-fill merge
  osv/manual > nspd/exif/llm), но ключ — **контур**, не объект.
- Технологическая схема лота = агрегат `contour_tech_profile` по контурам всех
  ЗУ/ЕЗП/МКУ лота (например «виноград: Каберне 12 га (контуры 1,3), Мерло 8 га
  (контур 2)»).
- При пересоздании БД из выписок §6-слой контуров НЕ восстанавливается (ADR-001).

## Альтернативы (rejected)

- **Хранить тех-свойства в `object_etp_profile` (на объект).** Не даёт
  поконтурной гранулярности (разный сорт на контурах одного МКУ). Отклонено.
- **Контуры только в `contours.json`, без таблицы.** Нет SQL-агрегации для
  техсхемы лота и графа. Sidecar остаётся как geom-источник, но нормализованный
  слой нужен в БД.
- **Моделировать МКУ-контуры как дочерние `land_objects` с псевдо-КН.** Ломает
  «КН уникален»; у МКУ-контура нет своего КН. Отклонено — отдельная сущность
  `land_contours`.

## Последствия

- ✅ Единая модель для ЗУ/ЕЗП/МКУ; поконтурная агрономия.
- ✅ Граф различает дочерние КН (ЕЗП) и безымянные контуры (МКУ).
- ⚠️ Миграция геометрии: разложить MultiPolygon → `land_contours` (одноразовый
  backfill из `object_geometries`/`contours.json`).
- ⚠️ Затрагивает контуры/geom/viewer — согласовать с граф-схемой соседнего чата
  (`contracts/db/SCHEMA_SPEC.md`, граф = логический) перед реализацией.

## Дальнейшие шаги (план)
1. Детект `land_layout_type` в `01_parsing_nspd`/`01b_ingest_contours` (маркер
   `(Единое землепользование)`, дочерние КН, число контуров).
2. Миграция `schema/migrations/0002_land_contours.sql` (+`contour_tech_profile`).
3. Backfill `land_contours` из `object_geometries`/`contours.json` (по `полигоны[]`).
4. Расширить sidecar `contours.json` (`contour_no`/`contour_cad`/`tech`).
5. Граф: `linked_objects` (`ezp_child`/`mku_contour`/`reorg_*`) + viewer-кластеры.
6. Техсхема лота: агрегатор `contour_tech_profile` → ViewModel/отчёт.
