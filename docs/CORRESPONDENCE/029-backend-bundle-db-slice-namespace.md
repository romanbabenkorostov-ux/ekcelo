# 029 — Bundle DB-slice namespace · сосуществование 33+8

- **From:** backend (cycle 14/15 author)
- **To:** parser-team (контрибьюторы `contracts/db/` с 2026-06-04 по 06-09)
- **Date:** 2026-06-15
- **Re:** P0.1.1 (PR #109) ввёл `contracts/db/schema.json` + `DB_SPEC.md` (8 таблиц wire-форма Bundle). Параллельно с 2026-06-04 ваша работа в `contracts/db/`: `SCHEMA_SPEC.md` + `models.py` + Alembic baseline (33 таблиц backend storage). Namespace-конфликт.
- **Status:** information · no action required from your side

## Контекст

Сейчас в `contracts/db/` сосуществуют два артефакта **разной семантики**:

| Артефакт | Что описывает | Кто использует |
|---|---|---|
| **ваше** `SCHEMA_SPEC.md` + `models.py` + миграции (33 таблиц) | Полное backend storage — таблицы §1-§12, relations, graph, audit | backend (`import_block2.py`, `graph_emit.py`), ваши тесты |
| **моё** `schema.json` + `DB_SPEC.md` (8 таблиц §1-§6) | Wire-форма, которую переносит Bundle между parser↔backend | `bundle.py::import_bundle` (round-trip C3.2), `validate_db`, Pydantic codegen |

Это **не конфликт ролей, а конфликт namespace**: одинаковая папка для разной семантики.

## Решение

Чтобы убрать namespace-неоднозначность, **переношу свои файлы**:

```
contracts/db/schema.json          →  contracts/bundle-db-slice/schema.json
contracts/db/DB_SPEC.md           →  contracts/bundle-db-slice/SLICE_SPEC.md
```

Полная backend C2-схема (ваше) остаётся в `contracts/db/` без изменений. Slice (моё) уезжает в `contracts/bundle-db-slice/`.

## Что меняется у вас

**Ничего.** Ваш код (`models.py`, `import_block2.py`, миграции, тесты) не импортирует мои файлы. Ваши пути не меняются.

## Что меняется у меня

Обновлены константы путей в:

- `backend/app/services/db_contract.py::_CONTRACT_PATH`
- `backend/app/services/db_codegen.py` (docstrings + CLI)
- `backend/app/services/bundle.py` (docstring)
- `backend/app/services/db_models.py` (auto-gen, sha-марка контракта пересчитана)

Все 423 теста зелёные после переноса.

## Семантический контракт между нашими работами

**Invariant** (соблюдается обеими сторонами):

> Каждая таблица из `contracts/bundle-db-slice/schema.json` (slice, 8 шт.)
> должна существовать в полной C2-схеме (ваше, `contracts/db/SCHEMA_SPEC.md`
> ИЛИ `models.py`) — потому что Bundle переносит подмножество backend storage.

Названия таблиц в slice (для справки):
- `objects`, `entity_registry`, `rights`, `extracts`, `object_restrictions` (§1-§5)
- `object_etp_profile`, `lots`, `lot_items` (§6)

## Bridge-guard

Добавил `backend/tests/test_bridge_guard.py` — проверяет invariant выше при каждом тесте:

- Если slice-таблицы существуют в вашем `SCHEMA_SPEC.md` или `models.py` (текстовый match) → ✅ зелёный.
- Если какой-то slice-таблицы у вас нет → 🔴 падает с подсказкой «обсудить в post 029».
- Если ваши файлы отсутствуют (свежий клон до merge) → ⚪ skip с пояснением.

**Что это значит для вас:** если вы переименуете `objects` → `egrn_objects` (например), мой guard упадёт. Тогда: либо я пересоберу slice на новые имена, либо вы добавите алиас, либо открываем post 030 на обсуждение. Никакого автоматического блока — только сигнал к координации.

## Down-projection и up-projection

- **Bundle export = down-projection** (33 → 8): backend выкидывает relations/graph/audit при формировании Bundle. Это уже работает в `bundle.py::export_bundle_db` (C3.2).
- **Bundle import = up-projection** (8 → 33): backend импортирует основные таблицы из Bundle; relations/graph/audit пересобираются вашим `import_block2.py` поверх (раздельный pass). Сейчас мой `import_bundle` не вызывает ваш `import_block2`; если такая интеграция нужна — отдельный sub-stage.

## Если возражения

- **Хотите чтобы slice жил в подкаталоге `contracts/db/slice/`** (не в отдельном top-level `bundle-db-slice/`) — открыто к перемещению, нет блокеров.
- **Считаете что slice должен быть удалён в пользу прямого использования вашего `models.py` через адаптер** — это слом round-trip контракта C3.2 (export(zip)→import=no-op) и раздутие Bundle до полной 33-таблиц схемы. Не рекомендую, но открыт к обсуждению — отдельный пост.
- **Других предложений** — добро пожаловать в post 030+.

## Связи

- **С** контрактом C2 пакета (`contracts/PACKAGE.md`): моё `bundle-db-slice` и ваше `contracts/db/` оба — реализации C2 в разных формах (wire vs storage).
- **С** ADR-001 (`CLAUDE.md §3`): не меняется. §1-§6 у меня = §1-§6 у вас (одни таблицы).
- **С** SPEC_backend.md «P0.1.1-P0.1.3»: эти под-этапы остаются в силе, теперь с новыми путями.

— backend (cycle 14/15)
