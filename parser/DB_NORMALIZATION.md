# Предложение по нормализации схемы БД (Пункт 36)
# egrn_parser v1.10 — минимизация дублирования данных

## Текущие избыточности

| Проблема | Таблицы | Потеря |
|---------|---------|--------|
| `right_holders.name` дублирует `entity_registry.name_full` | rights → right_holders → entity_registry | Обновление имени в двух местах |
| `rights.object_key_value` (cad_number) — текстовый FK вместо INTEGER | rights, accessories, valuations | Нет индексной проверки целостности |
| `valuations.cad_number` может указывать на ЗУ или ОКС | valuations | Нет типизированного FK |
| `object_events`, `right_events` — дублируют cad_number из родительских таблиц | — | Избыточно при JOIN |
| `extracts.cad_number` дублируется с land/building_objects | — | При переименовании обновлять везде |

## Реализованные изменения нормализации

### 1. Консолидация `right_holders` → `entity_registry`

В `upsert_right_holder` при сохранении правообладателя с ИНН
автоматически создаётся/обновляется запись в `entity_registry`.
Теперь `right_holders.inn` — FK к `entity_registry.inn`.

```sql
-- Уже реализовано (Fix 25):
UPDATE entity_registry
SET name_full = COALESCE(NULLIF(name_full,''), ?),
    updated_at = datetime('now')
WHERE inn = ?;
```

### 2. `permitted_uses` / `old_numbers` / `land_cad_numbers` — plain text

Убрана излишняя JSON-сериализация для простых текстовых полей.
Это упрощает запросы и индексирование.

```sql
-- Было: '["Многоквартирный жилой дом"]'
-- Стало: 'Многоквартирный жилой дом'

-- Было: '["90:25:020102:119", "90:25:020102:124"]'
-- Стало: '90:25:020102:119; 90:25:020102:124'
```

### 3. `object_restrictions` — остаётся JSON

`object_restrictions` сохраняется как JSON-массив объектов, потому что
каждое ограничение имеет атрибуты (type, description, registry_number,
basis_doc). Нормализация потребовала бы отдельной таблицы
`object_restriction_records` — это приемлемо при росте проекта.

## Рекомендуемые изменения для v1.11 (не реализованы)

### A. Выделить `object_restriction_records`

```sql
CREATE TABLE object_restriction_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class    TEXT NOT NULL,   -- 'land' | 'building'
    cad_number      TEXT NOT NULL,
    restrict_type   TEXT,            -- czuit_zone | okn_territory
    description     TEXT,
    registry_number TEXT,
    valid_from      TEXT,
    valid_to        TEXT,
    basis_doc_type  TEXT,
    basis_doc_number TEXT,
    basis_doc_date  TEXT,
    source_extract  TEXT,
    UNIQUE(cad_number, registry_number)
);
```

### B. Типизированный FK через object_id вместо cad_number

```sql
-- Вместо: rights.object_key_value = '90:25:020102:24' (TEXT)
-- Предлагается: права → отдельная таблица property_objects(id, cad_number)
-- Тогда: rights.property_id INTEGER REFERENCES property_objects(id)
```

Однако при текущем объёме данных (<10 000 объектов) текстовый cad_number
достаточно быстр с индексом.

### C. Партиционирование `extracts` по году

При длительном мониторинге таблица `extracts` растёт линейно.
Рекомендуется добавить `year_partition` INTEGER для быстрой фильтрации.
