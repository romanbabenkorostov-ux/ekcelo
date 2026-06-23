# 2026-06-23 — Cycle 15 M5: фильтр `/catalog` по VIEW-грантам

## Задача
Roadmap §Cycle 15 M5 (опц.): client/assessor в каталоге должен видеть только
объекты/лоты, на которые у него есть `VIEW`-грант. Сейчас `/catalog` отдаёт
весь список — это утечка имён/адресов мимо C6 ROLES_SPEC.

## Решение
**Пост-фильтр** (а не SQL): `build_catalog` строит полный список как и раньше,
затем `/catalog`-роут отсеивает карточки, для которых `can(principal, VIEW,
Resource(kind, id))` = False. Так не дублируем матрицу прав в SQL и сохраняем
ту же логику, что в `require_action` (superadmin минует, client read-only
для VIEW допустим, expires_at учитывается).

Активация — **opt-in**: только если `enforce_rbac=True` И `grant_store` есть.
Иначе no-op (полный backward-compat — критично для cycle 14 без RBAC).

## Файлы
- ✏️ `lot_orchestrator_web/rbac_api.py` — `filter_catalog_by_grants(cards,
  principal, store)`; маппинг `card.kind → ResourceType`; неизвестный kind →
  выкидываем (безопаснее).
- ✏️ `lot_orchestrator_web/main.py` — в `catalog_endpoint` после `build_catalog`
  и до `model_dump` применяем фильтр (lazy import во избежание цикла).
- ✨ `lot_orchestrator_web/tests/test_rbac_catalog_filter.py` — 8 тестов.

## Тесты (8 новых)
1. enforce_rbac=False → все карточки видны без auth (backward-compat).
2. enforce_rbac=True + superadmin → видит всё (без грантов).
3. assessor без грантов → `[]`.
4. assessor с VIEW-грантом на 1 объект → видит только его.
5. client с VIEW-грантом на лот → видит его (VIEW не в `_CLIENT_DENIED`).
6. q + grant-фильтр — пересечение (q=«Сочи» при грантах на :31/:33 → только :33).
7. kind=lot + смешанные гранты на object+lot → только разрешённые лоты.
8. Грант на EXPORT (не VIEW) → каталог пуст (action-specific).

## Тесты — regression
- **lot_orchestrator_web: 297 passed** (289 baseline + 8 M5).
- **parser smoke: 33/33**.

## Не в scope (отложено)
- SQL-пушдаун (фильтр в `WHERE`) — оптимизация под большие БД; сейчас пост-фильтр
  достаточен (каталог = единицы сотен, не миллионы).
- Фронт сейчас уже использует `/catalog` через `api.getCatalog` (FE-3) — никаких
  правок не требует, сервер вернёт уже отфильтрованный JSON.

## Канал доставки
zip-handoff (sandbox-proxy блокирует push).
