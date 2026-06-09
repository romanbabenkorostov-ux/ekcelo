# 2026-06-08 — PDF устойчив к pdfplumber + ОСВ→fixed_asset + ADR-006 v2

## Суть
(1) Главный багфикс: PDF-парсер ломался под pdfplumber (раскладка твоей машины).
(2) ОСВ → реестр ОС/техники (ADR-006 §G). (3) ADR-006 доработан по уточнениям.

## 1. PDF устойчив к раскладке pdfplumber (код, 44/44) — коммит e99c85a
Первопричина `founders:[]` у ЮНИКРЕДИТ: **pdfplumber кладёт «NN Метка Значение» в
ОДНУ строку**, а PyMuPDF — на разные. Рефактор `egrul_egrip_pdf.py`:
`_norm` снимает счётчик, метка матчится префиксом, значение = остаток строки или
строки ниже; числовые метки — guard. `_fio_triple`/`name_short`/ОКВЭД/акционер —
на обеих раскладках. Проверено на **реальном ЮНИКРЕДИТ** (pdfplumber И PyMuPDF):
директор ОБОРИН, иностр. акционер ЮНИКРЕДИТ С.П.А. (страна/рег.№/номинал), КПП,
ОКВЭД. +обезличенная plumber-фикстура.

## 2. ОСВ → fixed_asset (ADR-006 §G)
`egrn_parser/parsers/osv_assets.py`: ОСВ.xlsx (1С) → реестр ОС. Колонка «Субконто»
= код счёта (01.01/01.08…) или ОС; одинаковые ОС агрегируются (units/cost/qty).
**Счёт 01.08 → on_cadastre=0** (ОКС, права не оформлены, мост к ADR-005).
Идемпотентный upsert по `UNIQUE(name,account,period)`. Проверено на реальном ОСВ
(1344 ОС). Миграция `schema/migrations/0003_fixed_assets.sql`. Тесты
`tests/test_osv_assets.py` (мини-ОСВ в памяти, вкл. 01.08).

## 3. ADR-006 v2 (уточнения)
- **F. Эффективное датирование** (`valid_from/valid_to/known_from`) в дополнение к
  `season_year` — «параметры существуют/устанавливаются/известны с даты».
- **G. `fixed_asset`** из ОСВ + `agro_event.asset_id` (техника в обработках); ОКС 01.08.
- **H. Словарь** стартово: crop/variety/planting_date/planting_year/seeding_rate.
- Зафиксировано: **agro_parcel/agro_event ingest заблокирован** (нет образца
  техкарты); fixed_asset реализуем сразу — сделано.

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_pdf.py` (рефактор раскладки)
- `parser/egrn_parser/parsers/osv_assets.py` (новый)
- `parser/tests/test_osv_assets.py`, `tests/fixtures/fns/egrul_pdf_plumber_layout.txt`
- `schema/migrations/0003_fixed_assets.sql`
- `obsidian/Decisions/ADR-006-...md` (v2)

## Дальше / нужно от заказчика
- **Образец техкарты** (обезличенный) в `fixtures/agro/` → парсер
  agro_parcel/agro_event (последний блок плана ADR-006).
- Подтвердить датирование F и стартовый словарь H.
