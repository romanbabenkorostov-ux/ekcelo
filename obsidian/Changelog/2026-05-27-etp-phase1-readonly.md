# 2026-05-27 — viewer ETP Phase 1: read-only рендер профиля

## Итог
В info-карточке объекта появился раздел «ЭТП-профиль» с бейджами `source` / `confidence` — Phase 1 по TASK_BRIEF viewer-team. Контракт `CONTRACT_KMZ.md 2.12.0` не затронут, парсер KMZ не модифицирован.

## Артефакты
- `viewer/index.html` — 4 врезки (см. ниже).
- Фикстура `parser/tests/fixtures/etp/object_etp_profile_sample.json` уже в `main` с PR #53; в этот PR не дублируется.

## Изменения в `viewer/index.html`
1. **Загрузчик фикстуры** после `const TILES={...}` — глобал `_etpProfile = {byKn, lots, lotItems}` + async fetch. Молчаливый skip, если фикстура отсутствует.
2. **CSS** рядом с `.ic-att-chip`: `.ic-section-label`, `.ic-etp-badge--high|mid|low` (зелёный/жёлтый/оранжевый через CSS-переменные темы), `.ic-etp-body.ic-etp-dim` (opacity 0.55).
3. **`_renderObjectCard`** — извлечение `cad_number` из `m.cadNum || m.name` (с regex-фолбэком), вставка `egrnLabel` перед `ic-name` и `etpHtml` после `attHtml`. Метка «ЕГРН» появляется **только** при наличии ЭТП-пары.
4. **`_renderEtpBlock(etp)`** — новая функция: бейдж по правилам high/mid/low + tooltip; рендер строк по 6 секциям (`location_extra` / `building_extra` / `layout` / `legal_extra` / `risks` / `extras`); возврат пустой строки, если все секции пусты.

## Правила бейджа
| `confidence` | `source` | Бейдж | Текст приглушён? |
|---|---|---|---|
| `1.0` | `osv` / `manual` | зелёный | нет |
| `0.5..0.99` | `nspd` / `exif` | жёлтый | нет |
| `< 0.5` | любой | оранжевый | **да** (`opacity:0.55`) |

Tooltip — title-атрибут на бейдже с расшифровкой источника.

## Тесты (Node smoke + ручной)
- Smoke harness `node` против фикстуры:
  - КН `:31` (case A, `osv` 1.0) → бейдж high, без приглушения. ✓
  - КН `:42` (case B, `nspd` 0.65) → бейдж mid, без приглушения. ✓
  - КН `:7` (case C, `llm` 0.35) → бейдж low + `ic-etp-dim`. ✓
  - Пустой профиль → пустая строка (карточка не ломается). ✓
- Ручной чеклист (Chrome / Firefox / Yandex.Browser) — делегируется human-проверке после мерджа (нет live viewer в этой среде).

## Гранулы делеривери (что НЕ сделано в этом PR — by design)
- Редактор профиля (`admin/etp-profile/<cad_number>`) — после миграции БД, отдельный PR.
- Вкладка «Лоты» — YAGNI (CORRESPONDENCE/025 §3).
- Phase 2 overlay (бейдж лота на маркере + цвет границы по `lot_id`) — отдельная итерация.
- НЕ трогали: `CONTRACT_KMZ.md`, парсер KMZ-цепочку, блок `TILE SEAM FIX`, файлы в `parser/`.

## Связи
- TASK_BRIEF viewer-team (из приложения).
- CORRESPONDENCE/025 (PR #50) + 026 (PR #52).
- Фикстура — PR #53 (merged), формат identичен будущему БД-экспорту (Stage 2+ parser).
