# Список плейсхолдеров и условия их включения, в виде псевдокода или JSON-схемы, чтобы реализовать это как шаблонизатор (Jinja) в сервисе.

Ниже — список плейсхолдеров и логика их включения в формате, удобном для реализации в Jinja (условия/фильтры) плюс JSON‑схема описания этих плейсхолдеров.[^1][^2]

## 1. Базовые сущности и имена полей

Все шаблоны опираются на один объект контекста, например `ctx`:

```json
{
  "meta": { ... },
  "identity": { ... },
  "location": { ... },
  "building": { ... },
  "layout_and_condition": { ... },
  "legal": { ... },
  "risks": { ... },
  "extras": { ... }
}
```

В Jinja ты можешь передавать это как:

```python
render("torgi_long_description.txt", ctx=ctx)
```

И обращаться в шаблонах как `{{ ctx.identity.title }}`, `{{ ctx.location.region }}` и т.д.

***

## 2. Список плейсхолдеров и условия включения (Jinja‑логика)

### 2.1. identity

Поля:

- `identity.title` — обязательное (тип объекта).
- `identity.purpose` — опционально.
- `identity.area_total_sqm` — опционально (обязательно для помещений/зданий).
- `identity.area_land_sqm` — опционально (обязательно для участков).
- `identity.floor` — опционально (для помещений).
- `identity.floors_total` — опционально (для здания/помещения).
- `identity.cadastral_number` — опционально, но желательно.

Пример включения:

```jinja
Объектом торгов является {{ ctx.identity.title }}
{%- if ctx.identity.purpose %} {{ ctx.identity.purpose }} назначения{% endif %}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif %},
расположенное
{%- if ctx.location.floor and ctx.building.floors_total %}
    на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного
{%- elif ctx.identity.floor %}
    на {{ ctx.identity.floor }}-м этаже
{%- endif %}
{%- if ctx.building.building_type %} {{ ctx.building.building_type }}{% endif %}
здания по адресу: ...
{%- if ctx.identity.cadastral_number %} Кадастровый номер объекта: {{ ctx.identity.cadastral_number }}.{% endif %}
```

Условие: каждый фрагмент (назначение, площадь, этажность, тип здания, кадастровый номер) включается только при наличии соответствующего поля.

Для земельного участка:

```jinja
{% if ctx.object_type == "land" %}
Объектом торгов является земельный участок
{%- if ctx.identity.area_land_sqm %} площадью {{ ctx.identity.area_land_sqm }} кв. м{% endif %},
расположенный по адресу: ...
{%- if ctx.identity.cadastral_number %} Кадастровый номер: {{ ctx.identity.cadastral_number }}.{% endif %}
{% endif %}
```


***

### 2.2. location

Поля:

- `location.region` — опционально, желательно.
- `location.municipality` — опционально.
- `location.locality` — желательно.
- `location.street`, `location.house`, `location.building`, `location.room` — опционально.
- `location.landmark` — опционально.
- `location.transport_access` — опционально.
- `location.environment_short` — опционально.

Формирование полного адреса:

```jinja
{# вспомогательный макрос #}
{% macro full_address(location) -%}
    {%- if location.region %}{{ location.region }}, {% endif -%}
    {%- if location.locality %}{{ location.locality }}, {% endif -%}
    {%- if location.street %}{{ location.street }}, {% endif -%}
    {%- if location.house %}{{ location.house }}{% endif -%}
    {%- if location.building %}, {{ location.building }}{% endif -%}
    {%- if location.room %}, {{ location.room }}{% endif -%}
{%- endmacro %}
```

Использование:

```jinja
по адресу: {{ full_address(ctx.location) }}.
```

Абзац про окружение:

```jinja
{% if ctx.location.environment_short or ctx.location.transport_access or ctx.location.landmark %}
Объект расположен
    {%- if ctx.location.environment_short %} в {{ ctx.location.environment_short }}{% endif %}
    {%- if ctx.location.locality and not ctx.location.environment_short %}
        в пределах {{ ctx.location.locality }}
    {%- endif %}.
{%- if ctx.location.transport_access %}
    Доступ к объекту обеспечен по {{ ctx.location.transport_access }} улично-дорожной сети.
{%- endif %}
{%- if ctx.location.landmark %}
    В непосредственной близости находятся {{ ctx.location.landmark }}.
{%- endif %}
{% endif %}
```


***

### 2.3. building

Поля:

- `building.building_type`
- `building.floors_total`
- `building.year_built`
- `building.renovation_year`
- `building.wear_degree`
- `building.engineering.electricity`, `water`, `sewerage`, `heating`, `gas`, `telecom`
- `building.amenities` (массив строк)

Абзац:

```jinja
{% set b = ctx.building %}
{% if b.building_type or b.floors_total or b.year_built or b.wear_degree or b.engineering %}
Здание
    {%- if b.building_type %} {{ b.building_type }}{% endif -%}
    {%- if b.floors_total %}, {{ b.floors_total }}-этажное{% endif -%}
    {%- if b.year_built %}, год постройки — {{ b.year_built }}{% endif -%}
    {%- if b.wear_degree %}, состояние конструктивных элементов оценивается как {{ b.wear_degree }}{% endif -%}.
{%- if b.engineering %}
    Объект подключен к основным инженерным сетям:
    {%- if b.engineering.electricity %} электроснабжение — {{ b.engineering.electricity }}{% endif -%}
    {%- if b.engineering.water %}, водоснабжение — {{ b.engineering.water }}{% endif -%}
    {%- if b.engineering.sewerage %}, водоотведение — {{ b.engineering.sewerage }}{% endif -%}
    {%- if b.engineering.heating %}, отопление — {{ b.engineering.heating }}{% endif -%}
    {%- if b.engineering.gas %}, газоснабжение — {{ b.engineering.gas }}{% endif -%}
    {%- if b.engineering.telecom %}, телекоммуникации — {{ b.engineering.telecom }}{% endif %}.
{%- endif %}
{%- if b.amenities and b.amenities|length > 0 %}
    Территория/здание дополнительно характеризуются следующими элементами благоустройства: {{ b.amenities|join(", ") }}.
{%- endif %}
{% endif %}
```

Условие: весь абзац пропускается, если нет ни одного из ключевых полей.

***

### 2.4. layout_and_condition

Поля:

- `layout_and_condition.layout_type`
- `layout_and_condition.rooms_count`
- `layout_and_condition.ceiling_height_m`
- `layout_and_condition.finish_level`
- `layout_and_condition.finish_state`
- `layout_and_condition.windows`
- `layout_and_condition.entry_group`
- `layout_and_condition.current_condition_comment`

Абзац:

```jinja
{% set lc = ctx.layout_and_condition %}
{% if lc.layout_type or lc.rooms_count or lc.ceiling_height_m or lc.finish_level or lc.finish_state or lc.entry_group or lc.current_condition_comment %}
Планировочное решение — 
    {%- if lc.layout_type %} {{ lc.layout_type }}{% else %} типовое{% endif -%}
    {%- if lc.rooms_count %}, количество изолированных помещений — {{ lc.rooms_count }}{% endif %}.
{%- if lc.ceiling_height_m %}
    Высота потолков составляет {{ lc.ceiling_height_m }} м.
{%- endif %}
{%- if lc.finish_level or lc.finish_state %}
    Отделка — 
    {%- if lc.finish_level %} {{ lc.finish_level }}{% endif -%}
    {%- if lc.finish_state %}, состояние отделки оценивается как {{ lc.finish_state }}{% endif %}.
{%- endif %}
{%- if lc.entry_group %}
    Входная группа: {{ lc.entry_group }}.
{%- endif %}
{%- if lc.current_condition_comment %}
    {{ lc.current_condition_comment }}.
{%- endif %}
{% endif %}
```


***

### 2.5. legal

Поля:

- `legal.right_type`
- `legal.right_holder`
- `legal.basis_type`
- `legal.encumbrances` — массив объектов `{type, description, influence}`
- `legal.use_type_fact`
- `legal.use_type_permitted`
- `legal.zoning`
- `legal.special_restrictions` — массив строк

Вспомогательная функция для обременений (можно как макрос):

```jinja
{% macro join_encumbrances(encs) -%}
{%- for e in encs -%}
    {{ e.type }}
    {%- if e.description %} ({{ e.description }}){% endif -%}
    {%- if e.influence %} — {{ e.influence }}{% endif -%}
    {%- if not loop.last %}; {% endif -%}
{%- endfor -%}
{%- endmacro %}
```

Абзац:

```jinja
{% set l = ctx.legal %}
{% if l.right_type or l.right_holder or l.basis_type or l.encumbrances or l.use_type_fact or l.use_type_permitted %}
Право {{ l.right_type if l.right_type else "на объект недвижимости" }}
    {%- if l.right_holder %} зарегистрировано за {{ l.right_holder }}{% endif %}
    {%- if l.basis_type %} на основании {{ l.basis_type }}{% endif %}.
{%- if l.encumbrances and l.encumbrances|length > 0 %}
    В отношении объекта зарегистрированы следующие обременения: {{ join_encumbrances(l.encumbrances) }}.
{%- else %}
    Сведений о зарегистрированных обременениях не имеется.
{%- endif %}
{%- if l.use_type_fact %}
    Фактическое использование объекта — {{ l.use_type_fact }}.
{%- endif %}
{%- if l.use_type_permitted %}
    Виды разрешенного использования в соответствии с градостроительной документацией: {{ l.use_type_permitted }}.
{%- endif %}
{% endif %}
```


***

### 2.6. risks

Поля:

- `risks.technical_risks` — массив строк
- `risks.legal_risks` — массив строк
- `risks.location_risks` — массив строк
- `risks.other_risks` — массив строк

Абзац:

```jinja
{% set r = ctx.risks %}
{% if (r.technical_risks and r.technical_risks|length)
   or (r.legal_risks and r.legal_risks|length)
   or (r.location_risks and r.location_risks|length)
   or (r.other_risks and r.other_risks|length) %}
По результатам анализа документации и осмотра объекта выделены следующие особенности и риски:
{%- if r.technical_risks and r.technical_risks|length %}
    технические — {{ r.technical_risks|join(", ") }};
{%- endif %}
{%- if r.legal_risks and r.legal_risks|length %}
    правовые — {{ r.legal_risks|join(", ") }};
{%- endif %}
{%- if r.location_risks and r.location_risks|length %}
    территориальные — {{ r.location_risks|join(", ") }};
{%- endif %}
{%- if r.other_risks and r.other_risks|length %}
    иные — {{ r.other_risks|join(", ") }};
{%- endif %}
{% else %}
По результатам анализа документации и осмотра объекта существенных технических, правовых и территориальных рисков не выявлено.
{% endif %}
```


***

### 2.7. extras

Поля:

- `extras.equipment` — массив строк
- `extras.furniture` — строка
- `extras.advantages` — массив строк
- `extras.notes` — строка

Абзац:

```jinja
{% set ex = ctx.extras %}
{% if (ex.equipment and ex.equipment|length) or ex.furniture or (ex.advantages and ex.advantages|length) %}
К дополнительным характеристикам объекта относятся:
{%- if ex.equipment and ex.equipment|length %}
    установленное оборудование: {{ ex.equipment|join(", ") }};
{%- endif %}
{%- if ex.furniture %}
    наличие мебели: {{ ex.furniture }};
{%- endif %}
{%- if ex.advantages and ex.advantages|length %}
    положительные факторы: {{ ex.advantages|join(", ") }};
{%- endif %}
{% endif %}
{% if ex.notes %}
{{ ex.notes }}
{% endif %}
```


***

## 3. JSON‑схема плейсхолдеров (конфигурация для движка)

Можешь описать конфигурацию плейсхолдеров (для валидации/редактора) так:

```json
{
  "sections": [
    {
      "name": "identity",
      "fields": [
        {"name": "title", "type": "string", "required": true},
        {"name": "purpose", "type": "string", "required": false},
        {"name": "area_total_sqm", "type": "number", "required": false},
        {"name": "area_land_sqm", "type": "number", "required": false},
        {"name": "floor", "type": "integer", "required": false},
        {"name": "floors_total", "type": "integer", "required": false},
        {"name": "cadastral_number", "type": "string", "required": false}
      ]
    },
    {
      "name": "location",
      "fields": [
        {"name": "region", "type": "string", "required": false},
        {"name": "municipality", "type": "string", "required": false},
        {"name": "locality", "type": "string", "required": false},
        {"name": "street", "type": "string", "required": false},
        {"name": "house", "type": "string", "required": false},
        {"name": "building", "type": "string", "required": false},
        {"name": "room", "type": "string", "required": false},
        {"name": "landmark", "type": "string", "required": false},
        {"name": "transport_access", "type": "string", "required": false},
        {"name": "environment_short", "type": "string", "required": false}
      ]
    },
    {
      "name": "building",
      "fields": [
        {"name": "building_type", "type": "string", "required": false},
        {"name": "floors_total", "type": "integer", "required": false},
        {"name": "year_built", "type": "integer", "required": false},
        {"name": "renovation_year", "type": "integer", "required": false},
        {"name": "wear_degree", "type": "string", "required": false},
        {
          "name": "engineering",
          "type": "object",
          "required": false,
          "fields": [
            {"name": "electricity", "type": "string", "required": false},
            {"name": "water", "type": "string", "required": false},
            {"name": "sewerage", "type": "string", "required": false},
            {"name": "heating", "type": "string", "required": false},
            {"name": "gas", "type": "string", "required": false},
            {"name": "telecom", "type": "string", "required": false}
          ]
        },
        {"name": "amenities", "type": "array", "items": "string", "required": false}
      ]
    },
    {
      "name": "layout_and_condition",
      "fields": [
        {"name": "layout_type", "type": "string", "required": false},
        {"name": "rooms_count", "type": "integer", "required": false},
        {"name": "ceiling_height_m", "type": "number", "required": false},
        {"name": "finish_level", "type": "string", "required": false},
        {"name": "finish_state", "type": "string", "required": false},
        {"name": "windows", "type": "string", "required": false},
        {"name": "entry_group", "type": "string", "required": false},
        {"name": "current_condition_comment", "type": "string", "required": false}
      ]
    },
    {
      "name": "legal",
      "fields": [
        {"name": "right_type", "type": "string", "required": false},
        {"name": "right_holder", "type": "string", "required": false},
        {"name": "basis_type", "type": "string", "required": false},
        {
          "name": "encumbrances",
          "type": "array",
          "items": {
            "type": "object",
            "fields": [
              {"name": "type", "type": "string", "required": true},
              {"name": "description", "type": "string", "required": false},
              {"name": "influence", "type": "string", "required": false}
            ]
          },
          "required": false
        },
        {"name": "use_type_fact", "type": "string", "required": false},
        {"name": "use_type_permitted", "type": "string", "required": false},
        {"name": "zoning", "type": "string", "required": false},
        {"name": "special_restrictions", "type": "array", "items": "string", "required": false}
      ]
    },
    {
      "name": "risks",
      "fields": [
        {"name": "technical_risks", "type": "array", "items": "string", "required": false},
        {"name": "legal_risks", "type": "array", "items": "string", "required": false},
        {"name": "location_risks", "type": "array", "items": "string", "required": false},
        {"name": "other_risks", "type": "array", "items": "string", "required": false}
      ]
    },
    {
      "name": "extras",
      "fields": [
        {"name": "equipment", "type": "array", "items": "string", "required": false},
        {"name": "furniture", "type": "string", "required": false},
        {"name": "advantages", "type": "array", "items": "string", "required": false},
        {"name": "notes", "type": "string", "required": false}
      ]
    }
  ]
}
```


***

[^1]: https://torgi.gov.ru/new/api/public/lotcards/export/excel?dynSubjRF=\&biddType=\&biddForm=\&currCode=\&lotStatus=PUBLISHED%2CAPPLICATIONS_SUBMISSION%2CDETERMINING_WINNER\&biddEndFrom=\&biddEndTo=\&pubFrom=\&pubTo=\&aucStartFrom=\&aucStartTo=\&etpCode=\&text=\&matchPhrase=false\&noticeStatus=\&amoOrgCode=\&resourceTypeUse=\&npa=\&byFirstVersion=true\&sort=firstVersionPublicationDate%2Cdesc

[^2]: https://sberocenka.ru/article/otchet-ob-otsenke-nedvizhimosti.html

