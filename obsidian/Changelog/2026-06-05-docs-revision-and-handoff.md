# 2026-06-05 — Ревизия Obsidian/spec под выполненное + хэндофф-промпт

## Суть
Приведение базы знаний и spec к фактическому состоянию после добавления
ФНС-парсера ЕГРЮЛ/ЕГРИП (см. Changelog 2026-06-05-fns-egrul-egrip-xml-parser).
Плюс передаточный промпт для новой команды.

## Сделано
- **ADR-004** (`obsidian/Decisions/ADR-004-fns-egrul-egrip-xml-parser.md`) —
  решение: ФНС-XML как официальный источник данных о субъектах, единая
  нормализованная запись для всех источников, XSD по реестрам с версионированием,
  запись в БД отложена до `contracts/db/SCHEMA_SPEC.md`.
- **Карта парсеров** (`Architecture/parallel-parsers-map.md`) — добавлен
  `egrul_egrip_parser` в TL;DR (статус ✅ в репо) + секция §0.
- **SPEC_parser.md** — добавлены треки 8-10 (мультиисточниковый приём ЕГРЮЛ/ЕГРИП:
  XML сделано, PDF/checko — план, враппер в БД — блокер на contracts/db).
- **Хэндофф-промпт** (`obsidian/Prompts/handoff-egrul-egrip-and-team-onboarding.md`)
  — как общаться с заказчиком, GitHub в этом окружении (403/ZIP/MCP/автор коммитов),
  карта репо, где план задач, текущее состояние + следующие шаги.

## Файлы под нож
- `obsidian/Decisions/ADR-004-fns-egrul-egrip-xml-parser.md` (новый)
- `obsidian/Architecture/parallel-parsers-map.md` (правка)
- `docs/specs/SPEC_parser.md` (правка)
- `obsidian/Prompts/handoff-egrul-egrip-and-team-onboarding.md` (новый)

## Дальше
PDF-адаптер ЕГРЮЛ/ЕГРИП (приоритет — у заказчика только PDF) → та же
нормализованная запись; нужны обезличенные образцы в `fixtures/egrul_egrip/`.
