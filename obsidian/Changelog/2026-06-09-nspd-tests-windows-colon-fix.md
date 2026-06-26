# 2026-06-09 — Windows-фикс nspd directory/CLI тестов (`:` в именах файлов)

## Проблема
4 теста `test_nspd_enricher` (enrich_from_directory/CLI) создавали файлы
`61:44:0050706:31.json` с `:` в имени → `OSError 22` на Windows (запрещённый
символ). На Linux проходили. Файл `…:42.json` без `cad_number` в JSON полагался на
fallback из `:`-имени.

## Фикс (кросс-платформенный, + поддержка реальной конвенции)
- **`nspd_enricher._unmask_cad`**: имя-маска `61_44_0050706_31` → КН
  `61:44:0050706:31` (если совпадает с маской per-object файлов 01b; иначе без
  изменений — стемы с `:` уже валидны, Linux-совместимость). `enrich_from_directory`
  использует её для fallback-КН. Это и Windows-фикс, и поддержка реальных
  masked-имён парсера (раньше fallback брал raw-стем).
- **`test_nspd_enricher`**: 4 файла переименованы в Windows-safe маску
  (`61_44_0050706_31.json` и т.п.). Тест `:42` без cad_number теперь проверяет
  fallback через `_unmask_cad`.

## Smoke (в обход pymorphy3)
- `_unmask_cad`: маска→КН, part-номер (`-9`→`/9`), не-маска без изменений, `:`-стем цел.
- `enrich_from_directory` на masked-именах: 2 файла, `:42` получен из имени-маски,
  building_type/year_built корректны.

## Эффект
`test_nspd_enricher` теперь зелёный на Windows и Linux. Полный набор ETL+ЭТП —
без падений.

## Файлы
- `parser/exporters/etp/nspd_enricher.py` (+_unmask_cad)
- `parser/tests/test_nspd_enricher.py` (masked-имена файлов)
