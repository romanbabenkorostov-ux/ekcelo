# SPEC: Экспорт объектов сюрвея Ekcelo в ЭТП (torgi.gov.ru / roseltorg.ru / sberbank-ast.ru)

> Артефакт-спецификация. Содержит модель данных, маппинг, гэп-анализ и план доработки. Скрипты не пишутся в рамках этой задачи.

---

## 1. Context

Ekcelo сейчас умеет парсить выписки ЕГРН, обогащать NSPD, собирать фото/документы и публиковать данные в виде KMZ, EXIF-подписанных JPG и DOCX-отчётов. Для участия экономиста в продаже залогового/имущественного фонда через российские ЭТП требуется новый канал вывода — **карточка лота с развёрнутым описанием** в формате, близком к разделу «Описание объекта» отчёта оценщика.

Цель спеки — закрыть зазор между внутренней моделью Ekcelo (центрированной вокруг кадастрового номера) и требованиями ЭТП (центрированными вокруг лота с человекочитаемым описанием), не ломая принцип «БД = слепок ЕГРН».

Источник целевой модели описания, согласованный с экономистом, см. в `docs/etp_export/` (файлы 00–05): структура `long_description`, абзацные шаблоны для ГИС Торги / Росэлторг / Сбербанк-АСТ и Jinja-движок генерации.

---

## 2. Scope

| Платформа | Тон | Особенности |
|---|---|---|
| `torgi.gov.ru` | Официальный, сжатый | Канон — гос-формат; короткий + полный режимы |
| `roseltorg.ru` | Разговорно-развёрнутый | Больше описания района и выводов |
| `sberbank-ast.ru` | Оценочно-процедурный | Акцент на «предмет торгов», банкротство/реализация |

Все три — синхронно (общее JSON-ядро + платформенные адаптеры). Единица экспорта — **лот** (группа КН: например, здание + земля + помещения + оборудование), не отдельный КН.

Артефакты на каждый лот:
- `long_description.json` — структурированное ядро (см. §3).
- `description.short.txt` + `description.full.txt` — сгенерированные тексты под платформу.
- `lot_appendix.pdf` — PDF-приложение со ссылкой на отчёт оценщика и техдокументы.
- (Опционально) `gallery/` — фото и сканы из существующего EXIF-пайплайна.

---

## 3. Целевая JSON-структура `long_description`

```
meta { platform, platform_mode, object_type, deal_type, procedure_type, locale }
identity { title, purpose, area_total_sqm, area_land_sqm, floor, floors_total, cadastral_number }
location { region, municipality, locality, street, house, building, room,
           landmark, transport_access, environment_short }
building { building_type, floors_total, year_built, renovation_year, wear_degree,
           engineering{electricity, water, sewerage, heating, gas, telecom},
           amenities[] }
layout_and_condition { layout_type, rooms_count, ceiling_height_m, finish_level,
                       finish_state, windows, entry_group, current_condition_comment }
legal { right_type, right_holder, basis_type, encumbrances[{type,description,influence}],
        use_type_fact, use_type_permitted, zoning, special_restrictions[] }
risks { technical_risks[], legal_risks[], location_risks[], other_risks[] }
extras { equipment[], furniture, advantages[], notes }
generated_text { short, full, version }
```

Каноническая JSON-схема и Jinja-плейсхолдеры с условиями включения — в `docs/etp_export/` (файлы 03 и 05). Они переезжают в репо как есть.

---

## 4. Маппинг Ekcelo → ЭТП-структура

| Секция / поле | Источник в Ekcelo | Состояние |
|---|---|---|
| `identity.title, purpose, area_total_sqm, area_land_sqm, cadastral_number` | `objects.purpose, objects.area, objects.cad_number` | ✅ есть |
| `identity.floor, floors_total` | `objects.floors`, building parent | ✅ есть |
| `location.region/locality/street/house/building/room` | `objects.address` (plain) | ⚠️ нужен парсер адреса в компоненты |
| `location.landmark, transport_access, environment_short` | — | ❌ гэп → новые поля |
| `building.building_type, floors_total, year_built` | NSPD enrichment + `objects` | ⚠️ частично |
| `building.renovation_year, wear_degree, engineering, amenities` | — | ❌ гэп → ОСВ + EXIF |
| `layout_and_condition.rooms_count` | объекты-помещения с parent | ✅ есть |
| `layout_and_condition.layout_type, ceiling_height_m, finish_level, finish_state, windows, entry_group, current_condition_comment` | — | ❌ гэп → ОСВ + EXIF |
| `legal.right_type, right_holder, basis_type` | `rights` + `entity_registry` | ✅ есть |
| `legal.encumbrances[]` | `object_restrictions` | ⚠️ нужен маппер типа→текст |
| `legal.use_type_fact, use_type_permitted, zoning, special_restrictions` | `objects.permitted_use` + NSPD + `object_restrictions` (ЗОУИТ, ОКН) | ⚠️ собрать в один блок |
| `risks.legal_risks` | overlay-эффекты в `documents.json` (залоги, аресты, суды) | ⚠️ нужен экстрактор |
| `risks.technical_risks, location_risks, other_risks` | — | ❌ гэп → ОСВ + LLM-suggest |
| `extras.equipment, furniture` | `structure_*.json` (оборудование, инв.№, балансовая стоимость) | ✅ есть |
| `extras.advantages, notes` | EXIF UserComment notes | ⚠️ нужна агрегация |
| `meta.procedure_type` (Сбер-АСТ) | overlay-документы (банкротство, приватизация) | ⚠️ выводить из контекста |

**Гэпы (12 полей)** закрываются единым слоем `object_etp_profile` (см. §5), наполняемым из ОСВ/survey-листа экономиста и парсера EXIF-комментариев. NSPD/LLM — фолбэк, не источник правды.

---

## 5. Изменения схемы БД

Одна миграция `schema/migrations/0NN_etp_profile.sql`:

### 5.1 Таблица `object_etp_profile`
```
object_etp_profile (
  cad_number TEXT PRIMARY KEY REFERENCES objects(cad_number),
  location_extra JSON,      -- {landmark, transport_access, environment_short}
  building_extra JSON,      -- {renovation_year, wear_degree, engineering{}, amenities[]}
  layout JSON,              -- {layout_type, ceiling_height_m, finish_level,
                            --  finish_state, windows, entry_group, current_condition_comment}
  legal_extra JSON,         -- {use_type_fact, zoning, special_restrictions[]}
  risks JSON,               -- {technical[], legal[], location[], other[]}
  extras JSON,              -- {furniture, advantages[], notes}
  source TEXT,              -- 'osv' | 'exif' | 'manual' | 'nspd' | 'llm'
  confidence REAL,          -- 0..1, для не-ручных источников
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 5.2 Таблица `lots`
```
lots (
  lot_id TEXT PRIMARY KEY,           -- человекочитаемый, напр. "lot_pirushin_001"
  name TEXT,
  platform_targets JSON,             -- ["torgi.gov.ru","sberbank-ast.ru"]
  procedure_type TEXT,               -- "приватизация" | "банкротство" | "коммерческая продажа"
  deal_type TEXT,                    -- "sale" | "lease" | "other"
  primary_cad_number TEXT,           -- ведущий КН для адреса/идентификации
  notes_md TEXT,                     -- ручные пометки экономиста
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

lot_items (
  lot_id TEXT REFERENCES lots(lot_id),
  cad_number TEXT REFERENCES objects(cad_number),
  role TEXT,                         -- "building" | "land" | "room" | "equipment" | "structure"
  ord INTEGER,
  PRIMARY KEY (lot_id, cad_number)
)
```

JSON-колонки позволяют расширять структуру без новых миграций; индексы — только по `lot_id` и `cad_number`.

---

## 6. Структура модуля экспорта

```
parser/exporters/etp/
  __init__.py
  build_lot_context.py        # сборка ctx из objects + rights + object_restrictions
                              #   + object_etp_profile + lot_items + documents overlay
  address_parser.py           # plain address → {region, municipality, ..., room}
  encumbrance_mapper.py       # object_restrictions → encumbrances[] с человекочитаемым influence
  risks_extractor.py          # documents.json overlay → legal_risks[]
  text_render.py              # Jinja Environment + платформенный диспатч
  pdf_appendix.py             # PDF со ссылкой на отчёт оценщика и инвентарём документов лота
  cli.py                      # export-etp --lot <lot_id> --platform <p> --mode short|full

  templates/
    torgi_long_description.j2 # из docs/etp_export/05 (как есть)
    macros/
      address.j2
      encumbrances.j2
      risks.j2
```

Контракт: `build_lot_context(lot_id) -> dict (ctx)` строго совместим с §3. Текст рендерится через `text_render.render(ctx)`. Артефакты пишутся в `out/etp/<lot_id>/<platform>/`.

Использовать существующие утилиты:
- Чтение из БД и сборка graph — паттерн из `parser/scripts/pirushin_sosn_rocha_08_build_kmz_v2.py` (balloon_zu / balloon_oks / balloon_room).
- Overlay-эффекты документов — модель из `dev/SPEC_TEMPORAL_REPORTS.md`.
- EXIF UserComment — `docs/EXIF_USERCOMMENT_SCHEMA.md`.

---

## 7. Источники для гэп-полей

| Поле | Первичный источник | Фолбэк |
|---|---|---|
| `location_extra.*` | survey-лист экономиста (YAML/XLSX → ETL в `object_etp_profile`) | NSPD geo-context |
| `building_extra.engineering.*` | ОСВ/обходной лист | LLM-suggest с `source='llm'` |
| `building_extra.wear_degree, amenities` | фото EXIF UserComment notes | LLM-классификатор по фото |
| `layout.*` | ОСВ + техпаспорт | EXIF notes |
| `risks.legal[]` | overlay-эффекты `documents.json` (auto) | — |
| `risks.technical[], location[]` | ОСВ + комментарии в фото | — |
| `extras.advantages, notes, furniture` | EXIF UserComment notes (агрегация) | manual notes лота |

Экономист в ОСВ заполняет минимальный набор; парсер EXIF при обработке фото пишет дельты в `object_etp_profile` с `source='exif'`. Ручные правки получают `source='manual'` и имеют наивысший приоритет при мерже.

---

## 8. Платформенный диспатч (Jinja)

Шаблон `torgi_long_description.j2` уже содержит ветви для всех трёх платформ (см. файл 05). Импортируется как есть. Меняется только запуск:

```
ctx['meta']['platform'] = 'sberbank-ast.ru'
ctx['meta']['platform_mode'] = 'full'
ctx['meta']['procedure_type'] = 'реализации имущества должника в рамках дела о банкротстве'
text = env.get_template('torgi_long_description.j2').render(ctx=ctx)
```

`short` — для вставки в карточку ЭТП (2–3 абзаца), `full` — для PDF-приложения и встраиваемого виджета (4–6 абзацев).

---

## 9. CLI и интеграция

```
python -m parser.exporters.etp.cli \
  --lot lot_pirushin_001 \
  --platforms torgi.gov.ru,roseltorg.ru,sberbank-ast.ru \
  --modes short,full \
  --out out/etp/
```

Для каждой пары `(platform, mode)` — отдельный файл текста. JSON и PDF — один на лот.

Включить в существующий golden path экономиста (`docs/GOLDEN_PATH_economist_v3.md`) шагом «09. Экспорт под ЭТП» после KMZ-сборки.

---

## 10. Гэп-инвентарь (для трекинга)

Не покрыто стандартной схемой Ekcelo до данной доработки:

1. Компонентный адрес (region/municipality/locality/street/house/building/room).
2. Окружение и транспортная доступность (`location_extra`).
3. Год реконструкции, физический износ, благоустройство (`building_extra`).
4. Инженерные сети — структурированно (`building_extra.engineering`).
5. Планировка и состояние помещения (`layout`).
6. Зонирование и спец-ограничения как отдельный блок (`legal_extra`).
7. Технические, территориальные и «иные» риски (`risks`).
8. Преимущества и нотатки экономиста (`extras.advantages, notes`).
9. Меблировка (`extras.furniture`).
10. Тип процедуры (банкротство/приватизация/коммерч.) на уровне лота (`lots.procedure_type`).
11. Группировка КН в лоты (`lots` + `lot_items`).
12. Маркировка источника и confidence для каждого ЭТП-поля (`object_etp_profile.source/confidence`).

---

## 11. Verification

1. **Контракт JSON**: фикстура `tests/fixtures/etp/lot_sample.json` валидируется JSON-схемой из `docs/etp_export/03` (раздел «JSON-схема плейсхолдеров»).
2. **Рендер**: на той же фикстуре прогнать все 6 комбинаций `(3 platform × 2 mode)`, сравнить с golden-файлами в `tests/golden/etp/`.
3. **End-to-end на реальном лоте**: взять Пирушин/Сосну (есть в `parser/scripts/`), собрать `lot_pirushin_001`, выполнить `export-etp`, открыть `out/etp/lot_pirushin_001/torgi.gov.ru/description.full.txt` и `lot_appendix.pdf`, сверить с ОСВ.
4. **Условные пропуски**: фикстура с минимальным набором полей (только `identity` + `cad_number`) — проверить, что шаблон не падает и не оставляет «битых» фраз.
5. **Sanity по гэпам**: запустить экспорт без `object_etp_profile` — текст должен собраться из чисто ЕГРН-полей и явно опускать секции, для которых нет данных.

---

## 12. Outside scope

- Загрузка лотов в API ЭТП (только генерация артефактов).
- Двусторонняя синхронизация статусов торгов.
- UI для редактирования `object_etp_profile` (на этом этапе — XLSX/YAML импорт).
- Юридическая валидация формулировок описаний — остаётся за экономистом.
