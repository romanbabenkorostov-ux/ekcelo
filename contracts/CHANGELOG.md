# contracts/ CHANGELOG

## 1.2.1 — 2026-10-02

- **C7** `token 3.1.0` (копия из ekcelo-site): маршрут воркера `/file` отдаёт сам
  файл. Разовая ссылка Диска привязана к запросившему её воркеру.

## 1.2.0 — 2026-10-02

- **C7 Токен доставки** — `token/TOKEN_SPEC.md` (`token 3.0.0`), принесён из
  ekcelo-site. Токен `<payload>.<sig>` (HMAC-SHA256, 16 байт) содержит ссылку на
  публичную папку Яндекс.Диска, пути HTML и KMZ комплекта, название и срок
  действия. Подпись проверяет воркер `/token`. Выпуск из консоли —
  `tools/ekcelo_tokens.py v3`. Токен v2 не меняется.

## 1.0.0 — 2026-06-03

Первичная редакция пакета контрактов (Consistency Target v1.0). Сводит три
команды (parser / ekcelo-backend / ekcelo-site) к единой точке стыковки.

- **C1 KMZ wire** — ссылка на существующий `docs/CONTRACT_KMZ.md` (2.12.0), не меняется.
- **C2 DB §1–§6** — ссылка на `schema/egrn_current_schema.sql`; машиночитаемая выжимка → `contracts/db/` (TODO).
- **C3 Bundle** — `bundle/BUNDLE_SPEC.md` + `bundle.schema.json` (kmz+db+json+manifest).
- **C4 REST+ViewModel** — `api/openapi.yaml` + `viewmodel.schema.json` (полный REST-рендеринг).
- **C5 Lot** — `lot/LOT_SPEC.md` (include/exclude + as-of, две ветки активы∪права).
- **C6 Роли** — `roles/ROLES_SPEC.md` (контракт; реализация после веб-шва).

Governance — `docs/CONTRACT_KMZ.md` §3 (spec-PR-first) распространён на C1–C6.
