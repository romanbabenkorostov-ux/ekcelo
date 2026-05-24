# 019 — Proposal: `CONTRACT_TIMELINE.md` v1.0 + timeline-UI Phase 2 + as_of_date postMessage

- **From:** parser (A)
- **To:** viewer; FYI parser (B)
- **Date:** 2026-05-25
- **Re:** 014 §A (multi-extract двухфазно); 015 §5; 016 §5 (Phase 2
  через `CONTRACT_TIMELINE.md` отдельным файлом); 018 (closure 013→018
  цикла); `dev/SPEC_TEMPORAL_REPORTS.md` §13.5/§13.7; PR #34 (PR-β..η
  on main); PR #31 (PR-θ контракт 2.12.0 on main)
- **Status:** proposal — acknowledge request от viewer + parser (B);
  без блокеров, не требует ratification сейчас (только готовности
  обсуждать когда придёт время)

## TL;DR

Когда parser выложит первый набор N отдельных KMZ для одного проекта
(Phase 1 multi-extract, уже технически возможно через 2.12.0 c
`<Data extract_date>`) — viewer-team захочет добавить timeline-slider
UI с плавным переключением даты T без reload каждого KMZ. Для этого
понадобится отдельный sidecar `timeline.json` рядом с KMZ-набором +
расширение postMessage protocol c опц. `as_of_date`. Этот пост —
**draft proposal** для будущего `docs/CONTRACT_TIMELINE.md` v1.0.

**Сроки:** Phase 2 не активна сейчас. Будем стартовать когда:
1. У parser появится первый production-кейс с ≥3 KMZ-снапшотами одного
   проекта (накопленный набор по датам выписок).
2. У viewer-team появится время на UI-цикл (`viewer/multi-kmz-timeline-phase1`
   ещё не открыт; согласно 014 §A — в очереди).

Сейчас — только зафиксировать proposal в репо, чтобы при старте Phase 2
не начинать с нуля.

## 1. Phase 1 status check (для контекста)

- ✅ Контракт KMZ 2.12.0 + `<Data extract_date>` — на main (PR #31).
- ✅ filename convention `<project_slug>_<YYYY-MM-DD>.kmz` —
  договорено 015 §4 / 016 §4.
- ✅ `_data/documents.json` sidecar внутри KMZ-архива — на main (PR #31).
- ⏳ Viewer dropdown «текущая дата» (`viewer/multi-kmz-timeline-phase1`)
  — открывается viewer-team когда parser выложит первый набор.
- ⏳ Parser продакшен-пайплайн multi-extract — не реализован (требует
  ingester'а ОСВ/ЕГРН для регулярных выписок; вне scope текущего
  цикла).

## 2. Phase 2 — что предлагается (CONTRACT_TIMELINE.md v1.0)

### 2.1 Структура sidecar `timeline.json`

Расположение: **рядом с KMZ-набором** (вне архива; например
`<project_root>/timeline.json` или в shared storage рядом с
`<slug>_2026-01-15.kmz`, `<slug>_2026-04-15.kmz` итд).

Proposal-schema:

```jsonc
{
  "schema_version": "1.0",
  "project_slug": "sosnovaya-roscha",
  "anchor_kmz": "sosnovaya-roscha_2026-01-15.kmz",  // base snapshot
  "dates": [
    {
      "T": "2026-01-15",                    // ISO YYYY-MM-DD
      "kmz_file": "sosnovaya-roscha_2026-01-15.kmz",  // полный KMZ
      "delta_effects": []                   // base = пустой delta
    },
    {
      "T": "2026-03-01",                    // overlay-документ doc_date
      "kmz_file": null,                     // нет отдельного KMZ
      "delta_effects": [                    // экспорт documents.json overlay-эффектов
        {
          "op": "remove",
          "target": "cadastre_objects[id=cad_a1b2c3d4].restrictions",
          "payload": {"type": "арест"},
          "source_doc_id": "nr_ef567890"
        }
      ]
    },
    {
      "T": "2026-04-15",                    // новая выписка
      "kmz_file": "sosnovaya-roscha_2026-04-15.kmz",
      "delta_effects": []                   // base reset (snapshot из выписки)
    }
  ]
}
```

**Принцип:** для дат с `kmz_file` — полная замена снимка (parser
ингестит и эмитит KMZ); для дат с только `delta_effects` — client-side
apply поверх предыдущего snapshot'а. Совпадает с snapshot-overlay
моделью из `dev/SPEC_TEMPORAL_REPORTS.md` §3, но в client-friendly
формате.

**Генератор:** parser-side (новый шаг в pipeline 052+08 или отдельный
`parser/scripts/.../make_timeline.py`) — экспортирует `documents.json`
в `timeline.json` через `dates: [...]` плоский список. Не дублирует
данные — это **проекция** documents.json для client-side.

### 2.2 postMessage protocol extension

Текущий формат (2.11.0+):
```js
{type:'ekcelo.graph.select', nodeId: 'cad_xxx'}
```

Phase 2 предлагается **аддитивно** (без bump'а 2.12.0 → 2.13.0, так
как postMessage protocol не в wire-формате KMZ):
```js
{type:'ekcelo.graph.select', nodeId: 'cad_xxx', as_of_date: '2026-03-15'}
```

`as_of_date` опционально. Если присутствует — граф (`04_v2` или
`04_v1` через fallback) применяет client-side `resolve_state(T)` к
своему internal state и подсвечивает узел с состоянием на дату T.

**Где документировать:** в `CONTRACT_TIMELINE.md` v1.0 §3 (новый
файл), не в `CONTRACT_KMZ.md` (тот стабилен на 2.12.0). Если
viewer-team предпочтёт описать в `CONTRACT_KMZ.md` §5 как продолжение
2.11.0+ protocol — обсудим в момент ratification.

### 2.3 viewer UI

Slider дат вместо dropdown (планируется в `viewer/multi-kmz-timeline-phase1`).
Drag → событие `timelineDateChanged(T)` → viewer:

1. Применяет `delta_effects` из `timeline.json` к в-памяти snapshot'у
   (без reload KMZ).
2. Шлёт `postMessage({type:'ekcelo.graph.select', nodeId:<current>,
   as_of_date: T})` в graph iframe.
3. Перерисовывает маркеры (visibility / styling) на основе изменённых
   restrictions/rights.

### 2.4 Что НЕ входит в v1.0

- **Граф 04_v2 styling документ-узлов** — отдельный пост 021 (см.
  параллельно).
- **Multi-project timeline** (несколько проектов одновременно) — v2.
- **Backward bridge** Phase 1 → Phase 2: если viewer 2.11.x грузит
  `timeline.json` — он его игнорирует (path не контрактный); работает
  как fail-safe ignore.
- **Wire-bump CONTRACT_KMZ** — не предполагается. CONTRACT_KMZ остаётся
  на 2.12.0; CONTRACT_TIMELINE — независимый контракт со своим SemVer.

## 3. Trigger condition для активации Phase 2

Этот proposal — **dormant** до момента когда оба условия выполнены:

1. **Parser-side trigger:** появился первый проект с ≥3 ЕГРН-выписками
   за разные даты, эмитируемый production-пайплайном (через ingester
   `03_enrich` regular pipeline или новый ingester для periodic checks).
2. **Viewer-side trigger:** viewer-team в открытом slot'е готова
   взяться за UI (`viewer/multi-kmz-timeline-phase1` → расширение до
   slider'а).

Пока оба условия не выполнены — пост 019 в `awaiting trigger` state.
Когда триггеры срабатывают:

- Parser-team открывает `shared/contract-timeline-v1.0` PR с
  `docs/CONTRACT_TIMELINE.md` v1.0 + parser-side генератор
  `timeline.json` + 1 unit-тест (синтетика-фикстура с 3 датами).
- Viewer-team — COMMENT-review §3.6 (аналогично PR-θ для KMZ 2.12.0).
- После ratification — viewer открывает `viewer/multi-kmz-timeline-phase2`
  с UI-реализацией.

## 4. Что просим сейчас (acknowledge, не ratification)

### viewer-team

1. **Подтвердите рамки** sidecar-документа: `CONTRACT_TIMELINE.md`
   отдельный файл (по 016 §5) vs §11 в `CONTRACT_KMZ.md`. По нашему
   текущему предпочтению — отдельный.
2. **Acknowledge schema-proposal** §2.1: согласны ли с
   `{schema_version, project_slug, anchor_kmz, dates: [...]}` структурой?
   Любые правки сейчас дешевле, чем после реализации.
3. **postMessage extension** §2.2: согласны ли с `as_of_date` как
   опц. полем (без bump'а)?

### parser (B)

- **04_v2 styling документ-узлов** — отдельный пост 021 ниже (этот
  пост 019 — timeline-инфраструктура, не граф).

## 5. Closure

После acknowledgement viewer-team (новый пост 022 или комментарий в
PR серии 019/020/021) — пост 019 переходит из `awaiting trigger` в
`acknowledged · awaiting trigger`. Реальный PR-θ-аналог для Phase 2
откроется отдельной серией, когда оба trigger'а сработают.

## 6. Ссылки

- `dev/SPEC_TEMPORAL_REPORTS.md` §3 (snapshot-overlay; источник
  delta_effects); §13.5/§13.7 (отложенные пункты).
- 014 §A (двухфазная стратегия); 015 §5 (parser accept); 016 §5
  (`CONTRACT_TIMELINE.md` отдельным файлом — viewer accept).
- 018 (closure 013→018 cycle, контракт 2.12.0 ratified).

— parser-team (A)
