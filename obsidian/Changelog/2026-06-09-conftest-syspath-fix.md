# 2026-06-09 — Фикс путей conftest: разблокировка сборки всех тестов

## Проблема
`parser/tests/conftest.py` добавлял в `sys.path` только `parser/scripts`. Поэтому
при запуске `pytest` (без `python -m`) не резолвились **обе** конвенции импорта репо:
- `from egrn_parser...` (нужен `parser/` в path);
- `from parser.exporters...` (нужен корень репо в path, где `parser` — пакет).
ETL-тесты (`test_etl_*`, `test_nspd_enricher`, `test_etl_checko`) падали на сборке
`ModuleNotFoundError: No module named 'parser'`; мои `egrn_parser`-тесты собирались
лишь через `python -m pytest` из `parser/`.

## Фикс
`conftest.py` добавляет в `sys.path` (идемпотентно, независимо от cwd/способа запуска):
`parser/scripts`, **`parser/`** (→ `egrn_parser.*`/`exporters.*`), **корень репо**
(→ `parser.*`; `parser/__init__.py` делает его пакетом; в Py≥3.10 stdlib-модуля
`parser` нет, конфликта нет).

## Проверка
- `pytest tests/test_etp_merge.py` (plain) → **12 passed** (раньше падал на сборке).
- `test_nspd_enricher` проходит импорт `parser`/`egrn_parser` (остаток — отсутствие
  pyyaml/pymorphy3 в среде разработки парсера; на машине с зависимостями собирается).

## Эффект
Теперь все тесты собираются одной командой из `parser/`:
`pytest tests/` (или `python -m pytest tests/`) — и ETL, и egrn_parser-тесты.

## Файлы
- `parser/tests/conftest.py` (sys.path: +parser/, +корень репо)
