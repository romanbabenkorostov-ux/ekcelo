# llm_memorandum_pipeline — QUICKSTART

> Имя `QUICKSTART.md` (а не `README.md`) — глобальный `.gitignore` репо исключает все `README.md`.

Spec промпт-пайплайна меморандума недвижимости + спецификация оркестратора лота. Хранится в `obsidian/Prompts/llm_memorandum_pipeline/`.

## Точки входа

- **Новичкам** — `USER_GUIDE.md` (туториал «за руку»).
- **Обзор всего spec'а** — `INDEX.md`.
- **Контракт рабочей папки** — `workspace_contract.md`.
- **Команде разработки оркестратора** — `orchestrator_spec.md`.

## Quickstart (ручной режим)

```
# 1. Парсерный JSON
python -m egrn_parser export --json out.json

# 2. Граф
python parser/scripts/04_nspd_graph_v14.py --output <project>/graph.html

# 3. YAML-карточки (по шаблонам из templates/)
cp templates/target_scenario.yaml.tpl <project>/target_scenario.yaml  # заполнить
cp templates/documents_dates.yaml.tpl <project>/documents_dates.yaml  # заполнить

# 4. Этап 1 в claude.ai → 01_intake_and_pipeline.md + out.json + YAML → enrich.json
#    Сохранить в <project>/Memorandum/_data/enrich_<lot_id>.json

# 5. Этап 2 в claude.ai → 02_memorandum_prompt.md + enrich.json + market_analysis.txt
#    Разрезать ответ по тегам/маркерам → Memorandum/{market_template,final_report,investment_slides}.md

# 6. (Опц.) Marp-рендер
cd <project>/Memorandum/ && marp investment_slides.md -o investment_slides.html
```

## Quickstart (через оркестратор, после реализации)

```bash
POST /lots/<lot_id>/run  body: {"workspace_path": "<project>"}
```

Оркестратор сам пройдёт 4 фазы и положит выходы в `<project>/Memorandum/`.

## Структура папки

```
llm_memorandum_pipeline/
├── INDEX.md                              ← точка входа
├── QUICKSTART.md                         ← этот файл
├── USER_GUIDE.md                         ← подробный туториал
├── workspace_contract.md                 ← контракт рабочей папки
├── 01_intake_and_pipeline.md             ← Этап 1 (приёмщик SSOT)
├── 02_memorandum_prompt.md               ← Этап 2 (меморандум + Marp)
├── 03_presentation_prompt.md             ← Этап 3 (опц., отдельная Marp-пересборка)
├── market_injector_prompt_block.md       ← переиспользуемый блок Context Injection
├── orchestrator_spec.md                  ← спецификация оркестратора (для разработчиков)
├── templates/                            ← скелеты YAML и SSOT
└── examples/                             ← заполненные примеры
```

## Парадигма

Меморандумные артефакты живут в `<project>/Memorandum/` — параллельной подпапке направления (по образцу `Surveycontract/` из `parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py`). Структура корня проекта за пределами `Memorandum/` этим spec'ом не описывается.
