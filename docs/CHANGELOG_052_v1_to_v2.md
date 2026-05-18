# CHANGELOG 052: v1 → v2

**Файл:** `pirushin_sosn_rocha_052_make_structure_v2.py`
**Дата:** 2026-05-18
**Базируется на:** `pirushin_sosn_rocha_052_make_structure_v1.py` (929 строк, сохраняется как history)
**Новая длина:** 1796 строк
**Совместимость со спекой viewer:** `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md`

---

## TL;DR для команды viewer

v2 — это **источник полей**, на которых построена спека v2.10.0. Если вы планируете модификации фронта, ориентируйтесь на v2-структуру JSON, а не на v1. Главное:

- `equipment[].links.*_id` (скаляр) → `equipment[].links.*_ids` (массив)
- Появились секции: `photos[]`, `z_meters` (на levels и equipment), `_geometry` с extrude
- ID бизнес-единиц теперь стабильны по `anchor_cadastral`, а не по имени → старые `bu_<slug>` исчезли
- Добавлены `enterprise.inn/ogrn/kpp/external_ids` через cross-link с enriched

---

## 1. Изменения, ломающие контракт (BREAKING)

### 1.1 equipment[].links — теперь массивы

**v1:**
```json
"links": {
  "business_unit_id": "bu_xxx",
  "cadastre_id": "cad_xxx",
  "premises_id": null,
  "level_id": null,
  "location_kind": "level"
}
```

**v2:**
```json
"links": {
  "business_unit_ids": ["bu_xxx"],
  "cadastre_ids":      ["cad_xxx", "cad_yyy"],
  "level_ids":         ["lvl_xxx"],
  "premises_ids":      [],
  "location_kinds":    ["level", "land_point"]
}
```

`location_kinds[i]` соответствует `cadastre_ids[i]`. Если `cadastre_ids` пуст — `location_kinds = ["standalone"]`.

Допустимые значения `location_kind`: `level`, `premises`, `land_point`, `land_contour`, `standalone`.

### 1.2 ID бизнес-единиц

**v1:** `bu_<slugify(name)>` — менялся при правке имени, ломал merge.
**v2:** `bu_<sha1(anchor_cadastral)[:8]>` — стабилен между запусками даже при правке имени/адреса. У BU без КН (Phase B, по эвристике) сохранён `bu_<slugify(name)>`.

**Миграция старых ID:** см. раздел 4 ниже. ID будут переименованы при первом запуске v2 на старом ОСВ — нужен alias-map.

### 1.3 Поле `cadastrals` у BU

**v1:** `cadastrals: []` (всегда массив всех найденных)
**v2:** `cadastrals: []` пуст для address-based BU (используется `anchor_cadastral` как primary), либо массив для остальных. Появилось `anchor_cadastral: "12:34:567:8"` и `external_ids: {}`.

---

## 2. Новые секции в structure_*.json

### 2.1 `photos[]` (новая корневая секция)

Каждое фото:
```json
{
  "id": "ph_<sha1>",
  "path": "C:/…/IMG_1234.jpg",
  "folder_chain": ["02_Здания", "Здание_..."],
  "is_unassigned": false,
  "linked": {
    "cadastre_ids": [], "business_unit_ids": [],
    "equipment_ids": [], "level_ids": [], "premises_ids": []
  },
  "match_kinds": ["cn_mask", "inv_hint", "exif", "bu_name", "address_overlap"],
  "exif": {
    "gps_lat": 55.123, "gps_lon": 37.456, "gps_alt": 145.0,
    "gps_bearing": 87.5, "datetime_taken": "2026:04:12 14:32:01",
    "camera_make": "Apple", "camera_model": "iPhone 14"
  },
  "z_meters": 3.0,
  "z_source": "level" | "exif_gps_alt" | null
}
```

Привязка автоматическая по:
- маске КН в пути (`12_34_567_8` → `12:34:567:8`),
- маске инв.номера (`01.0123`),
- slug-имени папки vs slug BU,
- адресу (≥2 общих токена длиной ≥4 символов),
- EXIF GPS.

Папка `00_Нераспределенные/` (только в корне!) → `is_unassigned=true`, высоты НЕ вычисляются.

### 2.2 Z-координаты (русская система 3 м/этаж)

**В каждом уровне:**
```json
{
  "id": "lvl_xxx",
  "number": 3,
  "type": "Этаж",
  "label": "Уровень 3. Этаж 2",
  "underground": false,
  "z_meters": 3.0,
  "top_z_meters": 6.0,
  "height_m": 3.0,
  "cadastral_source": "12:34:567:8",
  "confirmed": false
}
```

**Правила** (`compute_level_z`):
- подвал K → `-K * 3.0`
- полуподвал / цокольный → `-2.0`
- технич. подполье → `-1.0`
- этаж K (надз.) → `(K - 1) * 3.0`
- антресоль K-го этажа → `(K - 1) * 3.0 + 2.0`
- антресоль без указания → `(N - 1) * 3.0 + 2.0` (N = верхний надз.)
- мансарда / чердак / эксплуат. кровля → `N * 3.0`
- технический этаж (сверху) → `(N + 1) * 3.0`

**В кадастровом объекте:** `height_m` (надземная часть), `depth_m` (подземная).

**В equipment:** `z_meters` (минимум из z привязанных уровней), `z_meters_max` (max + 3.0).

### 2.3 `cadastre._geometry` для KMZ extrude

```json
"_geometry": {
  "bottom_z_meters": -3.0,
  "top_z_meters": 12.0,
  "extrude": true
}
```

Появляется только если есть `height_m` и сырая геометрия из NSPD/ЕГРН.

### 2.4 `enterprise.inn / ogrn / kpp / external_ids`

Автоматически заполняются через cross-link с `enriched_*.json` (см. ниже).
```json
"enterprise": {
  "id": "ent_xxx", "slug": "xxx", "opf": "ООО", …,
  "inn": "7701234567",
  "ogrn": "1027700001234",
  "kpp": "770101001",
  "external_ids": {"enrich_beneficiary_key": "ben::abc123"}
}
```

---

## 3. Новые источники данных на входе

### 3.1 EGRN-style JSON (помимо NSPD)

`load_nspd_objects()` теперь принимает оба формата:
- **nspd-style:** `{"data": {"<Категория>": {"<КН>": {…info…}}}}`
- **egrn-style:** `{"tables": {"building_objects": [{cad_number, address, area, floors_above_ground, …}], "land_objects": [...]}}`

### 3.2 enriched-extras

`load_enriched_extras()` дополнительно вытаскивает:
- `beneficiaries: {<key>: {ИНН, ОГРН, КПП, Полное наименование, …}}` — для заполнения `enterprise.inn/ogrn/kpp`
- `business_units: [{Ключ, Наименование, Объект (КН), Бенефициар (ключ)}]` — для **поглощения** локальных BU (см. 3.3)

### 3.3 Cross-link с enriched (поглощение BU)

`link_with_enriched()` — если наша BU имеет `anchor_cadastral`, совпадающий с `Объект (КН)` из enrich-выгрузки, **локальный `bu.id` заменяется** на `bu::<sha1>` из enriched. Это нужно, чтобы граф `04_nspd_graph_v11` рисовал одну BU, а не две.

Побочный эффект: `equipment[].links.business_unit_ids[]` и `eq_to_bu` обновляются в той же транзакции, остаются консистентными.

### 3.4 Корневая папка с фотографиями (опц.)

CLI добавил вопрос: «Корневая папка с фотографиями». Если указана — сканируется в `photos[]`.

---

## 4. Миграция старых structure_*.json

При первом запуске v2 на старом ОСВ:
- `bu_<slug>` → `bu_<sha1(anchor_cn)>` (для address-based) → **все confirmed=false BU и их eq_to_bu теряются**.
- `equipment[].links.business_unit_id` → `business_unit_ids` → старые поля игнорируются `merge_preserve_confirmed`.

**Рекомендация на стороне команды viewer:** при чтении JSON фолбэкать на v1-поля (только для чтения старых файлов):

```js
const buIds = eq.links.business_unit_ids
  || (eq.links.business_unit_id ? [eq.links.business_unit_id] : []);
const cadIds = eq.links.cadastre_ids
  || (eq.links.cadastre_id ? [eq.links.cadastre_id] : []);
```

**На стороне парсера:** в `merge_preserve_confirmed` стоит добавить alias-таблицу для BU (планируется отдельным PR — пока не реализовано).

---

## 5. Прочие улучшения (не ломающие)

| Что | Где |
|---|---|
| Период: год (`за 2026 г.`) и диапазон дат (`за DD.MM.YYYY-DD.MM.YYYY`), не только квартал | `_parse_period` |
| Этажность учитывает поля `Количество этажей (в том числе подземных)`, `floors_above_ground`, `underground_floors` | `compute_levels_for_cadastre` |
| `_lease_key` срезает кадастровые хвосты → лучше матчит 01.К ↔ 01.03 | `_lease_key` |
| `area` распознаёт `Площадь, кв.м` / `Площадь общая` / `Площадь уточненная` / `Площадь` | `build_cadastre_objects` |
| `merge_preserve_confirmed` включает секцию `photos` | — |
| `auto_link_levels_and_premises`: если у привязанного кадастра ровно 1 уровень → equipment получает `level_ids=[этот]`; если объект — Помещение → `premises_ids=[этот]` + `location_kind="premises"` | `auto_link_levels_and_premises` |
| `generate_folder_structure` — генератор папок для фото на диске (`01_Земельные_участки/…/План_объекта/`, `06_Бизнес-единицы/`, `07_Оборудование/`); идемпотентный | — |
| Сохраняем `confirmed=true` BU/equipment/photos из старой структуры; `USER_EDITABLE_FIELDS = ("name", "links", "address", "confirmed", "photo_paths")` | `merge_preserve_confirmed` |

---

## 6. Совместимость с другими модулями

- **`pirushin_sosn_rocha_07_init_project_v1.py`** — потребляет `cadastre_objects[]`, `business_units[]`, `equipment[]`. Должен принять multi-links без изменений (читает только id-ссылки), но `cadastrals` у BU теперь может быть пустым → стоит фолбэкать на `anchor_cadastral`.
- **`pirushin_sosn_rocha_08_build_kmz_v2.py`** — уже использует `z_meters`, `height_m`, `_geometry.extrude`. **Совместим**.
- **`pirushin_sosn_rocha_052_v1.py`** — остаётся как history. Не удаляем.

---

## 7. Чеклист для команды viewer

- [ ] Перейти на чтение `equipment.links.*_ids[]` (с fallback на скаляры v1)
- [ ] Поддержать секцию `photos[]` (отрисовка по координатам/привязке)
- [ ] Использовать `z_meters` / `top_z_meters` для 3D-отображения уровней
- [ ] Учесть, что BU могут иметь `external_ids.enrich_bu_key` — это primary ID при cross-link с графом
- [ ] Папка `00_Нераспределенные/` — отображать отдельной категорией без высот
- [ ] План модификаций фронта согласовать с разделом 1 (BREAKING)

---

## 8. Что сейчас в git

- v1 (история): `pirushin_sosn_rocha_052_make_structure_v1.py` — не трогаем.
- **v2 (актуально): `pirushin_sosn_rocha_052_make_structure_v2.py` — запушен этим же коммитом.**
- Эта спека: `docs/CHANGELOG_052_v1_to_v2.md` — обновляется через PR.
