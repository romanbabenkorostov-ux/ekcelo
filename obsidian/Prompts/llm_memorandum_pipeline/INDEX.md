# llm_memorandum_pipeline / INDEX

Spec промпт-пайплайна меморандума недвижимости + спецификации оркестратора лота.

Не затрагивает `parser/`, `viewer/`, `schema/`, `CONTRACT_KMZ.md`. Все правки — внутри этой папки.

## Что это

Сквозной пайплайн «парсерный JSON + анализ рынка ФСО №7 → инвестиционный меморандум + Marp-презентация», с идемпотентным обогащением шаблона рынка и темпоральной разметкой фактов.

Три слоя данных склеиваются в SSOT (`enrich_<lot_id>.json`):
1. **Юридический** — ЕГРН (собственники, права, КН, условные номера, площади).
2. **Градостроительный** — ГПЗУ/Минкульт (зоны охраны ОКН, археология, ПЗЗ).
3. **Физический** — полевой осмотр (состояние, износ, перепланировки, оборудование).

Плюс **триада сценария** (`target_scenario`): что было / триггер / что планируется — управляет фильтром рисков (СПЯЩИЕ vs КРИТИЧЕСКИЕ).

## Режимы использования

### 1. Ручной (через claude.ai, без кода)

Оператор последовательно копипастит:

1. `01_intake_and_pipeline.md` + парсерный JSON → получает `enrich_<lot_id>.json`.
2. `02_memorandum_prompt.md` + SSOT + `market_analysis.txt` → получает единый ответ, в котором:
   - блок `<SYSTEM_MARKET_TEMPLATE>...</SYSTEM_MARKET_TEMPLATE>` (служебный шаблон рынка),
   - меморандум (5 разделов),
   - маркер `<!-- MARP_START -->`,
   - Marp-исходник презентации.
3. Руками режет ответ по маркерам в три файла: `Memorandum/market_template.md`, `Memorandum/final_report.md`, `Memorandum/investment_slides.md`.
4. (Опц.) `03_presentation_prompt.md` — если нужна отдельная пересборка презентации.
5. (Опц.) `marp investment_slides.md -o investment_slides.html` — рендер презентации.

### 2. Через оркестратор (после реализации по `orchestrator_spec.md`)

`POST /lots/{lot_id}/run` — оркестратор делает всё сам, маршрутизация и перехват служебных тегов автоматические.

## Точки входа

- **Новичкам** — `USER_GUIDE.md` (подробный туториал «за руку»).
- **Технический quickstart** — `QUICKSTART.md`.
- **Контракт рабочей папки и имена файлов** — `workspace_contract.md`.
- **Команде разработки оркестратора** — `orchestrator_spec.md`.
- **Промпты** — `01_intake_and_pipeline.md`, `02_memorandum_prompt.md`, `03_presentation_prompt.md`.
- **Переиспользуемый блок Context Injection** — `market_injector_prompt_block.md`.

## Чек-лист оператора (ручной режим, 10 шагов)

1. Открыть свою рабочую папку проекта (`<Название_проекта>/`).
2. Запустить парсер (`parser/scripts/04_nspd_graph_v14.py` + экспорт `egrn_parser`) — получить `graph.html` и парсерный JSON.
3. Создать `Memorandum/` в корне проекта (если её нет — оркестратор/мастер создаст идемпотентно).
4. Заполнить YAML-карточки по шаблонам из `templates/` (минимум — `target_scenario.yaml` + `documents_dates.yaml`).
5. Скопировать `01_intake_and_pipeline.md` в claude.ai, приложить парсерный JSON и YAML-карточки → получить `Memorandum/_data/enrich_<lot_id>.json`.
6. Положить `market_analysis.txt` (сырой анализ рынка по ФСО №7) в `Memorandum/incoming/`.
7. Скопировать `02_memorandum_prompt.md` в claude.ai, приложить SSOT и `market_analysis.txt` → получить единый ответ.
8. Разрезать ответ по маркерам в `Memorandum/market_template.md`, `Memorandum/final_report.md`, `Memorandum/investment_slides.md`.
9. (Опц.) `marp investment_slides.md -o investment_slides.html`.
10. Передать заказчику комплект из `Memorandum/`.

## Темпоральный контракт (коротко)

Каждый факт в SSOT снабжается `provenance = {document_id, as_of_date, evidence_level}`:

- `evidence_level=1` — `registered_date` (когда зарегистрировано в реестре, приоритет).
- `evidence_level=2` — `document_date` (когда сформирован документ выписки, ниже).

Правило конфликтов: «новее > при равных датах registered побеждает document_date». Подробнее — в `02_memorandum_prompt.md` и `workspace_contract.md`.

## Парадигма размещения (init_project v3)

Меморандумные артефакты живут в `<project>/Memorandum/` — параллельной подпапке направления (по образцу `Surveycontract/` из `parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py`). Структура корня проекта за пределами `Memorandum/` этим spec'ом не описывается.
