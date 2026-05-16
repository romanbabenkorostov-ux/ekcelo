# Журнал изменений egrn_parser v1.10.4
## bugfix_summary_38_to_39.md

---

## CHANGE 38 — Парсинг building_objects: main_value, registration_date, old_numbers

### CHANGE 38a — Fallback main_value=area

**Запрос:** Если спарсилось `building_objects.area`, а в `main_value` нет данных, то это значение записывать в `main_value`, а `main_char_type="площадь"` и `main_unit="в квадратных метрах"`.

**Симптом:** ОНС (90:22:010701:510) парсился с `area=105.8`, но `main_value=None`, `main_char_type=None`, `main_unit=None`. В XLSX лист «Здания, сооружения» колонка «Значение осн. хар-ки» оставалась пустой.

**Причина:** Для ОНС тег «Основная характеристика объекта незавершённого строительства» в pdfplumber разбивался на 2 строки:
- строка 1: `"Основная характеристика объекта незавершенного тип значение единица измерения"`
- строка 2: `"строительства и ее проектируемое значение: площадь 105.8 в квадратных метрах"`

Существующий regex в `_parse_section1_structure` не рассчитан на этот разрыв. Area парсилась отдельным полем `"Площадь, м2: 105.8"`, но main_char остался незаполненным.

**Реализация:** В `merge/upsert.py::upsert_building_object` добавлена нормализация ПЕРЕД INSERT:

```python
# Fix 38a: если area есть, а main_value нет → заполнить основную характеристику из площади
if obj.get("area") and not obj.get("main_value"):
    obj.setdefault("main_char_type", "площадь")
    obj["main_value"] = obj["area"]
    obj.setdefault("main_unit", "в квадратных метрах")
```

**Результат:**
| Объект | До | После |
|--------|-----|-------|
| ОНС 90:22:010701:510 | `main_value=None` | `main_char=площадь, main_value=105.8, main_unit=в квадратных метрах` |
| Помещение 61:44:0040713:308 (из XML) | `main_value=None` | `main_char=площадь, main_value=30.9, main_unit=в квадратных метрах` |

---

### CHANGE 38b — registration_date из XML <record_info>

**Запрос:** Дату регистрации в XML читать из `<record_info><registration_date>2013-12-11T12:17:37+04:00</registration_date></record_info>`.

**Симптом:** `building_objects.registration_date=None` и `land_objects.registration_date=None` при парсинге XML-выписок.

**Причина 1:** В `_parse_common_data` использовался `_find_recursive(root, "registration_date")`, который искал первый попавшийся элемент с таким тегом. При большом XML с несколькими `right_record` мог попасть не тот элемент.

**Причина 2 (критическая):** `parse_date_any` не обрабатывала формат с timezone-offset "2002-12-30T00:00:00+03:00" → возвращала `None`.

**Реализация:**

1. Исправлен `parse_date_any` в `parsers/_common.py` — добавлена поддержка ISO datetime с timezone offset:

```python
iso_dt = re.match(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}:\d{2})(?:[+\-]\d{2}:\d{2}|Z)?",
    t
)
if iso_dt:
    y, mo, d, time_part = iso_dt.groups()
    if time_part != "00:00:00":
        return f"{y}-{mo}-{d}T{time_part}"
    return f"{y}-{mo}-{d}"
```

2. В `_parse_common_data` явно ищем `<record_info>` у текущей записи (не рекурсивно по всему дереву):

```python
record_info_e = _find(root, "record_info")
if record_info_e is None:
    for child in root:  # land_record, room_record, etc.
        if "record" in _tag(child):
            ri = _find(child, "record_info")
            if ri is not None:
                record_info_e = ri; break
```

**Результат:**
| Объект | До | После |
|--------|-----|-------|
| ЗУ 61:44:0040713:7 (XML) | `registration_date=None` | `registration_date=2002-12-30` |
| Помещение 61:44:0040713:308 (XML) | `registration_date=None` | `registration_date=2012-01-21` |

---

### CHANGE 38c — old_numbers из XML <old_numbers>

**Запрос:** Извлекать ранее присвоенные номера из XML-структуры:
```xml
<old_numbers>
  <old_number>
    <number_type><code>01</code><value>Инвентарный номер</value></number_type>
    <number>143/3</number>
  </old_number>
  <old_number>
    <number_type><code>02</code><value>Условный номер</value></number_type>
    <number>61:44:04 00 00:0000:143/3/АБФ:0/30107</number>
  </old_number>
</old_numbers>
```

**Симптом:** `old_numbers=None` для объектов с историческими номерами в XML.

**Причина:** В `_parse_common_data` не было кода для парсинга `<old_numbers>`.

**Реализация:** Добавлена функция `_parse_xml_old_numbers(root)` в `xml_parser.py`:

```python
def _parse_xml_old_numbers(root):
    old_ns = _find_recursive(root, "old_numbers")
    if old_ns is None:
        return None
    parts = []
    for old_num in old_ns:
        if _tag(old_num) != "old_number": continue
        type_e = _find(old_num, "number_type")
        num_e  = _find(old_num, "number")
        num_text = _text(num_e)
        if not num_text or is_absent(num_text): continue
        val_e = _find(type_e, "value") if type_e else None
        type_text = _text(val_e) if val_e else None
        part = f"{type_text} {num_text}".strip() if type_text else num_text
        if part and part not in parts:
            parts.append(part)
    return "; ".join(parts) if parts else None
```

**Результат:**
| Объект | До | После |
|--------|-----|-------|
| Помещение 61:44:0040713:308 | `old_numbers=None` | `old_numbers=Инвентарный номер 143/2; Условный номер 61-61-01/177/2006-124` |

---

## CHANGE 39 — Парсинг land_objects: name, area, registration_date

### CHANGE 39a — Автогенерация name для ЗУ

**Запрос:** Наименование ЗУ конструируется как `"Земельный участок {кад.номер} {площадь} кв.м"`.

**Реализация:** Уже было реализовано в предыдущей итерации (Fix 5.4 → Change 5). Автогенерация происходит в `pdf_parser.py::parse_egrn_pdf` после определения типа объекта `"land"`:

```python
if object_type == "land":
    obj_data.update(_parse_section1_land(sec1_text))
    area = obj_data.get("area")
    area_str = f", {area} кв.м" if area else ""
    obj_data["name"] = f"Земельный участок {cad_number}{area_str}"
```

Применяется как для PDF, так и в XML-парсере (в `parse_egrn_xml` после `_parse_land_params`).

**Результат:** `name=Земельный участок 61:44:0040713:7, 248.0 кв.м` ✓

---

### CHANGE 39b — area из XML <area/value>

**Запрос:** Площадь ЗУ из XML из `<area><type><value>Уточненная площадь</value></type><value>248</value><inaccuracy>6</inaccuracy></area>`.

**Реализация:** Уже было реализовано (Fix 26 → Change 26). В `_parse_land_params`:

```python
area_top = _find_recursive(root, "area")
if area_top is not None:
    val_e  = _find(area_top, "value")
    inac_e = _find(area_top, "inaccuracy")
    result["area"]       = parse_number(_text(val_e))
    result["area_error"] = parse_number(_text(inac_e))
```

**Результат:** `area=248.0 ±6.0` ✓

---

### CHANGE 39c — registration_date ЗУ из XML <record_info>

**Запрос:** `land_objects.registration_date` из `<record_info><registration_date>2002-12-30T00:00:00+03:00</registration_date></record_info>`.

**Симптом:** `registration_date=None` для ЗУ из XML.

**Причина:** Та же что в Change 38b — `parse_date_any` не обрабатывала timezone-offset.

**Реализация:** Решено вместе с Change 38b — единый `parse_date_any` и единый `_parse_common_data`.

**Результат:** `registration_date=2002-12-30` ✓

---

## Итоговая таблица проверок

| Поле | PDF работало | XML работало | После фиксов |
|------|-------------|-------------|-------------|
| `registration_date` (здания/ОКС) | ✅ | ❌ → ✅ | ✅ |
| `registration_date` (ЗУ) | ✅ | ❌ → ✅ | ✅ |
| `old_numbers` (PDF) | ✅ | — | ✅ |
| `old_numbers` (XML) | — | ❌ → ✅ | ✅ |
| `main_value` (сооружения с main_char) | ✅ | — | ✅ |
| `main_value` (ОНС/здания fallback) | ❌ → ✅ | ❌ → ✅ | ✅ |
| `area` (ЗУ) | ✅ | ✅ | ✅ |
| `area_error` (ЗУ) | ✅ | ✅ | ✅ |
| `land_category` | ✅ | ✅ | ✅ |
| `permitted_uses` | ✅ | ✅ | ✅ |
| `land.name` (автогенерация) | ✅ | ✅ | ✅ |

## Статус тестов: 31/31 ✅
