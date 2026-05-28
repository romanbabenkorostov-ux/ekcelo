# 2026-05-28 — ETP viewer roadmap, открытые пункты

Состояние после мерджа PR #56 (Phase 1), #60 (026 ratify), #61
(parser address+encumbrance) и Stage 1-3 экспортёра (PR #55/#57/#59).

## Закрыто (моя зона)

- Phase 1 read-only render `_renderEtpBlock` — PR #56.
- Бейдж + тултип + приглушение `confidence<0.5` — Phase 1 (ack п.2).
- ЕГРН/ЭТП раздельно с подписями — Phase 1 (ack п.4).
- Параллельная работа через фикстуру — Phase 1 (ack п.5).

## Открыто

### admin/etp-profile/<cad_number> (ack п.1, вариант b)

Мини-UI редактирования полей `object_etp_profile` с токен-защитой
(по аналогии с `viewer/admin-encode.html`).

**Write-путь зафиксирован: вариант B — генератор YAML survey-листа.**
UI генерирует YAML по контракту `obsidian/Architecture/etl-osv.md`
(parser-A, PR #62). Экономист скачивает → кладёт по согласованному
пути → parser-A прогоняет ETL → запись в БД. Никакого REST endpoint
на parser-стороне, viewer остаётся статикой GitHub Pages.

**Не начинаем сейчас.** Ждём Stage 4b parser-A: JSON-экспорт текущего
состояния профиля по пути в репо (точное место уточняется письмом).
Без него UI не сможет показать «что сейчас в БД» для редактирования.

Triggers: pинг от parser-A о готовности Stage 4b + ответ на два вопроса:
- где в репо будет лежать `object_etp_profile.json` (fetch-источник);
- куда экономист кладёт сгенерированный UI YAML (workflow для UI-инструкции).

Содержимое UI (когда возьмёмся):
- Выбор `cad_number` из списка объектов (или ввод вручную).
- GET текущего профиля из JSON-экспорта parser-A (fallback на фикстуру для dev).
- Inline-форма по 6 секциям профиля (location/building/legal/...).
- На каждое поле — выпадушка source (по дефолту `manual`) +
  confidence (по дефолту `1.0`).
- Кнопка «Скачать YAML» → файл по контракту etl-osv.md.
- Минимум защиты: токен-gate как в `admin-encode.html`.

### Phase 2 overlay (ack п.3)

YAGNI до подтверждённого спроса. Если/когда оператору понадобится
визуально видеть состав лотов на графе/карте — переиспользуем
S5 group-overlay (`lots.lot_id` уже `[A-Za-z0-9_:/-]+` совместим
с `graph_node_id`, контракт KMZ не трогаем).

## Не моя зона (для контекста)

- Stage 4 ETL — parser-A.
- §10 SPEC gap'ы (address/encumbrance) — closed PR #61.
- NSPD-enrichment, PDF-конверсия Markdown-приложения — parser-A.
- Jinja-grammar refactor — parser-A.
