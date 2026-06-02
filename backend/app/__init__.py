"""backend/app — структурная обёртка под fastapi/full-stack-fastapi-template.

Не содержит логики. Только re-export уже существующих модулей:
- `lot_orchestrator/` — backend ядро (CLI меморандум-пайплайн)
- `lot_orchestrator_web/` — FastAPI обёртка (web + persistence + pub/sub)
- `parser/` — ETL парсер ЕГРН + ЭТП-экспортёр

Цель: дать пользователю / новому контрибьютеру знакомый layout
(`backend/app/{api,core,models,crud,services}/`), не меняя ни одной строчки
логики. См. `obsidian/Architecture/system-state-2026-05-30.md` раздел
«Архитектурные паттерны».
"""
