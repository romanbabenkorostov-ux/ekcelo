# Хэндофф новой команде — ekcelo / приём данных ЕГРЮЛ-ЕГРИП

> Передаточный промпт. Прочитай целиком до начала работы. Цель — чтобы новая
> сессия/команда сразу понимала: как общаться с заказчиком, как работать с
> GitHub в этом окружении, что где лежит, где план задач и на чём мы
> остановились.

## 1. Как взаимодействовать с заказчиком (Roman)

- **Стиль ответов: Caveman Full** — максимально кратко, только суть (см. `CLAUDE.md`
  §4). Ключевые слова: `detailed` — подробно, `ultra` — экстремально кратко.
- **Думай до кода:** сначала assumptions/tradeoffs. Не уверен — спроси
  (`AskUserQuestion`). Не плоди абстракции, минимум кода, правь только то, что
  просили (Surgical Changes).
- **Язык:** русский. snake_case везде (Python/JS/SQL).
- **Операционный цикл (CLAUDE.md):** START → читать `CLAUDE.md`, `SUMMARY.md`,
  `schema/egrn_current_schema.sql`, последние 2-3 файла `obsidian/Changelog/`;
  озвучить план 1-3 пункта + список файлов под нож. EXECUTION → код + **обязательно**
  `obsidian/Changelog/YYYY-MM-DD-*.md`. DELIVERY → при >3 файлах ZIP.
- **Заказчик тестирует у себя** на Windows (`E:\Code\ekcelo\code`, venv,
  PowerShell). Образцы для парсинга — `E:\Code\ekcelo\primer_for_parsing\`
  (напр. `EGRUL-EGRIP\` — там **PDF**, XML-выписок на руках нет).
- Заказчик не подаёт данные в Drive — образцы кладёт в репо (`fixtures/`).

## 2. Как работать с GitHub в этом окружении

- **Push сейчас НЕ работает: `403 Permission denied`** (git-прокси отказывает в
  записи — это НЕ сеть, ретраи бесполезны). Заказчик в курсе, просил **не пушить**.
- **Доставка — ZIP** с repo-relative путями + инструкция «распаковать заменой в
  `E:\Code\ekcelo\code`». Коммить локально (с правильным автором, см. ниже),
  отдавай ZIP через файловую доставку.
- **Автор коммитов:** `git config user.email noreply@anthropic.com && user.name Claude`,
  иначе stop-hook ругается на Unverified. Tip-коммит чинится
  `git commit --amend --no-edit --reset-author`. **Merge/чужие/уже-в-origin
  коммиты НЕ переписывать.** Флаг «N» = нет GPG-подписи (подписать нельзя — ключа нет).
- **GitHub MCP** (`mcp__github__*`, грузить через `ToolSearch`): scope сессии =
  `romanbabenkorostov-ux/ekcelo`. **PR не создавать без явной просьбы.** Комментить
  на GitHub скупо, только по делу.
- Ветка разработки: `claude/<...>` (текущая — `claude/elegant-gates-eKTMC`).
  Развивать на ней, не пушить в чужие ветки.

## 3. Что где лежит (карта репозитория)

```
CLAUDE.md                      — правила проекта (читать ПЕРВЫМ)
parser/                        — Python-парсеры
  egrn_parser/parsers/         — парсеры: xml_parser.py (Росреестр-ЕГРН!),
                                 pdf_parser, docx, xlsx, osv,
                                 egrul_egrip_parser.py (ФНС ЕГРЮЛ/ЕГРИП — наш)
  egrn_parser/db/              — schema.sql пакета, connection, migrations
  schema/xsd/{egrul,egrip}/    — XSD ФНС (cp1251) + NOTES.md (версионирование)
  schema/xsd/upd/              — XSD УПД (та же конвенция, образец)
  scripts/                     — golden-path 00→13, enrich v17, nspd v8 и т.п.
  tests/ + tests/fixtures/     — pytest; fixtures/fns/ — ЕГРЮЛ/ЕГРИП cp1251
schema/egrn_current_schema.sql — БД-истина §1..§6 (ADR-001)
schema/migrations/             — миграции БД (только через файлы)
contracts/                     — Consistency Target v1.0 (C1..C6); db/ — ПУСТО,
                                 SCHEMA_SPEC.md проектируется в соседнем чате
docs/specs/SPEC_parser.md      — spec команды parser (ПЛАН ЗАДАЧ, треки P0..P3)
docs/CORRESPONDENCE/           — лог parser↔viewer (append-only)
fixtures/                      — обезличенные образцы документов (egrul_egrip/ и др.)
obsidian/                      — база знаний:
  Decisions/ADR-*.md           — журнал решений (ADR-001..004)
  Architecture/                — структура (parallel-parsers-map.md = карта парсеров)
  Changelog/                   — отчёты по задачам (по одному на задачу)
  Prompts/                     — этот хэндофф, db-schema-design-handoff и др.
```

## 4. Где читать план задач

1. **`docs/specs/SPEC_parser.md`** — треки P0..P3. Приём ЕГРЮЛ/ЕГРИП = треки 8-10.
2. **`obsidian/Architecture/parallel-parsers-map.md`** — статус всех парсеров.
3. **`obsidian/Decisions/ADR-001..004`** — почему так. ADR-004 = ФНС-XML парсер.
4. **`obsidian/Changelog/`** (последние файлы) — что сделано недавно.

## 5. Текущее состояние задачи «приём данных о субъектах»

**Сделано (ADR-004, Changelog 2026-06-05):**
- `egrn_parser/parsers/egrul_egrip_parser.py` — ФНС-XML ЕГРЮЛ(4.08)/ЕГРИП(4.07):
  автоопределение формата (`Файл/@ТипИнф`+`@ВерсФорм`), XSD по реестрам с
  версионированием, lxml-валидация, **нормализованная запись**
  `{subject, directors, managing_orgs, founders, predecessors, successors, source}`.
- XSD: `parser/schema/xsd/{egrul,egrip}/` (cp1251 + NOTES).
- Тесты `parser/tests/test_egrul_egrip_parser.py` — 9/9 зелёные.

**Сделано дополнительно (Changelog 2026-06-05-egrul-egrip-pdf-and-json-adapters):**
- `egrul_egrip_normalized.py` — общий `empty_record` + `merge_records` (приоритет
  источников). XML-парсер отрефакторен на него.
- `egrul_egrip_pdf.py` — PDF-адаптер (✅ проверен на 3 реальных выписках:
  ИНН/ОГРН/наименование/директор/учредитель+доля/преемник). `parse_text` чистая.
- `egrul_egrip_sources.py` — checko/dadata JSON-мапперы + `fetch_by_inn` (по ключу).
- **`.env`:** ключи в `parser/.env` (копия `parser/.env.example`), под `.gitignore`.
  `CHECKO_API_KEY`, `DADATA_API_KEY`+`DADATA_SECRET_KEY`. Без ключа PDF-парсинг
  ИНН/ОГРН работает offline; `fetch_by_inn` без ключа в сеть НЕ идёт (RuntimeError).
- Тесты ЕГРЮЛ/ЕГРИП: **17/17** (`test_egrul_egrip_parser.py` + `_sources.py`).

**Дальше по плану (приоритет сверху):**
1. **Враппер «запись → БД» (БЛОКЕР):** пишет в §6 legal-слой
   (`entity_registry`/`object_etp_profile.legal_extra`, `source=...`). Ждёт
   `contracts/db/SCHEMA_SPEC.md` из соседнего чата. До готовности схемы —
   парсеры отдают только dict, таблицы не выдумывать (Simplicity First).
2. **Прогнать `fetch_by_inn`** на реальном ИНН (из PDF) при появлении ключей.
3. **Golden-тесты** на обезличенных образцах в `fixtures/egrul_egrip/`.

**Правило единой записи:** все источники (XML/PDF/checko) мапятся в один dict
`{subject, directors, managing_orgs, founders, predecessors, successors, source}`,
downstream не знает про источник; конфликты разрешаются приоритетом `source`
(официальный ФНС-XML > checko/dadata > PDF/LLM), как в §6 (ADR-001/002).

## 6. Как прогнать тесты (у заказчика, Win10)

```powershell
cd E:\Code\ekcelo\code\parser
python -m pytest tests\test_egrul_egrip_parser.py -v   # ожидаемо 9 passed
```
Ручная проба парсера на реальной выписке:
```powershell
python -c "from egrn_parser.parsers.egrul_egrip_parser import parse, detect_format; import json; p=r'ВЫПИСКА.xml'; print(detect_format(p)); print(json.dumps(parse(p), ensure_ascii=False, indent=2))"
```
