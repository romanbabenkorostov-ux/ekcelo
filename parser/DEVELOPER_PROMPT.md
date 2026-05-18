# Промпт для разработчика парсера ЕГРН  
# ТЗ v1.10.2 — актуальная редакция  
# Единственный источник истины: ТЗ_парсинг_выписок_ЕГРН_v1_10.md

---

## Роль

Ты — senior Python-инженер, разрабатывающий систему `egrn_parser v1.10`.  
Ты читаешь только ТЗ v1.10 и файлы пакета в `/egrn_parser/`.  
Старые скрипты `pirushin_sosn_rocha_*.py` — только справочно, не переиспользуются.

---

## Жёсткие запреты (никогда не нарушать)

| Правило | Источник |
|---------|---------|
| Поле «Сведения о возможности предоставления третьим лицам персональных данных физического лица» **никогда** не сохраняется ни в одном выходном формате | ТЗ 4.5, Приложение A |
| Листы 1–2 XLSX-шаблона (A–U / A–AC) **не изменяются** | ТЗ 11.2 |
| DOCX-фотоотчёты **исключаются** из источников данных | ТЗ 4.1 |
| `right_category` = `'right'` / `'encumbrance'` / `'restriction'` — **никакой склейки** через `' | '` | ТЗ 5.4 |
| Единственный канал в веб-подсистему Block 2 — `graph.json v1.1` | ТЗ 11.4 |

---

## Архитектура пакета

```
egrn_parser/
├── parsers/       pdf_parser, xml_parser, osv_parser, docx_parser,
│                 spravka_parser, xlsx_template_parser, _common
├── enrichers/    room_parent_resolver, geometry_extractor, ownership_resolver
├── merge/        content_hash, differ, interactive, upsert, cad_resolver
├── exporters/    xlsx_exporter (15 листов), json_exporter, graph_json
├── monitoring/   runner, change_detector
├── db/           schema.sql, connection, migrations, seeds
└── utils/        encoding, colored_output, filename_filter, personal_data_filter
```

---

## Чек-лист выполненных пунктов ТЗ

### Парсинг (Раздел 5-8 ТЗ)

| Пункт | Описание | Статус |
|-------|----------|--------|
| 4.1 | DOCX-фотоотчёты отфильтрованы | ✅ |
| 4.4 | Все типы ОН: ЗУ, Здание, Сооружение, Помещение, ММ, ОНС | ✅ |
| 4.4 | ОНС: `area`, `construction_stage`, `purpose`, `land_cad_numbers` | ✅ |
| 4.4 | Сооружение: `main_char_type` / `main_value` / `main_unit` | ✅ |
| 4.5 | Фильтр персональных данных до записи в БД | ✅ |
| 5.4 | `name` извлекается только **после первого вхождения кад. номера** в тексте | ✅ |
| 5.4 | ЗУ: авто-генерация name = `"Земельный участок {кад.номер}, {площадь} кв.м"` | ✅ |
| 5.4 | `old_numbers` = plain text (не JSON), склейка разорванных строк | ✅ |
| 5.4 | `lifecycle_status_text` без префикса «Сведения об объекте недвижимости имеют статус» | ✅ |
| 5.4 | `object_restrictions`: мульти-страничный парсинг ЗОУИТ/ОКН по `реестровым номером` | ✅ |
| 5.4 | `object_restrictions`: фильтр ложноположительных («данные отсутствуют», «Сведения, необходимые») | ✅ |
| 5.4 | `floors_total` санитарная проверка `< 200` (иначе — год постройки) | ✅ |
| 5.4 | `area_error` для ЗУ из «248 +/- 6» | ✅ |
| 5.4 | `land_cad_numbers` через поиск по строкам «пределах» (горизонтальное склеивание pdfplumber) | ✅ |
| 6 | XML-парсер: все типы ОН, пропуск personal_data_* тегов | ✅ |
| 8 | ОСВ 1С: 01.01 → собственность, 01.К → аренда; аннуализация lease_annual | ✅ |
| 8.3 | Частичные кад. номера `:119`: интерактивная привязка с поиском в БД | ✅ |
| 8.5 | Справка по юридическим вопросам DOCX: аренды ЗУ → `rights`, статусы ОКС | ✅ |
| 8.6 | Перечень имущества DOCX: сроки аренды ЗУ, этажность/год зданий | ✅ |

### Хранение (Раздел 9 ТЗ)

| Пункт | Описание | Статус |
|-------|----------|--------|
| 9.1 | `land_objects`: все поля включая `name`, `area`, `object_restrictions` (JSON) | ✅ |
| 9.2 | `building_objects`: `floors_total/above_ground/underground`, `main_char_type/value/unit`, `construction_stage` | ✅ |
| 9.12 | Идемпотентность: `(extract_number, content_hash)`, второй проход → `skipped=1` | ✅ |
| 9.12 | `right_category` ∈ `{right, encumbrance, restriction}` | ✅ |
| 9.12 | `object_restrictions` хранится как JSON-массив в `land_objects/building_objects` | ✅ |

### Обогащение (Раздел 7 ТЗ)

| Пункт | Описание | Статус |
|-------|----------|--------|
| 7.5 | `resolve_room_parent()`: этажность из здания → помещению | ✅ |
| 7.6 | Интерактивный diff: диалог по каждому изменённому полю (X из Y) | ✅ |
| 7.6 | При enrich с несколькими полями → `ask_enrich_fields()` | ✅ |

### Экспорт (Раздел 11 ТЗ)

| Пункт | Описание | Статус |
|-------|----------|--------|
| 11.2 | XLSX 15 листов: 1–2 расширяются справа от шаблона A–U/A–AC | ✅ |
| 11.2 | Лист «Контакты»: роль / заказчик / исполнитель / договор | ✅ (листов 15) |
| 11.2 | Лист «Правообладатели»: дедупликация, нормализация ООО/ОАО/АО | ✅ |
| 11.2 | Лист «Права»: правообладатель, ИНН, доля (при Собственности без доли → 1/1) | ✅ |
| 11.2 | Лист «Бизнес-единицы»: поля INN, KPP | ✅ |
| 11.2 | «Наименование по бух.учету» из ОСВ (`accessories.item_name`) | ✅ |
| 11.2 | Сооружение: `main_char_type`, `main_unit` в листе 2 | ✅ |
| 11.3 | JSON-экспорт всех таблиц без `code_dictionary` | ✅ |
| 11.4 | `graph.json v1.1`: `schemaVersion`, `nodes`, `edges`, `groups`, `metadata` | ✅ |
| 11.4 | `graph.json`: `objectRestrictions[]`, `floorsAboveGround`, `undergroundFloors` | ✅ |

### CLI (Раздел 13 ТЗ)

| Пункт | Описание | Статус |
|-------|----------|--------|
| 13.1 | Команды: parse, export, migrate, dict-load, validate, enrich, monitor, serve, folders | ✅ |
| 13.3 | Интерактивный режим: вопросы на русском `[д/н]`, Enter=н | ✅ |
| 13.3 | Интерактивный режим: папка `output` создаётся рядом с источником | ✅ |
| 13.3 | Идемпотентность: находит ранее созданные БД/XLSX в папке вывода | ✅ |

---

## Ключевые алгоритмы

### Определение типа объекта (pdf_parser)
```python
OBJ_TYPE_RE = re.compile(
    r"(Земельный участок|Помещение|Здание|Сооружение|Машино-место|"
    r"Объект незаверш[её]нного строительства)"   # ← character class [её] обязателен
    r"[\s\r\n]+вид объекта",
    re.IGNORECASE,
)
```

### Безопасное извлечение наименования
```python
def _extract_name_safe(text, cad_number):
    """Ищет 'Наименование:' ТОЛЬКО после первого вхождения кад. номера."""
    pos = text.find(cad_number)
    ...
    m = re.search(r"(?m)^Наименование\s*:\s*(.+?)$", text[pos:], re.IGNORECASE)
```

### ЗОУИТ из многостраничных выписок
```python
# Поиск по реестровым номерам (не по тексту-метке)
BLOCK_RE = re.compile(
    "(?:полностью расположен)[^\\n]*реестровым номером\\s+([\\d:.\\-/]+)", IGNORECASE
)
# Fallback: «Особые отметки» (ст. 56 ЗК) — с фильтром ложноположительных
```

### `old_numbers` — plain text (не JSON)
```python
obj_data["old_numbers"] = ' '.join(old_raw.split())
# + re.sub(r'(\d+)- (\d)', r'\1-\2', ...) для склейки артефактов pdfplumber
```

### `lifecycle_status_text` — без системного префикса
```python
def _clean_status_text(raw):
    return re.sub(r'^Сведения об объекте недвижимости имеют статус\s*["«]?\s*',
                  '', raw, re.IGNORECASE).strip('"»')
```

---

## Выходные форматы

### XLSX (15 листов)

| № | Лист | Ключевые поля v1.10.2 |
|---|------|-----------------------|
| 1 | Земельные участки | A–U шаблон + V–AH + name_accounting из ОСВ |
| 2 | Здания, сооружения | A–AC шаблон + AD–AW + main_char_type, main_unit |
| 3 | Помещения и машино-места | parent_floors_above_ground, parent_underground_floors |
| 4 | ОНС | construction_stage |
| 5 | Принадлежности и оборудование | lat/lon + lat2/lon2 + geom_polyline |
| 6 | Бизнес-единицы | INN, KPP |
| 7 | Права | Правообладатель, ИНН, доля (при Собственности без доли → 1/1) |
| 8 | Обременения | beneficiary_name, beneficiary_inn |
| 9 | Ограничения | object_restrictions[] + rights(restriction) |
| 10 | Правообладатели | дедупликация, нормализация (ООО → ООО, хэш для физлиц) |
| 11 | События объектов | — |
| 12 | События прав | — |
| 13 | Оценка стоимости | — |
| 14 | Словарь кодов | — |
| 15 | Контакты | Роль / Заказчик / Исполнитель / Договор / Акт |

### Схема БД (ключевые изменения v1.10.2)
- `land_objects.name` — авто-генерируется парсером
- `land_objects.old_numbers` — TEXT (plain text, не JSON)
- `building_objects.construction_stage` — % готовности ОНС
- `business_units.entity_inn`, `.entity_kpp` — поля для ИНН/КПП
- `contacts` — новая таблица (15-й лист XLSX)

---

## Тестирование

```bash
# Запуск 31 теста
python -m pytest tests/ -v

# Интеграционный тест двух проходов
python -m egrn_parser parse --input ./выписки --db ./output/egrn.db
python -m egrn_parser parse --input ./выписки --db ./output/egrn.db  # должен: skipped=N
python -m egrn_parser export --db ./output/egrn.db
```

### Что проверять при тестировании (чек-лист ТЗ 17.2)

- [ ] ОНС парсится как `object_type='ons'`, `area` заполнена, `lifecycle_status_text` без префикса
- [ ] ЗУ 61:44:0040713:7: `object_restrictions` содержит 4 зоны с реестровыми номерами
- [ ] Сооружение: `main_char_type`, `main_value`, `main_unit` заполнены
- [ ] `old_numbers` — plain text без JSON-обёртки
- [ ] Второй проход — `skipped=1` для всех объектов
- [ ] XLSX содержит 15 листов, лист «Контакты» имеет 3 предзаполненные строки
- [ ] Персональные данные отсутствуют во всех выходных форматах


---

## Дополнения v1.10.3 (пункты 20–28)

### Новые пункты чек-листа

| # | Описание | Статус |
|---|----------|--------|
| 20 | `land_objects.area` + `area_error` из «248 +/- 6» | ✅ |
| 21 | `land_cad_numbers` — plain text «90:25:020102:119; 90:25:020102:124» | ✅ |
| 21 | Интерактивный выбор папки вывода с 3 вариантами (Enter=рядом с источником) | ✅ |
| 22 | `land_cad_numbers` для зданий через поиск строк «пределах» | ✅ |
| 22 | `right_number` — очищается от артефакта «права: » pdfplumber | ✅ |
| 23 | Заголовок строки 2: Calibri 9pt bold, #0D0D0D, #CCFFCC, center+center, wrap | ✅ |
| 24 | Таблица `photos` в БД + лист «Фото» в XLSX (16-й лист) | ✅ |
| 25 | `entity_registry` заполняется при сохранении правообладателей (ЮЛ с ИНН) | ✅ |
| 26 | XML: `land_category` из `<category/type/value>` | ✅ |
| 26 | XML: `area` + `area_error` из `<area/value>` + `<inaccuracy>` | ✅ |
| 26 | XML: `permitted_uses` из `<permitted_use_established/by_document>` | ✅ |
| 26 | XML: `lifecycle_status_text` без системного префикса | ✅ |
| 27 | XML: `object_restrictions` из `<restriction_encumbrance>` (все 7 зон для ЗУ) | ✅ |
| 27 | XML: `right_number` из `<right_data/right_number>` (Fix ET boolean bug) | ✅ |
| 27 | XML: `share_numerator/denominator` из `<share/numerator>/<denominator>` | ✅ |
| 27 | XML: Публичный субъект (Российская Федерация) из `<public_formation>` | ✅ |
| 27 | XML: `restrict_record` → полный парсинг с типом, датой, документом-основанием | ✅ |
| 28 | FK проверены: `rights` → `right_holders`, множественность прав на объект ✓ | ✅ |

### Критический баг: ET element boolean

Элементы Python `xml.etree.ElementTree` возвращают `False` при `bool(elem)` если не имеют дочерних элементов — даже при наличии текстового содержимого. Конструкция `elem_a or elem_b` вместо `elem_a is not None` вызывает потерю данных.

```python
# НЕВЕРНО — elem с текстом без дочерних → bool=False → теряем значение:
right_num_e = _find_recursive(rec, "right_number") or _find_recursive(rec, "number")

# ВЕРНО:
right_num_e = _find_recursive(rec, "right_number")
if right_num_e is None:
    right_num_e = _find_recursive(rec, "number")
```

Исправлено во всех вхождениях в `xml_parser.py`.

### Хранение форматов

| Поле | Старый формат | Новый формат |
|------|--------------|--------------|
| `land_cad_numbers` | `["90:25:...:119"]` JSON | `"90:25:...:119; 90:25:...:124"` plain text |
| `permitted_uses` | `["ВРИ"]` JSON | `"ВРИ"` plain text |
| `nested_objects` | JSON | plain text |
| `old_numbers` | `[{"type":"old","number":"..."}]` | plain text |

### Идемпотентность: PDF+XML для одного объекта

При обработке одного объекта из PDF и XML по очереди хэши различаются,
поэтому второй формат всегда «заменяет» первый. Это ожидаемое поведение.
Идемпотентность гарантируется для одинаковых файлов одного формата.
