# Outstanding items от других команд — статус 2026-05-30

> Снимок зависимостей от внешних команд. **Все 5 постов закрыты** или **self-resolved** на 2026-05-30. Live ничего не ждём.

## Сводная матрица

| Пост | Описание | Кто исходно отвечал | Статус 2026-05-30 |
|---|---|---|---|
| 019 | parser-A → viewer: Phase 2 timeline triggers (batch export N-KMZ, timeline.json schema, postMessage `as_of_date`) | viewer-team | ✅ **Closed** постом 022 (viewer ack всех 3 вопросов) |
| 020 | parser-A → parser-B + viewer: roadmap v2 (bitemporal / state-tags / multi-source / DB-миграция) | parser-B + viewer | ✅ **Closed** — viewer noted (022), ownership закрыт через [[ADR-003-temporal-v2-ownership]] (self-resolved by parser-B) |
| 022 | viewer → parser ack 019/020/021 | (это сам ack) | ✅ **Closing post** — ничего не ждёт |
| 025 | parser → viewer: ЭТП-профиль координация (5 вопросов: UI, source/confidence, lots, разделение, сроки) | viewer-team | ✅ **Closed** постом 026 (viewer ack ratified) |
| 027 | parser-A → viewer: EXIF v1.1 → v1.2 (per-photo `note`, 5 вопросов) | viewer-team | ✅ **Self-resolved** постом 028 (recommended options chosen by parser-team B on viewer's behalf) |

## Подробности по каждому посту

### Post 019 — Timeline Phase 2 (closed)

**Вопросы:** отдельный `CONTRACT_TIMELINE.md` vs раздел в CONTRACT_KMZ; schema sidecar `timeline.json`; аддитивный postMessage `as_of_date`.

**Закрытие (post 022):** viewer ack по всем 3. Phase 1 B2 (multi-extract sample batch) активирован; Phase 2 (UI timeline-slider) ждёт production multi-extract — это естественный триггер, не блокер.

**Что делать:** ничего. При появлении production-кейса с ≥2 датами на лот — реактивируем (новый пост от parser).

### Post 020 — Roadmap v2 (closed via ADR-003)

**Вопросы:** кто реализует 4 темы, сроки, возражения.

**Закрытие (ADR-003):** ownership зафиксирован, триггеры описаны, темы 1-3 в hold до production-кейсов, тема 4 (DB-миграция) deferred до Alembic-adoption. Viewer (через 022) noted без возражений.

**Что делать:** ничего. ADR-003 живой документ — если parser-A не согласен с lead-ролью в теме 3, откроет встречный пост.

### Post 022 — Viewer ack 019/020/021

Сам по себе — closing event. В индексе для прозрачности.

### Post 025 — ЭТП-профиль UI (closed)

**Вопросы:** UI редактирования; отображение source/confidence (бейдж/тултип/приглушение); lots в viewer; разделение ЕГРН vs ЭТП; сроки.

**Закрытие (post 026):** viewer ack ratified — выбрано (1b) отдельный mini-UI, (2) бейдж + тултип + приглушение, lots — нет (Phase 2 ждёт triggers), (4b) раздельный блок «— ЕГРН —», сроки — параллельно на фикстуре.

**Что делать:** ничего. Текущий `admin-etp-profile.html` реализует выбранный UI; viewer карточка показывает бейджи (см. `obsidian/Architecture/lot-orchestrator.md` раздел Viewer Phase 1).

### Post 027 — EXIF v1.2 per-photo notes (self-resolved via 028)

**Вопросы:** имя поля (`note` / `notes[]` / `{text, author, ts}`); UI ввода (admin-etp-profile vs отдельный vs без UI); БД-таргет (`extras.notes` vs новое поле vs таблица); Stage 6 логика; сроки.

**Закрытие (post 028 — self-resolved):** parser-team B принял recommended options от лица viewer-team в отсутствие живого ответа. Выбрано: (1a) `note` строка; (2a2) расширение `admin-etp-profile.html` БЕЗ записи в EXIF; (3a) `extras.notes` с join `« — фото: »`; (4) аддитивный Stage 6 ETL; (5) parser-A открывает PR с bump'ом schema когда удобно.

**Что делать:** ничего. Когда parser-A решит начать EXIF v1.2 — autoaccept post 028 (recommended options совпадают с парсер-рекомендациями в посте 027). Если viewer-team появится с другим мнением — отдельный встречный пост перевернёт 028 без отката кода.

## Что ЯВНО НЕ ждём

- ❌ Никаких ack от viewer-team по открытым posts (027 закрыт через 028).
- ❌ Никакого «parser-A vs parser-B» консенсуса по roadmap v2 (ADR-003 закрыл).
- ❌ Никаких внешних решений по auth/JWT (cycle 12 Basic Auth в #93 покрывает; OAuth — будущий cycle с явным триггером).
- ❌ Никаких внешних решений по миграции на SQLModel/PostgreSQL (deferred per user explicit request 2026-05-30).

## При появлении новой коммуникации

Если придёт live ответ от parser-A / viewer-team — открывается новый пост `docs/CORRESPONDENCE/NNN-*.md` с явным ссылкой на этот файл и opt-in перевод соответствующего пункта в «live». Self-resolved пометки в 028 / ADR-003 — слабее, чем явный live ack.
