# 2026-05-27 — ADR-001: расширение схемы БД под ЭТП-профиль

## Итог
Зафиксировано архитектурное решение по разд. 5 SPEC (`docs/etp_export/SPEC_etp_export.md`): новые таблицы `object_etp_profile`, `lots`, `lot_items` живут в основной БД как отдельный «не-ЕГРН» слой. Принцип `CLAUDE.md` переформулирован: «БД = слепок ЕГРН + ЭТП-профиль».

## Артефакт
- `obsidian/Decisions/ADR-001-etp-profile-extension.md` — статус Proposed.

## Альтернативы (rejected)
- Manual-overlay JSON sidecar — нет транзакций, дублирование ключей.
- Только NSPD + LLM — нет ручного контроля экономиста.
- Расширение `objects` — размывает семантику таблицы.

## Следующий шаг
Пост в `docs/CORRESPONDENCE/` для согласования с viewer-team (UI редактирования профиля, бейджи `source/confidence`); затем PR с миграцией DDL.
