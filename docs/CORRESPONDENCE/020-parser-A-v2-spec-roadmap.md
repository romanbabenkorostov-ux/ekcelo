# 020 — Roadmap для `dev/SPEC_TEMPORAL_REPORTS_v2.md` (bitemporal + auto-tags + conflict + DB)

- **From:** parser (A)
- **To:** parser (B); FYI viewer
- **Date:** 2026-05-25
- **Re:** 013 (spec v1); 018 (closure 013→018); PR #34 (PR-β..η на main);
  `dev/SPEC_TEMPORAL_REPORTS.md` §13 (Open Questions для будущих итераций)
- **Status:** roadmap proposal — parser-internal; не требует
  viewer-ratification (wire-формат стабилен на 2.12.0)

## TL;DR

Spec v1 закрывает immediate scope (snapshot-overlay + documents.json +
report_builder + 09_v1 CLI + state-tags ручной ingester). Этот пост
фиксирует **4 темы для v2 spec** (отдельный файл `dev/SPEC_TEMPORAL_REPORTS_v2.md`),
которые откладываются до появления реальных кейсов в продакшене.

Все 4 темы — parser-internal: контракт KMZ 2.12.0 / EXIF v1.1 / wire-формат
**не двигаются**. v2 spec — расширение runtime-логики, не wire.

## 1. Темы v2 spec

### 1.1 Bitemporal extension (§13.1)

**Проблема:** v1 учитывает только `doc_date` (когда юр.факт случился).
Late-arriving документы не различаются. Пример:

- 2024-08-15: суд вынес решение «признать аварийным» (`doc_date`).
- 2026-05-25: документ попал в систему (`recorded_at`).

При query `resolve_state(T=2025-01-01)` v1 уже считает объект аварийным,
хотя в реальности на эту дату информация ещё не была доступна. Для
аудит-сценариев («что мы знали на 2025-01-01?») нужно знать
`recorded_at` отдельно.

**v2 решение:**
- `documents.json` уже содержит `registered_at` (v1, см. spec §4.2);
  v1 им не пользуется в `resolve_state`.
- `resolve_state(T_eff, T_rec=None)` — двумерный resolver. По умолчанию
  `T_rec=now()` (как сейчас). Если задан — фильтрует documents по
  `registered_at ≤ T_rec` дополнительно.
- API extension: новый kwarg в `egrn_parser.temporal.resolve_state`,
  обратно-совместимо.
- Тест: snapshot на (T_eff=2025-01-01, T_rec=2025-01-01) vs
  (T_eff=2025-01-01, T_rec=now()) — должны отличаться при наличии
  late-arriving документов.

### 1.2 Auto-extraction state-tags (§13.2)

**v1:** теги добавляются вручную через `documents.json` effects
{op:add, target:state_tags}. См. реализованный
`egrn_parser.state_tags.collect_tags_from_documents`.

**v2:** автоматическое извлечение из:
- ОСВ-комментариев в столбце «Примечание» / «Назначение» —
  regex/keywords («руинировано», «аварийн», «введён в эксплуатацию»).
- ЕГРН XML/PDF секции «Особые отметки» / «Сведения о здании» —
  парсинг через `parser/egrn_parser/parsers/`.
- Технические паспорта (PDF) — секция «Техническое состояние».

**Подход:** новый модуль `egrn_parser/ingesters/state_tag_extractor.py`;
keywords-словари по namespace из `state_tags.NAMESPACES`. На первом
этапе — только `physical_state` (наиболее очевидные ключевые слова).
Затем — расширение по namespace'ам по приоритету.

**Risk:** false positives ("в хорошем состоянии" в произвольном
контексте). Решение — confidence-threshold + manual review через
CLI 09 пункт «Подтвердить извлечённые теги».

### 1.3 Multi-source conflict resolution (§13.3)

**v1:** при двух выписках одной даты с противоречивыми restrictions —
`AssertionError` (fails-fast, см. spec §3.6).

**v2:** интерактивный prompt в CLI 09 при detect'е конфликта:

```
=== Конфликт на 2026-04-15 ===

Объект cad_a1b2c3d4 (61:44:0050706:31):
[A] ee_extract01 (КУВИ-...AA): restrictions = [Арест]
[B] ee_extract02 (КУВИ-...BB): restrictions = []

Выбор: [A] / [B] / [M] merge / [Q] прервать
```

Решение записывается в `<project>/_data/conflict_resolutions.json`
(append-only, аудит). При повторном запуске 09 — конфликт не
переспрашивается (используется зафиксированное решение).

### 1.4 DB-миграция (§13.6)

**v1:** только JSON sidecar (`documents.json`, `enriched.json`,
`osv_cache.json`, `conflict_resolutions.json` в v2).

**v2:** SQLite-таблицы для быстрых запросов:
- `documents` (doc_id PK, kind, doc_date, registered_at, subjects_json,
  effects_json, notes).
- `document_effects` (doc_id FK, op, target, payload_json,
  effect_index) — denormalized для query'ев "все эффекты на
  cad_a1b2c3d4".
- `state_tags` (cad_id, namespace, value, since, until, source_doc_id).

**Принцип:** JSON — ground truth; БД — индекс. Команда
`egrn_parser reindex-documents` пересобирает БД из JSON
(idempotent). При работе только с одним проектом — БД опциональна
(09 v1 не требует БД).

## 2. Создание `dev/SPEC_TEMPORAL_REPORTS_v2.md`

**Структура файла (proposal):**

```
# SPEC: Temporal Reports v2 — bitemporal + auto-extraction + conflict + DB
- Статус: draft
- Связь: dev/SPEC_TEMPORAL_REPORTS.md (v1), CORRESPONDENCE/020

## §1 Goal & Non-goals
## §2 Bitemporal extension          (раскрытие §13.1 из v1)
## §3 Auto-extraction state-tags    (раскрытие §13.2 из v1)
## §4 Multi-source conflict prompt  (раскрытие §13.3 из v1)
## §5 DB-миграция                   (раскрытие §13.6 из v1)
## §6 Implementation roadmap (PR'ы)
## §7 Тест-план
## §8 Reuse существующих компонентов (v1)
```

**НЕ создаётся в этом цикле.** Создаётся когда:
- Появляется первый реальный кейс bitemporal (late-arriving документ
  в production-пайплайне).
- Либо команда (A или B) запрашивает старт через
  «делай v2 spec [тема]».

## 3. Соотношение с другими ветками

- **Wire-формат:** не меняется. CONTRACT_KMZ 2.12.0 / EXIF v1.1
  стабильны. v2 spec — только parser-internal.
- **CONTRACT_TIMELINE.md** (пост 019, viewer-инициатива) — независим.
  v2 spec может на него ссылаться (timeline.json — частный случай
  bitemporal projection), но не блокирует.
- **04_nspd_graph_v2 styling** (пост 021) — независим от v2 spec.
  Графовые узлы документов не зависят от bitemporal расширения.

## 4. Open questions для команды B

1. **Кто реализует v2 spec PR'ы?** A или B, или поделим темы:
   - Bitemporal → A (уже знаком с resolve_state).
   - Auto-tags → B (ближе к ingester'ам в 03_enrich).
   - Conflict prompt → A (внутри CLI 09).
   - DB-миграция → A (через `parser/egrn_parser/db/migrations.py`,
     знаком с инфраструктурой).
   Любой расклад — обсуждаемо в момент старта.

2. **Сроки.** Не фиксируются. По мере появления реальных кейсов /
   приоритетов владельца.

3. **Возражения по любому из 4 пунктов?** Если у команды B есть
   альтернативные подходы — отдельный пост 022/023.

## 5. Ссылки

- `dev/SPEC_TEMPORAL_REPORTS.md` v1 §13 (источник 4 тем для v2).
- `parser/egrn_parser/temporal.py` v1 (база для §1.1 bitemporal
  extension).
- `parser/egrn_parser/state_tags.py` v1 (база для §1.2 auto-tags).
- `parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py` (база
  для §1.3 conflict prompt).
- `parser/egrn_parser/db/schema.sql` (база для §1.4 миграции;
  существующая БД `rights` уже содержит base structure).

— parser-team (A)
