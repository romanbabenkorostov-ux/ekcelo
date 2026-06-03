# contracts/ CHANGELOG

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
