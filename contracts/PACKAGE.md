# contracts/ — Consistency Target v1.0 (пакет контрактов EKCELO)

> **Источник истины** для стыковки трёх команд: `parser` (локальные парсеры),
> `ekcelo` (бэкенд), `ekcelo-site` (фронтенд). Пакет vendored/синхронизируется
> во все три кодовые базы. Источник живёт здесь (`ekcelo/contracts/`); остальные
> базы держат копию и сверяют хеш в CI.

**Версия пакета:** `contracts v1.0.0` (SemVer; см. §Версионирование).
**Governance:** правила изменения — `docs/CONTRACT_KMZ.md` §3 «spec-PR-first» +
дуальная мажоритарность, распространённые на все контракты C1–C6.

---

## Состав (6 контрактов)

| ID | Контракт | Файл | Эмитент | Потребитель |
|----|----------|------|---------|-------------|
| **C1** | KMZ wire (2.12.0) | `docs/CONTRACT_KMZ.md` + `KML_INGESTION_SPEC…v2.10.0.md` | parser (08) | фронт (локаль/скачивание), Google Earth Pro |
| **C2** | DB-схема §1–§6 | `contracts/db/` ← `schema/egrn_current_schema.sql` | parser (egrn_parser) | backend (импорт) |
| **C3** | Bundle | `contracts/bundle/BUNDLE_SPEC.md` + `bundle.schema.json` | parser ⇄ backend | обе (round-trip) |
| **C4** | REST-API + ViewModel | `contracts/api/openapi.yaml` + `viewmodel.schema.json` | backend | фронт |
| **C5** | Lot model | `contracts/lot/LOT_SPEC.md` | parser+backend | фронт |
| **C6** | Роли и шеринг | `contracts/roles/ROLES_SPEC.md` | backend | фронт |

## Связующая идея — нормализованная ViewModel

Веб-шов = **полный REST-рендеринг**. Фронт рисует не KMZ и не сырой ответ API, а
**нормализованную ViewModel** (C4). Два адаптера дают её эквивалентно:

```
        ┌─ KMZ (C1) ─► kmz→ViewModel ─┐
ViewModel ┤                            ├─► ui (Leaflet / React)
        └─ REST (C4) ─► api→ViewModel ─┘
```

ViewModel описывает объект/лот через **4 характеристики EKCELO**:
`physical` (что) · `ownership` (чьё) · `geo` (где) · `temporal` (когда),
каждое поле несёт `source` + `confidence` (для ЭТП-слоя §6).

## Definition of Convergence («стали консистентны»)

На одном реальном лоте все 4 пункта зелёные:
1. parser выпускает **Bundle vN** (manifest фиксирует `contracts vX.Y.Z`).
2. backend идемпотентно **импортирует** Bundle в БД §1–§6, отдаёт **ViewModel** по REST, умеет **реэкспортировать** тот же Bundle.
3. фронт **рендерит ViewModel из REST** и **открывает тот же KMZ локально** — картинка идентична.
4. round-trip `export → import → export` идемпотентен: `sha256(project.kmz)` и набор id в БД стабильны.

## Версионирование

`contracts MAJOR.MINOR.PATCH`. Любое изменение контракта = PR в `contracts/` +
bump SemVer + запись в `contracts/CHANGELOG.md` + ack доменной команды до кода
(домены: данные→parser/backend, UI/UX→frontend, кросс→обе + арбитр-владелец).
KMZ-контракт (C1) сохраняет собственный SemVer (сейчас 2.12.0); пакет ссылается
на него по pin-SHA, как уже описано в `docs/CONTRACT_KMZ.md` §5.

## Синхронизация во все три базы

- Источник: `ekcelo/contracts/`.
- `ekcelo-site` и репо парсеров держат копию `contracts/` + файл
  `contracts/.sync` с `contracts_version` и `sha256` дерева.
- CI каждой базы падает, если локальная копия разошлась с pin-версией.
