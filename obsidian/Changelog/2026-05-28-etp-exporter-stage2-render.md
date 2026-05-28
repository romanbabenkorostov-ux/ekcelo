# 2026-05-28 — ЭТП-экспортёр Stage 2: text_render (Jinja)

## Итог
Второй слой ЭТП-экспортёра: `render_lot_description(ctx) → str`. Импорт Jinja-шаблона из `docs/etp_export/05_*.md` как есть, платформенный диспатч (3 платформы × 2 mode), 8 golden-файлов для регрессии.

## Артефакты
- `parser/exporters/etp/text_render.py` — Jinja Environment + render-функция + нормализация whitespace.
- `parser/exporters/etp/templates/torgi_long_description.j2` — копия шаблона из docs (473 строки). Единственное локальное расширение: `full_address` макрос фолбэчит на `location.address_raw`, если компонентов нет (gap §10).
- `parser/tests/golden/etp/` — 8 файлов: 6 базовых (3 × short/full) для case A + caseB (sber-ast full со ипотекой) + caseC (torgi short по земле).
- `parser/tests/test_text_render.py` — 18 тестов.
- `parser/scripts/dev/gen_etp_golden.py` — utility для регенерации goldens.
- `parser/pyproject.toml` — `jinja2>=3.1` в dependencies.

## Поведение
- `platform_mode` берётся из `ctx.meta.platform_mode` (default `short`).
- Платформа из `ctx.meta.platform`; шаблон сам диспатчит на нужный макрос.
- Неизвестная платформа/mode → `ValueError`.
- `ChainableUndefined`: цепочки `ctx.building_extra.engineering.electricity` молча работают на отсутствующих словарях (case C: land без `building_extra`).
- Whitespace-нормализация: 3+ переносов → 2; trailing spaces убираются; результат заканчивается одним `\n`.

## Тесты (18/18 pass)
- 2 — валидация platform / mode.
- 6 — golden-сравнения для case A (office, 3 платформы × 2 mode).
- 2 — case B (storage) и case C (land) — дополнительные golden.
- 8 — семантические инварианты (cad_number в тексте, адрес виден, банкротство в sber full, ипотека в storage, «земельный участок» в land, нет 3+ blank lines, не-empty на всех 6 комбо).

## Известные ограничения шаблона (не фиксились — импорт «как есть»)
- Грамматические шероховатости в окончаниях («Здание ,», «удовлетворительная улично-дорожной»).
- Жёсткие шаблонные строки про «по результатам анализа документации и материалов дела о банкротстве» (sber-AST full) выводятся даже когда фактический список рисков пуст.
- Стихийные одиночные / двойные пробелы между токенами — частично нормализуются в text_render, остальное — задача отдельного PR-рефакторинга шаблона (потребует обновления и docs/etp_export/05_*.md).

Эти моменты документированы и захвачены в goldens. Не блокеры для MVP.

## Следующий шаг (Stage 3)
CLI `python -m parser.exporters.etp.cli --lot <lot_id> --platforms ... --modes ... --out <dir>` + PDF-приложение (`pdf_appendix.py`) + integration test «лот → 6 .txt в out/etp/<lot_id>/<platform>/».
