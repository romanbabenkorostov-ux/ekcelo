# workspace_contract.md

Контракт рабочей папки лота для меморандумного пайплайна.

## Что считается «рабочей папкой лота»

Корень проекта объекта (`<Название_проекта>/`) — папка, в которой оператор хранит все артефакты по лоту. **Spec НЕ описывает её содержимое за пределами подпапки `Memorandum/`** и не зависит от него.

Это соответствует парадигме `parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py` (узкое идемпотентное направление). При появлении `pirushin_sosn_rocha_07_init_project_v4.py` или изменении v3-паттерна этот файл нужно синхронизировать.

## Структура `Memorandum/` (фиксируется этим spec'ом)

```
<Название_проекта>/                      ← корень рабочей папки лота (произвольное содержимое)
└── Memorandum/                           ← подпапка направления (создаётся идемпотентно)
    ├── _data/
    │   └── enrich_<lot_id>.json          ← SSOT
    ├── incoming/                         ← канонический «вход» для market_analysis*.txt
    ├── market_template.md                ← СЛУЖЕБНЫЙ выход (идемпотентное обогащение)
    ├── final_report.md                   ← КЛИЕНТСКИЙ выход
    ├── investment_slides.md              ← КЛИЕНТСКИЙ выход (Marp-исходник)
    └── _run_log.jsonl                    ← СЛУЖЕБНЫЙ лог запусков оркестратора
```

## Идемпотентность подпапки (правила v3)

`Memorandum/` и её дети создаются по тем же правилам, что и `Surveycontract/` в `init_project_v3`:

- `parser.utils.folder_match.best_match(canonical, siblings, threshold=0.7)` — fuzzy-match имён.
- При коллизии (нашлась похожая «memorandum», «меморандум», «Memo» и т.п.) спрашивается оператор: **[1]** использовать существующую, **[2]** создать каноническую рядом, **[3]** переименовать существующую в каноническую — точно как `_resolve_existing_or_new` в v3.
- В CI/non-interactive режиме (`--yes`) — по умолчанию «использовать существующую» (consrvative), как в v3.

Повторный запуск на готовой `Memorandum/` ничего не пересоздаёт; существующие `market_template.md`, `final_report.md`, `investment_slides.md` обновляются (а не дублируются).

## Входы — fallback-цепочки поиска

| Логический вход | Где искать (по порядку, первое найденное) | Обязательность |
|---|---|---|
| SSOT `enrich_<lot_id>.json` | `Memorandum/_data/enrich_<lot_id>.json` → (если нет — Этап 1 строит из YAML + парсерного JSON) | Обязателен до Фазы 2 |
| Анализ рынка `market_analysis.txt` | `Memorandum/incoming/market_analysis*.txt` → рекурсивный поиск `^market_analysis.*\.txt$` от корня проекта (case-insensitive), первый по `mtime` | Обязателен |
| Граф `graph.html` | Явный параметр `graph_path` → рекурсивный поиск `graph.html` от корня (первый по `mtime`) | Опционален; флаг `graph_status` |
| Существующий `market_template.md` | `Memorandum/market_template.md` → рекурсивный поиск `^market_template.*\.md$` от корня (case-insensitive), первый по `mtime` | Опционален; если найден — в `existing_market_template` |

Рекурсивный поиск **пропускает** служебные директории: `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `Memorandum/_data/`. При нескольких совпадениях берётся самый свежий по `mtime`; источник пишется в `Memorandum/_run_log.jsonl` (поля `inputs.market_analysis_source`, `inputs.market_template_source`, `inputs.graph_source`).

## Выходы — канонические пути

| Файл | Тип | Описание |
|---|---|---|
| `Memorandum/market_template.md` | СЛУЖЕБНЫЙ | Идемпотентно обновлён (или создан) из тегов `<SYSTEM_MARKET_TEMPLATE>` ответа модели. Канонический путь — даже если входной шаблон был найден глубже в дереве проекта. |
| `Memorandum/final_report.md` | КЛИЕНТСКИЙ | Меморандум без служебных тегов. |
| `Memorandum/investment_slides.md` | КЛИЕНТСКИЙ | Marp-исходник презентации. Рендер в HTML/PDF — отдельная команда оператора (`marp investment_slides.md -o investment_slides.html`). |
| `Memorandum/_run_log.jsonl` | СЛУЖЕБНЫЙ | Лог запусков оркестратора. |
| `Memorandum/_data/enrich_<lot_id>.json` | SSOT | Обновлён, если Фаза 1 получала недостающие поля от оператора. |

## Сетка соответствия YAML-карточек ↔ ключи SSOT

| YAML-карточка (опц.) | Ключ в `enrich_<lot_id>.json` |
|---|---|
| `target_scenario.yaml` | `target_scenario` (объект `{was, trigger, to_plan}`) |
| `documents_dates.yaml` | `documents_dates[]` |
| `gpzu_minkult.yaml` | `gpzu_minkult` |
| `field_inspection.yaml` | `field_inspection` |
| `photo_album_index.yaml` | `photo_album` |
| ЭТП-профиль (если есть) | `etp_profile` (см. `parser/tests/fixtures/etp/object_etp_profile_sample.json`) |
| Парсерный JSON (ЕГРН) | `egrn` (под ключом `egrn.tables` — как выдаёт `parser/egrn_parser/exporters/json_exporter.py`) |

Если YAML-карточки нет — Этап 1 (`01_intake_and_pipeline.md`) интерактивно соберёт данные у оператора и запишет в SSOT с пометкой в `missing_layers[]`.

## Команды для генерации входов

- Парсерный JSON ЕГРН (фрагмент для SSOT):

  ```bash
  python -m egrn_parser export --json out.json
  ```

  → положить в `Memorandum/_data/enrich_<lot_id>.json` под ключ `egrn.tables`.

- Граф связей:

  ```bash
  python parser/scripts/04_nspd_graph_v14.py --output <path>/graph.html
  ```

  → положить `graph.html` в любое удобное место под корнем проекта; spec найдёт рекурсивно.

- Рендер Marp-презентации:

  ```bash
  cd <project>/Memorandum/
  marp investment_slides.md -o investment_slides.html
  marp investment_slides.md -o investment_slides.pdf --pdf
  ```

## Темпоральный контракт

Каждый факт SSOT сопровождается `provenance`:

```json
{
  "document_id": "<строковый ID документа>",
  "as_of_date": "YYYY-MM-DD",
  "evidence_level": 1
}
```

- `evidence_level = 1` — `registered_date` (когда данные зарегистрированы в реестре). Приоритет.
- `evidence_level = 2` — `document_date` (когда сформирован документ выписки). Ниже приоритетом.

Правило разрешения конфликтов:

1. Свежее `as_of_date` побеждает более старое.
2. При равных датах: `evidence_level=1` (registered) побеждает `evidence_level=2` (document_date).
3. При полном равенстве: оба факта попадают в `conflicts[]` SSOT, меморандум явно отмечает «конфликт не разрешён» в Преамбуле.

## Предупреждение для разработчиков

При появлении `pirushin_sosn_rocha_07_init_project_v4.py` (который, скорее всего, будет создавать `Memorandum/` инициализатором по парадигме v3) или при изменении v3-паттерна нужно:

- синхронизировать этот файл (структура подпапок, имена выходов);
- обновить `orchestrator_spec.md` §3 (модуль `workspace.py` должен переиспользовать новую реализацию);
- проверить smoke-тесты в `orchestrator_spec.md` §7.
