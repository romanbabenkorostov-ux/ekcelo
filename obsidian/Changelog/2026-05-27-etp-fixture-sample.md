# 2026-05-27 — PR-fixture: object_etp_profile_sample.json

## Итог
Создана read-only фикстура ЭТП-профиля для параллельной разработки viewer (рендер карточки) и parser (тест миграции DDL). Согласовано в CORRESPONDENCE/025+026.

## Артефакты
- `parser/tests/fixtures/etp/object_etp_profile_sample.json` — 3 профиля + 2 лота + 3 lot_items.
- `parser/tests/fixtures/etp/FIXTURE_NOTES.md` — назначение, структура, кейсы покрытия, контракт совместимости (имя избегает gitignore `README.md`).

## Покрытие кейсов
- **A** (КН `:31`, офис) — `source=osv, confidence=1.0`, все секции заполнены.
- **B** (КН `:42`, склад) — `source=nspd, confidence=0.65`, виден бейдж + тултип.
- **C** (КН `:7`, участок) — `source=llm, confidence=0.35`, `building_extra`/`layout` = null, приглушение текста в viewer (бонус (c) из CORRESPONDENCE/025).

Лоты: `lot:pirushin:001` (банкротство, 2 КН), `lot:sosna-rocha:042` (приватизация, 1 КН). `lot_id` формат `[A-Za-z0-9_:/-]+` ≤256 — совместимо с `graph_node_id` из `CONTRACT_KMZ §6`.

## Следующий шаг
PR-migration: `schema/migrations/0NN_etp_profile.sql` (DDL с CHECK-constraint на `lots.lot_id` regex) + правка `CLAUDE.md` §3 + тест `tests/test_etp_profile_schema.py` на загрузку этой фикстуры в БД.
