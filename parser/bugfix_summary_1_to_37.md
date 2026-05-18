# Журнал изменений egrn_parser v1.10
## bugfix_summary_1_to_37.md

Каждое изменение — отдельная секция «CHANGE N».

---

## CHANGE 1 — Инициализация пакета v1.10

**Запрос:** Создать Python-пакет `egrn_parser` по ТЗ v1.10.

**Реализация:**
- Создан полный скелет: `__init__.py`, `__main__.py`, `cli.py`, `api.py`, `config.py`
- Схема БД: 22 таблицы в `db/schema.sql`
- Утилиты: `colored_output`, `filename_filter`, `personal_data_filter`, `encoding`

---

## CHANGE 2 — Инициализация pyproject.toml

**Запрос:** Создать `pyproject.toml` для установки.

**Симптом (регрессия):** `Cannot import 'setuptools.backends.legacy'` на Windows 10.

**Причина:** Использован экспериментальный build-backend `setuptools.backends.legacy:build`, недоступный через pip.

**Реализация:** Заменён на стандартный `setuptools.build_meta`.

---

## CHANGE 3 — Мусорная папка в архиве ZIP

**Симптом:** После распаковки появлялась папка `{db,parsers,enrichers,...}` с буквальным именем из bash brace expansion.

**Причина:** `mkdir -p` создал папку с именем, содержащим скобки.

**Реализация:** Папка удалена; архив пересобран как `.zip` без `{...}` папок.

---

## CHANGE 4 — Полный парсер PDF (pdf_parser.py)

**Запрос:** Парсинг всех типов объектов ЕГРН из PDF-выписок.

**Реализация:**
- `OBJ_TYPE_RE` — определение типа объекта
- `_parse_section1_land`, `_parse_section1_building`, `_parse_section1_room`, `_parse_section1_structure`
- `_extract_right_blocks`, `_parse_one_right_block`, `_parse_one_encumbrance_block`
- Заголовок выписки: номер, дата, орган

---

## CHANGE 5 — Полный парсер XML (xml_parser.py)

**Запрос:** Парсинг XML-выписок из Росреестра.

**Симптом (регрессия):** `bool(elem)=False` для листовых ET-элементов при использовании `or`.

**Причина:** `ET.Element.__bool__` возвращает `False` если у элемента нет дочерних элементов, даже при наличии текстового содержимого.

**Реализация:**
- Все `elem_a or elem_b` заменены на `if elem_a is None: elem_a = elem_b`
- `_parse_land_params`: category, area+inaccuracy, permitted_uses
- `_parse_xml_restrict_record`: полный парсинг restrict_record с типом, датой, документом

---

## CHANGE 6 — Парсер ОСВ (osv_parser.py)

**Запрос:** Парсинг ОСВ 1С по счёту 01.

**Реализация:**
- 01.01 → право собственности; 01.К → аренда
- Аннуализация начального остатка; `extract_cad_from_name`, `extract_inventory_number`

---

## CHANGE 7 — Интерактивный diff (Fix 7.6)

**Запрос:** При выборе «обогатить» с несколькими изменёнными полями показывать вопрос по каждому.

**Реализация:** `ask_enrich_fields()` в `merge/interactive.py` — диалог X из Y.

---

## CHANGE 8 — old_numbers plain text (Fix 8)

**Симптом:** `old_numbers` сохранялось как `[{"type": "old", "number": "..."}]`.

**Причина:** Избыточная JSON-сериализация для простого текстового поля.

**Реализация:** `old_numbers = ' '.join(old_raw.split())` + постобработка дефисов-артефактов pdfplumber.

---

## CHANGE 9 — lifecycle_status_text очистка (Fix 9)

**Симптом:** `lifecycle_status_text = "Сведения об объекте недвижимости имеют статус «актуальные»"`.

**Реализация:** `_clean_status_text()` в pdf_parser.py и xml_parser.py; удаляет системный префикс.

---

## CHANGE 10 — Структуры main_char (Fix 10)

**Запрос:** Сооружения: показывать тип/значение/единицу измерения основной характеристики.

**Реализация:** Поля `main_char_type`, `main_value`, `main_unit` добавлены в BLDG_EXT_COLS XLSX и строку данных.

---

## CHANGE 11 — land_objects.area проверка (Fix 11)

**Запрос:** Убедиться что `area` и `area_error` заполняются для ЗУ.

**Реализация:** В XML-парсере добавлена читка `<area/value>` и `<inaccuracy>`.

---

## CHANGE 12 — object_restrictions фильтр ложноположительных (Fix 12)

**Симптом:** `object_restrictions` содержит `"данные отсутствуют"` и `"Сведения, необходимые для заполнения раздела"`.

**Причина:** Fallback-стратегия парсила «Особые отметки» без фильтрации системных сообщений.

**Реализация:** Фильтр `_FALSE_POSITIVE_PATTERNS` в `_parse_object_restrictions`.

---

## CHANGE 13 — Папка вывода (Fix 13)

**Запрос:** Создавать папку output рядом с источником; спрашивать пользователя.

**Реализация:** `_find_or_create_output_dir()` — 3 варианта с интерактивным выбором (Enter=рядом с источником).

---

## CHANGE 14 — Лист «Контакты» (Fix 14)

**Запрос:** Добавить лист «Контакты» в XLSX с предзаполненными строками.

**Реализация:** Таблица `contacts` в schema.sql; 15-й лист `_export_contacts()` в xlsx_exporter.py.

---

## CHANGE 15 — Нормализация правообладателей (Fix 15)

**Запрос:** Дедупликация, нормализация ООО/АО в листе «Правообладатели».

**Реализация:** `_normalize_holder_name()`, `_shorten_org_form()` в xlsx_exporter.py; дедупликация по `(INN, normalized_name)`.

---

## CHANGE 16 — «Наименование по бух.учету» из ОСВ (Fix 16)

**Запрос:** Заполнять «Наименование по бух.учету» из ОСВ в листах 1–2.

**Реализация:** SQL-подзапрос `accessories.item_name` в SQL для land и building.

---

## CHANGE 17 — Права: правообладатель + ИНН + доля (Fix 17)

**Запрос:** На листе «Права» показывать правообладателя, ИНН, долю; при Собственности → 1/1.

**Реализация:** Обновлён `_export_rights()`: headers + row с holder_name, holder_inn, share_str.

---

## CHANGE 18 — Бизнес-единицы: INN, KPP (Fix 18)

**Запрос:** Добавить ИНН и КПП в лист «Бизнес-единицы».

**Реализация:** Поля `entity_inn`, `entity_kpp` в schema.sql + лист.

---

## CHANGE 19 — Обновление ТЗ и промпта разработчика

**Реализация:** `DEVELOPER_PROMPT.md` — полный чек-лист с отметками ✅.

---

## CHANGE 20 — land_objects.area + area_error (Fix 20)

**Запрос:** Проставлять площадь и погрешность из «248 +/- 6».

**Реализация:** XML: `_parse_land_params` читает `<area/value>` и `<inaccuracy>`; PDF: `area_error` из паттерна `\d+ \+/- \d+`.

---

## CHANGE 21 — land_cad_numbers plain text + интерактивный выбор папки (Fix 21)

**Запрос:** `land_cad_numbers` без JSON; интерактивный выбор папки вывода.

**Реализация:**
- `land_cad_numbers` → plain text через `"; ".join()`
- Интерактивный выбор: 3 варианта + Enter=по умолчанию

---

## CHANGE 22 — land_cad_numbers для зданий через поиск строк «пределах» (Fix 22)

**Симптом:** `land_cad_numbers=None` для здания, хотя в PDF есть «в пределах 90:25:020102:119».

**Причина:** pdfplumber склеивает длинный заголовок таблицы с значением в одну строку; `_extract_field` не находит разорванный заголовок.

**Реализация:** Поиск всех строк содержащих «пределах» вместо поля-заголовка.

---

## CHANGE 23 — Стиль заголовка XLSX (Fix 23)

**Запрос:** Строка 2: Calibri 9pt bold, #0D0D0D, #CCFFCC, center+center, wrap=True.

**Реализация:** `HEADER_FILL`, `HEADER_FONT`, `HEADER_ALIGN` в xlsx_exporter.py.

---

## CHANGE 24 — Таблица photos (Fix 24)

**Запрос:** Добавить таблицу photos в БД и лист «Фото» в XLSX.

**Реализация:** `CREATE TABLE photos` в schema.sql; 16-й лист `_export_photos()`.

---

## CHANGE 25 — entity_registry заполнение (Fix 25)

**Запрос:** При сохранении правообладателей заполнять `entity_registry`.

**Реализация:** `upsert_right_holder` создаёт/обновляет запись в entity_registry при наличии ИНН.

---

## CHANGE 26 — XML: category, area, permitted_uses (Fix 26)

**Запрос:** Парсить из XML `land_category`, `area+area_error`, `permitted_uses`.

**Реализация:**
- `land_category` из `<category/type/value>`
- `area` + `area_error` из `<area/value>` + `<inaccuracy>`
- `permitted_uses` из `<permitted_use_established/by_document>`

---

## CHANGE 27 — XML: object_restrictions + rights (Fix 27)

**Запрос:** Парсить из XML `special_notes`, `restrictions_encumbrances`, `right_holders`.

**Реализация:**
- `_parse_xml_object_restrictions`: все `<restriction_encumbrance>` + `<special_notes>`
- `_parse_xml_restrict_record`: полный парсинг `restrict_record` (тип, дата, документ-основание)
- `_parse_xml_holder`: публичный субъект из `<public_formation>`
- Share: `<numerator>/<denominator>` вместо `parse_share()`

---

## CHANGE 28 — ET boolean bug + проверка FK (Fix 28)

**Симптом:** `right_number=None` для всех прав в XML; `bool(elem)=False` для листовых элементов.

**Причина:** Оператор `or` на ET-элементе использует `bool(elem)`, который возвращает `False` для элементов без дочерних (но с текстом).

**Реализация:** Все `elem_a or elem_b` → `if elem_a is None: elem_a = elem_b` во всём xml_parser.py.

---

## CHANGE 29 — Права: date format + source_file (Fix 29)

**Запрос:** Дата регистрации в формате «20.12.2016 21:18:49»; колонка файл-источник.

**Реализация:** `_fmt_date()` в xlsx_exporter.py; заголовок «Файл-источник» + `source_extract_number` в строке.

---

## CHANGE 30 — Обременения: дубли и beneficiary (Fix 30)

**Симптом:**
- Аренда дублируется вместо обогащения
- beneficiary содержит «прав и обременение объекта недвижимости: 9103015220»

**Причина:** beneficiary-regex не обрабатывал случай когда pdfplumber разрывает строку «лицо, в пользу которого...» на две части.

**Реализация:** DOTALL-regex с очисткой артефактов системного префикса второй строки.

---

## CHANGE 31 — ООО нормализация (Fix 31)

**Запрос:** «Общество с ограниченной ответственностью» → «ООО».

**Реализация:** `_normalize_org_name()` в pdf_parser.py; вызывается при очистке beneficiary_name и в xlsx_exporter.py `_shorten_org_form()`.

---

## CHANGE 32 — Файл-источник в листах XLSX (Fix 32)

**Запрос:** Добавить колонку «Файл-источник» на листах ЗУ, Здания, Помещения, ОНС, Обременения, Ограничения, Принадлежности.

**Реализация:** Добавлена колонка в LAND_EXT_COLS, BLDG_EXT_COLS и в строки данных всех перечисленных листов.

---

## CHANGE 33 — ЗУ: Площадь и Собственник (Fix 33)

**Запрос:** На листе «Земельные участки» заполнять «Площадь, кв.м» и «Собственник».

**Реализация:** SQL-подзапросы `owner_name` (через rights → right_holders) + `r.get("area")` уже были — убеждено что передаются в нужные позиции.

---

## CHANGE 34 — Здания: поле «Значение» между Типом и Ед. изм. (Fix 34)

**Запрос:** Добавить `main_value` между «Тип осн. хар-ки» и «Ед. измерения».

**Реализация:** Добавлена колонка «Значение осн. хар-ки» (AW) в BLDG_EXT_COLS и строку данных.

---

## CHANGE 35 — Помещения и ОНС: Инв. №, Наименование по бух. учёту (Fix 35)

**Запрос:** Вставить «Инв. №» и «Наименование по бух.учету» перед кадастровым номером; переименовать «Наименование» → «Наименование по выписке из ЕГРН».

**Реализация:** Обновлены `_export_rooms()` и ОНС-блок в `export_xlsx()`: новые заголовки, SQL + строки.

---

## CHANGE 36 — Нормализация схемы БД (Fix 36)

**Запрос:** Предложение по минимизации дублирования данных в БД.

**Реализация:** Документ `DB_NORMALIZATION.md` с:
- Описанием текущих избыточностей
- Реализованными изменениями (plain text вместо JSON, entity_registry)
- Рекомендациями для v1.11 (object_restriction_records, типизированные FK)

---

## CHANGE 37 — SQL views для досье объекта (Fix 37)

**Запрос:** Создать SQL-представления для воссоздания досье.

**Реализация:**
- `v_all_objects` — ЗУ + ОКС в одной таблице
- `v_rights_full` — права с правообладателями
- `v_lease_contracts` — договоры аренды
- `v_object_dossier` — сводное досье (owner, encumbrances, last_extract)
- `v_pledges_prohibitions` — ипотеки/запреты

Скрипт: `egrn_parser/scripts/dossier.py`

```bash
python -m egrn_parser.scripts.dossier --db output/egrn.db --cad 90:25:020102:24
python -m egrn_parser.scripts.dossier --db output/egrn.db --cad 90:25:020102:24 --format xlsx
```

---

## Итоговый статус тестов

| Метрика | Значение |
|---------|---------|
| Тестов | 31 |
| Проходит | 31 |
| Падает | 0 |
| Форматов вывода | XLSX (16 листов), JSON, graph.json v1.1 |
| Форматов входных | PDF, XML, ОСВ xlsx, Справка docx, Перечень docx |
