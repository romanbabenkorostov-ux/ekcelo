# 2026-06-05 — PDF-адаптер + checko/dadata JSON-адаптеры ЕГРЮЛ/ЕГРИП (мультиисточник)

## Суть
Добавлены ещё два источника данных о субъектах в ту же нормализованную запись,
что и ФНС-XML (ADR-004): **PDF-выписки ФНС** (у экономиста на руках только PDF)
и **checko/dadata JSON**. Все источники → единая форма
`{subject, directors, managing_orgs, founders, predecessors, successors, source}`.

## Сделано
- **Общий модуль записи** `egrul_egrip_normalized.py`: `empty_record()`,
  `SOURCE_PRIORITY` (ФНС-XML > ФНС-PDF > checko > dadata > llm), `merge_records()`
  (gap-fill по приоритету). XML-парсер отрефакторен на него (убран дубль).
- **PDF-адаптер** `egrul_egrip_pdf.py`: `extract_text()` (pdfplumber→PyMuPDF→
  pypdfium2) + `parse_text()` (чистая, тестируется на тексте). Опознание реестра
  по интро, идентификация из шапки (ОГРН/ОГРНИП/ИНН/наименование/ФИО), связи —
  best-effort по секциям (руководитель ФЛ/управляющая орг., учредители+доли,
  правопреемник/предшественник, статус, ОКВЭД). Фильтр колонтитулов.
  **Проверено на 3 реальных выписках** (ИП + ООО «АНТАРЕС» + Личный фонд «ДОМ»):
  ИНН/ОГРН/КПП/наименование/директор/учредитель+доля/преемник извлекаются верно.
- **checko/dadata адаптеры** `egrul_egrip_sources.py`: чистые мапперы
  `from_checko_json` (кириллич. ключи Руковод/Учред/РосОрг/ФЛ) и `from_dadata_json`
  (латинские management/founders/okveds). Опциональный клиент `fetch_by_inn(inn,
  vendor)` — читает ключи из `parser/.env`, **без ключа в сеть НЕ идёт**
  (RuntimeError). `load_env()` — простой парсер `.env` без зависимостей.
- **`.env`**: `parser/.env.example` (CHECKO_API_KEY / DADATA_API_KEY+SECRET).
  `parser/.env` уже под `.gitignore` (правило `.env`/`.env.*`, исключение
  `.env.example`).
- **Тесты** `tests/test_egrul_egrip_sources.py` (8) + синтетические фикстуры без
  ПД (`egrul_pdf_min.txt`, `egrip_pdf_min.txt`, `checko_min.json`, `dadata_min.json`).
  Итого по ЕГРЮЛ/ЕГРИП — **17/17 зелёных**.

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_normalized.py` (новый)
- `parser/egrn_parser/parsers/egrul_egrip_pdf.py` (новый)
- `parser/egrn_parser/parsers/egrul_egrip_sources.py` (новый)
- `parser/egrn_parser/parsers/egrul_egrip_parser.py` (рефактор на empty_record)
- `parser/.env.example` (новый)
- `parser/tests/test_egrul_egrip_sources.py` + `tests/fixtures/fns/*` (новые)

## Решения
- **Извлечение текста отделено от разбора** — `parse_text(text)` чистая,
  тестируется на тексте без PDF-библиотек (в CI могут отсутствовать).
- **PDF = confidence 0.8**, надёжна шапка (ИНН/ОГРН); связи best-effort.
- **Враппер в БД по-прежнему не делаем** — ждём `contracts/db/SCHEMA_SPEC.md`.

## Дальше
- Враппер «нормализованная запись → §6 legal-слой», когда готова схема БД.
- При появлении ключей — прогнать `fetch_by_inn` на реальном ИНН из PDF
  (PDF даёт ИНН → checko/dadata дотягивают руковод/учредителей).
