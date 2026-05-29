# Jinja-шаблон torgi_long_description.j2 (с секциями short/full и переключателем по meta.platform), расширенный под `roseltorg.ru` и `sberbank-ast.ru`, есть альтернативные макросы абзацев и дополнительные ветви `if ctx.meta.platform == "...“` в основном блоке.

Ниже — torgi_long_description.j2, в котором есть отдельные блоки для `roseltorg.ru` и `sberbank-ast.ru` (имущественные/банкротные торги), с переключением по `ctx.meta.platform` и режиму `short/full`.[^1][^2]
Оставлены все базовые макросы для ГИС Торги и добавлены платформенные макросы-обёртки, чтобы не дублировать логику.

***

## шаблон torgi_long_description.j2

```jinja
{# ==============================
   Макросы и вспомогательные функции
   ============================== #}

{% macro full_address(location) -%}
    {%- if location.region %}{{ location.region }}{% if location.locality or location.street or location.house or location.building or location.room %}, {% endif %}{% endif -%}
    {%- if location.locality %}{{ location.locality }}{% if location.street or location.house or location.building or location.room %}, {% endif %}{% endif -%}
    {%- if location.street %}{{ location.street }}{% if location.house or location.building or location.room %}, {% endif %}{% endif -%}
    {%- if location.house %}{{ location.house }}{% endif -%}
    {%- if location.building %}, {{ location.building }}{% endif -%}
    {%- if location.room %}, {{ location.room }}{% endif -%}
{%- endmacro %}

{% macro join_encumbrances(encs) -%}
{%- for e in encs -%}
    {{ e.type }}
    {%- if e.description %} ({{ e.description }}){% endif -%}
    {%- if e.influence %} — {{ e.influence }}{% endif -%}
    {%- if not loop.last %}; {% endif -%}
{%- endfor -%}
{%- endmacro %}

{# ==============================
   Базовые абзацы (ядро, переиспользуемое для всех платформ)
   ============================== #}

{# Абзац 1: идентификация и основные параметры для помещений/зданий #}
{% macro paragraph_identity_premise(ctx) -%}
Объектом торгов является {{ ctx.identity.title }}
{%- if ctx.identity.purpose %} {{ ctx.identity.purpose | inflect_gen }} назначения{% endif -%}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif -%},
расположенное{% if ctx.identity.floor and ctx.building.floors_total %} на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного{% elif ctx.identity.floor %} на {{ ctx.identity.floor }}-м этаже{% endif %}{% if ctx.building.building_type %} {{ ctx.building.building_type }}{% endif %} здания по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер объекта: {{ ctx.identity.cadastral_number }}.
{%- endif %}
{%- endmacro %}

{# Абзац 1: идентификация для земельного участка #}
{% macro paragraph_identity_land(ctx) -%}
Объектом торгов является земельный участок
{%- if ctx.identity.area_land_sqm %} площадью {{ ctx.identity.area_land_sqm }} кв. м{% endif -%},
расположенный по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер: {{ ctx.identity.cadastral_number }}.
{%- endif %}
{%- if ctx.legal.zoning %}
 Категория/зонирование земель: {{ ctx.legal.zoning }}.
{%- endif %}
{%- if ctx.legal.use_type_permitted %}
 Разрешенное использование: {{ ctx.legal.use_type_permitted }}.
{%- endif %}
{%- endmacro %}

{# Абзац 2: местоположение и окружение #}
{% macro paragraph_location(ctx) -%}
{% set loc = ctx.location %}
{% if loc.environment_short or loc.transport_access or loc.landmark %}
Объект расположен
    {%- if loc.environment_short %} в {{ loc.environment_short | inflect_loc }}{% elif loc.locality %} в пределах {{ loc.locality | inflect_gen }}{% endif -%}.
{%- if loc.transport_access %}
 Доступ к объекту обеспечен по {{ loc.transport_access | inflect_loc }} улично-дорожной сети.
{%- endif -%}
{%- if loc.landmark %}
 В непосредственной близости находятся {{ loc.landmark }}.
{%- endif %}
{% endif %}
{%- endmacro %}

{# Абзац 3: здание и инженерные сети #}
{% macro paragraph_building(ctx) -%}
{% set b = ctx.building %}
{% if b.building_type or b.floors_total or b.year_built or b.wear_degree or b.engineering %}
{% if b.building_type or b.floors_total or b.year_built -%}
Здание{% if b.building_type %} {{ b.building_type }}{% endif %}{% if b.floors_total %}, {{ b.floors_total }}-этажное{% endif %}{% if b.year_built %}, год постройки — {{ b.year_built }}{% endif %}.
{%- endif %}
{%- if b.wear_degree %}
 Состояние конструктивных элементов оценивается как {{ b.wear_degree }}.
{%- endif %}
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
 Дополнительно имеются элементы благоустройства: {{ b.amenities|join(", ") }}.
{%- endif %}
{% endif %}
{%- endmacro %}

{# Абзац 4: планировка и состояние #}
{% macro paragraph_layout_condition(ctx) -%}
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
{%- endmacro %}

{# Абзац 5: правовой статус и обременения #}
{% macro paragraph_legal(ctx) -%}
{% set l = ctx.legal %}
{% if l.right_type or l.right_holder or l.basis_type or l.encumbrances or l.use_type_fact or l.use_type_permitted %}
Право
    {%- if l.right_type %} {{ l.right_type | inflect_gen }}{% else %} на объект недвижимости{% endif -%}
    {%- if l.right_holder %} зарегистрировано за {{ l.right_holder | inflect_ins }}{% endif -%}
    {%- if l.basis_type %} на основании {{ l.basis_type | inflect_gen }}{% endif %}.
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
{%- endmacro %}

{# Абзац 6: риски и дополнительные характеристики #}
{% macro paragraph_risks_extras(ctx) -%}
{% set r = ctx.risks %}
{% set ex = ctx.extras %}
{% set has_risks = (r.technical_risks and r.technical_risks|length)
                    or (r.legal_risks and r.legal_risks|length)
                    or (r.location_risks and r.location_risks|length)
                    or (r.other_risks and r.other_risks|length) %}
{% if has_risks %}
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
{% set has_extras = (ex.equipment and ex.equipment|length)
                    or ex.furniture
                    or (ex.advantages and ex.advantages|length) %}
{% if has_extras %}
 К дополнительным характеристикам объекта относятся:
{%- if ex.equipment and ex.equipment|length %} установленное оборудование: {{ ex.equipment|join(", ") }};{% endif -%}
{%- if ex.furniture %} наличие мебели: {{ ex.furniture }};{% endif -%}
{%- if ex.advantages and ex.advantages|length %} положительные факторы: {{ ex.advantages|join(", ") }};{% endif %}
{% endif %}
{% if ex.notes %}
 {{ ex.notes }}
{% endif %}
{%- endmacro %}

{# ==============================
   Платформенные обёртки/варианты
   ============================== #}

{# ---- ГИС Торги (torgi.gov.ru) ---- #}
{% macro platform_torgi_short(ctx) -%}
{% if ctx.meta.object_type == "land" %}
{{ paragraph_identity_land(ctx) }}
{% else %}
{{ paragraph_identity_premise(ctx) }}
{% endif %}

{% set p2 = paragraph_location(ctx) %}
{% if p2|trim %}
{{ p2|trim }}
{% endif %}

{% set p3b = paragraph_building(ctx) %}
{% if p3b|trim %}
{{ p3b|trim }}
{% else %}
{{ paragraph_legal(ctx)|trim }}
{% endif %}
{%- endmacro %}

{% macro platform_torgi_full(ctx) -%}
{% if ctx.meta.object_type == "land" %}
{{ paragraph_identity_land(ctx) }}
{% else %}
{{ paragraph_identity_premise(ctx) }}
{% endif %}

{% set p2 = paragraph_location(ctx) %}
{% if p2|trim %}
{{ p2|trim }}
{% endif %}

{% set p3 = paragraph_building(ctx) %}
{% if p3|trim %}
{{ p3|trim }}
{% endif %}

{% set p4 = paragraph_layout_condition(ctx) %}
{% if p4|trim %}
{{ p4|trim }}
{% endif %}

{% set p5 = paragraph_legal(ctx) %}
{% if p5|trim %}
{{ p5|trim }}
{% endif %}

{% set p6 = paragraph_risks_extras(ctx) %}
{% if p6|trim %}
{{ p6|trim }}
{% endif %}
{%- endmacro %}

{# ---- Росэлторг (www.roseltorg.ru) ----
   Чуть более «разговорный» и развернутый стиль #}

{% macro platform_roseltorg_short(ctx) -%}
{# Абзац 1: общие сведения #}
На торги выставляется {{ ctx.identity.title }}
{%- if ctx.identity.purpose %} {{ ctx.identity.purpose | inflect_gen }} назначения{% endif -%}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif -%},
расположенное по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.floor and ctx.building.floors_total %}
 Помещение находится на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного {{ ctx.building.building_type }} здания.
{%- elif ctx.identity.floor %}
 Помещение находится на {{ ctx.identity.floor }}-м этаже здания.
{%- endif -%}
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер: {{ ctx.identity.cadastral_number }}.
{%- endif %}

{# Абзац 2: местоположение #}
{% set loc = ctx.location %}
{% if loc.environment_short or loc.locality or loc.landmark %}
Объект расположен в
    {%- if loc.environment_short %} {{ loc.environment_short }}{% elif loc.municipality %} районе {{ loc.municipality }}{% elif loc.locality %} пределах {{ loc.locality }}{% endif -%}.
{%- if loc.landmark %}
 В зоне шаговой доступности находятся {{ loc.landmark }}.
{%- endif %}
{% endif %}
{%- endmacro %}

{% macro platform_roseltorg_full(ctx) -%}
{# Абзац 1: общие сведения #}
На торги выставляется {{ ctx.identity.title }}
{%- if ctx.identity.purpose %} {{ ctx.identity.purpose | inflect_gen }} назначения{% endif -%}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif -%},
расположенное по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.floor and ctx.building.floors_total %}
 Помещение находится на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного {{ ctx.building.building_type }} здания.
{%- elif ctx.identity.floor %}
 Помещение находится на {{ ctx.identity.floor }}-м этаже здания.
{%- endif -%}
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер: {{ ctx.identity.cadastral_number }}.
{%- endif %}

{# Абзац 2: описание местоположения #}
{% set loc = ctx.location %}
{% if loc.environment_short or loc.municipality or loc.locality or loc.landmark %}
Объект расположен в
    {%- if loc.environment_short %} {{ loc.environment_short }}{% elif loc.municipality %} районе {{ loc.municipality }}{% elif loc.locality %} пределах {{ loc.locality }}{% endif -%}.
 Район характеризуется {{ loc.environment_short if loc.environment_short else "развитой городской застройкой" }}.
{%- if loc.landmark %}
 В непосредственной близости расположены {{ loc.landmark }}.
{%- endif %}
{% endif %}

{# Абзац 3: здание и территория #}
{% set b = ctx.building %}
{% if b.building_type or b.floors_total or b.year_built or b.wear_degree or b.amenities %}
Здание {{ b.building_type if b.building_type else "" }}
    {%- if b.floors_total %}, {{ b.floors_total }}-этажное{% endif -%}
    {%- if b.year_built %}, постройки {{ b.year_built }} года{% endif -%}.
 Состояние строительных конструкций оценивается как {{ b.wear_degree if b.wear_degree else "удовлетворительное" }}.
{%- if b.amenities and b.amenities|length %}
 Территория вокруг здания {{ b.amenities|join(", ") }}.
{%- endif %}
{% endif %}

{# Абзац 4: внутренние характеристики #}
{% set p4 = paragraph_layout_condition(ctx) %}
{% if p4|trim %}
{{ p4|trim }}
{% endif %}

{# Абзац 5: правовой статус #}
{% set p5 = paragraph_legal(ctx) %}
{% if p5|trim %}
{{ p5|trim }}
{% endif %}

{# Абзац 6: выводы/рекомендации #}
{% set r = ctx.risks %}
С учетом местоположения, технического состояния и правового статуса объект может быть использован для {{ ctx.legal.use_type_fact if ctx.legal.use_type_fact else "размещения объектов, соответствующих его назначению" }}.
{% if (r.technical_risks and r.technical_risks|length)
   or (r.legal_risks and r.legal_risks|length)
   or (r.location_risks and r.location_risks|length) %}
 Потенциальному покупателю следует учитывать следующие риски: 
    {%- if r.technical_risks and r.technical_risks|length %} технические — {{ r.technical_risks|join(", ") }};{% endif -%}
    {%- if r.legal_risks and r.legal_risks|length %} правовые — {{ r.legal_risks|join(", ") }};{% endif -%}
    {%- if r.location_risks and r.location_risks|length %} территориальные — {{ r.location_risks|join(", ") }};{% endif -%}
{% endif %}
{%- endmacro %}

{# ---- Сбербанк-АСТ (sberbank-ast.ru) ----
   Акцент на процедуру (банкротство/реализация имущества) #}

{% macro platform_sber_short(ctx) -%}
{# Абзац 1: предмет торгов #}
Предметом торгов является {{ ctx.identity.title }}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif -%},
расположенное по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.floor and ctx.building.floors_total %}
 Помещение расположено на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного {{ ctx.building.building_type }} здания.
{%- endif -%}
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер {{ ctx.identity.cadastral_number }}.
{%- endif %}
 Объект реализуется в составе имущества {{ ctx.legal.right_holder if ctx.legal.right_holder else "правообладателя" }} в порядке {{ ctx.meta.procedure_type if ctx.meta.procedure_type else "установленной процедуры" }}.

{# Абзац 2: краткая характеристика района и состояния #}
{% set loc = ctx.location %}
{% if loc.environment_short or loc.locality %}
Район расположения объекта характеризуется {{ loc.environment_short if loc.environment_short else "развитой городской застройкой" }}.
{% endif %}
{% set b = ctx.building %}
{% if b.building_type or b.wear_degree %}
Здание {{ b.building_type if b.building_type else "" }}; состояние строительных конструкций и инженерных систем оценивается как {{ b.wear_degree if b.wear_degree else "удовлетворительное" }}.
{% endif %}
{%- endmacro %}

{% macro platform_sber_full(ctx) -%}
{# Абзац 1: предмет торгов #}
Предметом торгов является {{ ctx.identity.title }}
{%- if ctx.identity.area_total_sqm %} общей площадью {{ ctx.identity.area_total_sqm }} кв. м{% endif -%},
расположенное по адресу: {{ full_address(ctx.location) }}.
{%- if ctx.identity.floor and ctx.building.floors_total %}
 Помещение расположено на {{ ctx.identity.floor }}-м этаже {{ ctx.building.floors_total }}-этажного {{ ctx.building.building_type }} здания.
{%- endif -%}
{%- if ctx.identity.cadastral_number %}
 Кадастровый номер {{ ctx.identity.cadastral_number }}.
{%- endif %}
 Объект реализуется в составе имущества {{ ctx.legal.right_holder if ctx.legal.right_holder else "правообладателя" }} в порядке {{ ctx.meta.procedure_type if ctx.meta.procedure_type else "реализации имущества" }}.

{# Абзац 2: характеристика района и здания #}
{% set loc = ctx.location %}
{% set b = ctx.building %}
Район расположения объекта характеризуется {{ loc.environment_short if loc.environment_short else "развитой городской застройкой" }}.
{% if loc.landmark %}
 В непосредственной близости расположены {{ loc.landmark }}.
{% endif %}
Здание {{ b.building_type if b.building_type else "" }}
    {%- if b.floors_total %}, {{ b.floors_total }}-этажное{% endif -%}
    {%- if b.year_built %}, {{ b.year_built }} года постройки{% endif -%}.
 Состояние строительных конструкций и инженерных систем оценивается как {{ b.wear_degree if b.wear_degree else "удовлетворительное" }}.

{# Абзац 3: внутренние помещения #}
{% set p3 = paragraph_layout_condition(ctx) %}
{% if p3|trim %}
{{ p3|trim }}
{% endif %}

{# Абзац 4: правовой статус и обременения #}
{% set p4 = paragraph_legal(ctx) %}
{% if p4|trim %}
{{ p4|trim }}
{% endif %}

{# Абзац 5: риски (акцент для банкротства; печатается только при наличии рисков) #}
{% set r = ctx.risks %}
{% set _has_any_risks = (r.technical_risks and r.technical_risks|length)
   or (r.legal_risks and r.legal_risks|length)
   or (r.location_risks and r.location_risks|length)
   or (r.other_risks and r.other_risks|length) %}
{% if _has_any_risks %}
По результатам анализа документации и материалов дела о банкротстве участникам торгов рекомендуется учитывать следующие факторы риска:
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
Существенные технические, правовые и территориальные риски по объекту не выявлены.
{% endif %}
{%- endmacro %}

{# ==============================
   Основной блок: выбор платформы и режима
   ============================== #}

{% if ctx.meta.platform == "torgi.gov.ru" %}

    {% if ctx.meta.platform_mode == "short" %}
{{ platform_torgi_short(ctx) }}
    {% else %}
{{ platform_torgi_full(ctx) }}
    {% endif %}

{% elif ctx.meta.platform == "roseltorg.ru" %}

    {% if ctx.meta.platform_mode == "short" %}
{{ platform_roseltorg_short(ctx) }}
    {% else %}
{{ platform_roseltorg_full(ctx) }}
    {% endif %}

{% elif ctx.meta.platform == "sberbank-ast.ru" %}

    {% if ctx.meta.platform_mode == "short" %}
{{ platform_sber_short(ctx) }}
    {% else %}
{{ platform_sber_full(ctx) }}
    {% endif %}

{% else %}
    {# Fallback для прочих площадок #}
    {% if ctx.meta.platform_mode == "short" %}
{{ paragraph_identity_premise(ctx) }}
    {% else %}
{{ paragraph_identity_premise(ctx) }}

{{ paragraph_location(ctx) }}

{{ paragraph_building(ctx) }}

{{ paragraph_layout_condition(ctx) }}

{{ paragraph_legal(ctx) }}

{{ paragraph_risks_extras(ctx) }}
    {% endif %}
{% endif %}
```


***

### Как использовать

- Для ГИС Торги: `ctx.meta.platform = "torgi.gov.ru"`.
- Для Росэлторг: `ctx.meta.platform = "roseltorg.ru"`.
- Для Сбербанк‑АСТ: `ctx.meta.platform = "sberbank-ast.ru"`, опционально можно передать `ctx.meta.procedure_type` вроде `"реализации имущества должника в рамках дела о банкротстве"`, чтобы текст был более точным.[^2][^1]

В остальном вызов такой же:

```python
ctx["meta"]["platform_mode"] = "short"  # или "full"
text = jinja_env.get_template("torgi_long_description.j2").render(ctx=ctx)
```

[^1]: https://tensor.ru/uc/etp/roseltorg/info

[^2]: https://delo.modulbank.ru/all/instruction-auction-Sber-Ast

