# 009 — Принято: пост-S5 viewer-чистка (3 PR, §3 UI/UX, контракт не затронут)

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-20
- **Re:** 008; PR #22, #23, #24 (все merged в main); §3 (UI/UX viewer-домен)
- **Status:** closed — acknowledge, контракт остаётся 2.11.0

## Принято к сведению

Три post-S5 viewer-чистки в main — все чистый §3 UI/UX, **контракт/wire/parser не затронуты**. Возражений нет, отдельный аппрув по §3.5 не требуется (только UI-домен).

| PR  | Что                                                  | Влияние на parser |
|-----|------------------------------------------------------|--------------------|
| #22 | `_renderObjectCard` фильтрует фото-миниатюры         | нет — `photoPin_*` на карте остаются первоисточником |
| #23 | Root-cleanup: `worker.js` → `infra/cloudflare-worker/`, удалён legacy snapshot, `logic_index_html.md` → `docs/` | нет — `parser/` структура не затронута; ссылки в нашей документации/CORRESPONDENCE на старые пути не было |
| #24 | Идемпотентность `<description>` + type-aware дедуп + `markerVisible` + `_graphNodeIdOf` cross-layer + `_dedupParsedPlacemarks` propagates `graph_node_id` | нет — наш генератор уже эмитит `description` в каноне `Ключ: значение; ` без HTML (контракт §5) и `graph_node_id` в `ExtendedData` |

## Особо отмечу: type-aware дедуп (PR #24)

Это **обратное подтверждение архитектурного выбора** parser-стороны.
`08_build_kmz_v2.py` для `cad_eq_*` Placemark'а пишет `<Data name="cad_number">`
с КН **родительского здания/сооружения** (а не отдельный КН оборудования —
его не существует). До #24 был риск, что viewer спутает `cad_eq_*` с КН-объектом
по совпадению `cad_number`. Ваш ключ дедупа `type|cn` это исключает —
**parser продолжает эмитить как есть**, без правок.

То же справедливо для `cad_ben_*` (несёт `ben_inn`, не `cad_number`, так что
дедупа по cn не возникнет вовсе, но type-aware ключ — strictly more correct).

## `_dedupParsedPlacemarks` propagates `graph_node_id`

Тоже отмечаю: если viewer дедуплицирует мульти-source плейсмарки одного
объекта (например, КН из двух KMZ-слоёв), 🕸 покажется если **хоть один**
источник несёт `graph_node_id`. Это **расширяет UX** S5 на cross-layer
сценарии — спасибо. Контракт §5 требует поле для каждого Placemark'а
независимо, но parser ничего не теряет: эмитируем для всех valid маркеров,
viewer корректно мержит.

## Идемпотентность `<description>`

`_normalizeDesc` в `parseKML` (вход) + `_parseDescPairs` (display) — defensive
обработка возможного грязного на входе. Парсер эмитит чистый
`Ключ: значение; ` per контракт §5; нормализация — broader compatibility
с внешними KMZ (Google Earth Pro, сторонние редакторы). Полезно для
импорта/экспорта-цикла без потери идентичности.

## Финальное состояние S5

S5 закрыт + post-S5 чистка завершена. Из заявленного S6+:

- **multi-level Z для помещений** (MAJOR) — наиболее ожидаемый;
- **EXIF lightbox-роутинг** (viewer-инициатива, контракт не расширяется —
  поле parser-internal стабильно с 2.11.0);
- **ingesters ОСВ/ЕГРЮЛ/ЕГРИП** (parser-инициатива);
- **MessageChannel / de-sandbox** — гипотетика.

Любая команда инициирует через обычный spec-PR-first (`§3.5`).

Спасибо за быстрые чистки. До следующей итерации.

— parser-team
