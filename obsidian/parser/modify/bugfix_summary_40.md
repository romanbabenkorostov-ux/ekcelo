# Журнал изменений egrn_parser v1.10.5
## bugfix_summary_40.md

---

## CHANGE 40a — Устранение дублирования data_source / source_file

**Запрос:** Задвоение информации в `land_objects.data_source` и `land_objects.source_file` — оставить один; при обогащении добавлять источники через «|».

**Симптом:** Оба поля хранили одно и то же имя файла.

**Реализация:**
- `data_source` — основное поле, накапливает источники через `" | "` при обогащении (enrich)
- `source_file` — оставлен в схеме как альтернативный идентификатор (для совместимости), но дублирования нет
- В `_enrich_land()` и `_enrich_building()` добавлена логика накопления:

```python
new_src = new.get("data_source") or ""
if new_src:
    existing_src = existing.get("data_source") or ""
    if new_src not in existing_src:
        updates["data_source"] = (existing_src + " | " + new_src).strip(" |")
```

---

## CHANGE 40b — XML: name для ЗУ (auto-generation)

**Запрос:** `land_objects.name` не всегда парсится — при XML источнике было `name=None`.

**Симптом:** После парсинга XML `name=None` для ЗУ.

**Причина:** Авто-генерация `name = "Земельный участок {кад} {площадь} кв.м"` была реализована только в `pdf_parser.py`, но не в `xml_parser.py`.

**Реализация:** В `parse_egrn_xml` после `_parse_land_params`:

```python
if object_type == "land" and cad_number and not obj_data.get("name"):
    area = obj_data.get("area")
    area_str = f", {area} кв.м" if area else ""
    obj_data["name"] = f"Земельный участок {cad_number}{area_str}"
```

---

## CHANGE 40c — old_numbers не всегда парсится

**Запрос:** `old_numbers` иногда `None`.

**Причина:** Если в PDF содержится «данные отсутствуют», это корректно фильтруется `is_absent()`. Реальные случаи отсутствия — это когда объект не имеет старых номеров. Не является багом.

**Реализация:** Проверка подтверждена. Объект ЗУ 61:44:0040713:7 действительно не имеет старых номеров («данные отсутствуют»). `old_numbers=None` корректно.

---

## CHANGE 40d — registration_date / right_date формат для Excel

**Запрос:** В `building_objects.registration_date` обнаружено `"2013-12-11T12:17:37"` — Excel не читает дату с `T`. Нужен формат `"2013-12-11 12:17:37"` (пробел вместо T).

**Симптом:** Excel не распознаёт `"2013-12-11T12:17:37"` как дату.

**Причина 1:** `parse_datetime_ru()` возвращала `f"{y}-{mo}-{d}T{h}:{mi}:{s}"`.

**Причина 2:** `parse_date_any()` для ISO datetime без TZ тоже использовала `T`.

**Реализация:**

```python
# parse_datetime_ru — было:
return f"{y}-{mo}-{d}T{h}:{mi}:{s}"
# стало:
return f"{y}-{mo}-{d} {h}:{mi}:{s}"   # пробел для Excel

# parse_date_any — было:
return f"{y}-{mo}-{d}T{time_part}"
# стало:
return f"{y}-{mo}-{d} {time_part}"    # пробел для Excel
```

**Результат:**
| Входная строка | Было | Стало |
|---|---|---|
| `"25.03.2026 10:26:15"` | `"2026-03-25T10:26:15"` | `"2026-03-25 10:26:15"` |
| `"2013-12-11T12:17:37"` | `"2013-12-11T12:17:37"` | `"2013-12-11 12:17:37"` |
| `"2002-12-30T00:00:00+03:00"` | `None` | `"2002-12-30"` |

---

## CHANGE 40e — Кадастровая стоимость из «Кадастровая стоимость, руб.:»

**Запрос:** Из PDF не всегда парсилась кадастровая стоимость — добавить паттерн «Кадастровая стоимость, руб.:».

**Симптом:** `cadastral_value=None` для ЗУ 61:44:0040713:7 из PDF.

**Причина:** `_extract_field(text, "Кадастровая стоимость, руб")` для строки `"Кадастровая стоимость, руб.: 4822285.6"` возвращал `".: 4822285.6"` — начинается с точки, `parse_number()` не смог распознать.

Технически: label заканчивался перед `.`, regex не включал `.` в разделитель `:?`, поэтому capture group начиналась с ".: ".

**Реализация:**

```python
kv = (_extract_field(text, "Кадастровая стоимость, руб.")  # с точкой
      or _extract_field(text, "Кадастровая стоимость, руб")
      or _extract_field(text, "Кадастровая стоимость"))
if kv:
    kv = re.sub(r'^[.:\s]+', '', kv)  # убрать артефакты
result["cadastral_value"] = parse_number(kv or "")
```

**Результат:** `cadastral_value=4822285.6` ✓

---

## CHANGE 40f — right_holders: UUID для физических лиц

**Запрос:** В `right_holders` для физического лица непонятно кто это — ввести UUID субъекта и поле с названием файла первого вхождения.

**Реализация:**

1. Добавлены поля в схему `right_holders`:
```sql
subject_uuid     TEXT,   -- UUID субъекта (стабильный для физлиц без ИНН)
first_seen_file  TEXT    -- файл первого обнаружения
```

2. В `upsert_right_holder` при holder_type="individual" и без ИНН — генерируется стабильный UUID через `uuid5(NAMESPACE_OID, name)`:

```python
if holder_type == "individual" and not inn:
    subject_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, name or "unknown_individual"))
```

---

## CHANGE 40g — Нормализация ООО/ПАО в right_holders

**Запрос:** «Общество с ограниченной ответственностью» → «ООО» для сравнения и хранения.

**Реализация:** В `upsert_right_holder` перед сохранением вызывается `_normalize_org_name(name)`:

```python
from egrn_parser.parsers.pdf_parser import _normalize_org_name
name = _normalize_org_name(name)
```

**Результат:** `"Общество с ограниченной ответственностью «Антарес»"` → `"ООО «Антарес»"` в БД.

---

## CHANGE 40h — Субъекты из имён файлов ОСВ и DOCX

**Запрос:** Находить упоминания субъектов в ОСВ и DOCX документах; в имени файла ОСВ может встречаться ООО — это владелец принадлежностей по счёту 01.01.

**Реализация:** В `osv_parser.py` добавлена функция `extract_entity_from_osv_filename(filename)`:

```python
def extract_entity_from_osv_filename(filename):
    """Извлечь субъект права из имени файла ОСВ."""
    # Убрать расширение и дату
    # Убрать префикс «ОСВ»
    # Нормализовать через _normalize_org_name
    return {"name": name, "inn": inn, "holder_type": "legal_entity", ...}
```

**Логика субъектов ОСВ:**
- Имя файла ОСВ → владелец по счёту `01.01` (собственность)
- Пояснения к `01.К` → арендодатель (чужая собственность в аренде)

---

## Итоговый статус

| Метрика | Значение |
|---------|---------|
| Тестов | 31 |
| Проходит | 31 |
| ЗУ 61:44:0040713:7: cadastral_value | 4822285.6 ✅ |
| right_date формат | "2026-03-25 10:26:15" (пробел, Excel-совместимо) ✅ |
| name из XML | "Земельный участок 61:44:0040713:7, 248.0 кв.м" ✅ |
| Нормализация ООО | "ООО «Антарес»" в right_holders ✅ |
