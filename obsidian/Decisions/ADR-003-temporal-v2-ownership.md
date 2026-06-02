# ADR-003: Ownership 4 тем dev/SPEC_TEMPORAL_REPORTS v2

**Статус:** Accepted (self-resolved) · **Дата:** 2026-05-30 · **Автор:** parser-team B
**Связанные:** post 020 (`docs/CORRESPONDENCE/020-parser-A-v2-spec-roadmap.md`), post 022 (viewer noted), `dev/SPEC_TEMPORAL_REPORTS.md` §13, [[ADR-001-etp-profile-extension]], [[ADR-002-parser-checko-integration-policy]]

## Контекст

Пост 020 (parser-A → parser-B + viewer-FYI) предложил roadmap для `dev/SPEC_TEMPORAL_REPORTS_v2.md` — 4 темы:

1. **Bitemporal extension** — два временных измерения (`valid_time` vs `recorded_time`) в overlay-документах.
2. **Auto-extraction state-tags** — парсер LLM/regex заполняет namespaced state-tags из текста выписок автоматически.
3. **Multi-source conflict resolution** — переход с «newer > registered > document» (текущее) на ranked-list резолвер с user-overrides.
4. **DB-миграция** — переход с JSON-колонок overlay-структур на нормализованные таблицы (требует Alembic-adoption).

Viewer-team в посте 022 ответил «noted, parser-internal, без возражений». Параллельно осталось открытым «кто реализует, какие сроки, есть ли возражения».

В сессии 2026-05-30 пользователь поручил parser-team B закрыть открытые posts самостоятельно. ADR фиксирует ownership и триггеры.

## Решение

### Ownership

| Тема | Owner | Обоснование |
|---|---|---|
| 1. Bitemporal extension | **parser-A** | Тема живёт в `parser/egrn_parser/temporal.py` (resolve_state, founder_chain_has_pledge) — core parser-A. Расширение `recorded_time` логичнее всего у того, кто владеет `parse_date` и overlay-моделью. |
| 2. Auto-extraction state-tags | **parser-B** | Тема пересекается с ЭТП-экспортёром (NSPD-enrichment, EXIF, ETL OSV — parser-B зона). Auto-extraction естественно встраивается между парсингом текста и записью в `state_tags` namespaces. |
| 3. Multi-source conflict resolution | **parser-A** (lead) + **parser-B** (review) | Текущий резолвер живёт в `lot_orchestrator/temporal.py` (parser-B) и `parser/egrn_parser/temporal.py` (parser-A). Ranked-list требует согласования модели. Lead — parser-A (как автор v1 модели), review — parser-B (как owner ЭТП-консьюмера). |
| 4. DB-миграция | **deferred** (joint после adoption Alembic) | Нет смысла мигрировать JSON-колонки на нормализованные таблицы, пока в стеке нет Alembic + SQLModel. Требует cycle "backend-full-template-migration", который пользователь явно отложил. |

### Триггеры запуска (когда тема становится «нужно делать»)

| Тема | Триггер |
|---|---|
| 1 | Появление production-кейса, где `valid_time != recorded_time` (например, ретроспективная корректировка ЕГРН-данных задним числом). |
| 2 | Появление NSPD-enrichment с >100 КН где ручная разметка state-tags нереалистична. |
| 3 | Появление spec кейса с ≥3 источниками одного факта (например, ЕГРН-выписка + checko + OSV для одного юрлица). Сейчас покрытие 2-source через `detect_conflicts` достаточно. |
| 4 | Решение о переходе на SQLModel + Alembic в основном стеке (вне ADR-003). |

### Что НЕ делаем сейчас

- Не создаём `dev/SPEC_TEMPORAL_REPORTS_v2.md` — нет триггера ни по одной теме.
- Не открываем PR-ы под темы 1-3 — нет production-кейсов.
- Не препятствуем parser-A добавлять `recorded_time` опционально в overlay-эффекты, если он сочтёт это полезным до триггера 1 (additive, не ломает).

## Альтернативы (rejected)

- **Один owner на все 4** — нагрузка концентрируется на одной итерации команды; темы пересекают границы parser-A/B.
- **Joint ownership всех 4** — без явного lead'а решения буксуют (выяснилось на примере поста 027).
- **Сразу написать v2 spec** — преждевременно, нет триггеров.

## Последствия

- ✅ Post 020 закрыт со стороны parser-team B. Viewer (через 022) noted ранее.
- ✅ Ownership зафиксирован — при появлении триггера сразу понятно, кто открывает PR.
- ⚠️ Если parser-A не согласен с lead-ролью в теме 3 — отдельный пост со встречным предложением.
- ⚠️ Тема 4 остаётся блокером, пока пользователь не одобрит миграцию на SQLModel/Alembic.

## Связи

- post 020: `docs/CORRESPONDENCE/020-parser-A-v2-spec-roadmap.md`
- post 022 (ack noted): `docs/CORRESPONDENCE/022-viewer-ack-019-020-021.md`
- spec: `dev/SPEC_TEMPORAL_REPORTS.md` §13 (источник 4 тем)
- ADR-001 — расширение БД под `object_etp_profile` (related)
- ADR-002 — отложенная интеграция parser_checko_ru (паттерн «deferred» применён)
