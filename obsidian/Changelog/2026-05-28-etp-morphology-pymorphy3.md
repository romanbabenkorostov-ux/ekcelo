# 2026-05-28 — Морфология русского (pymorphy3) в Jinja-шаблоне

## Итог
Закрыты 4 главных падежных бага шаблона ЭТП-описания через `pymorphy3` + Jinja-фильтры. Текст теперь грамматически корректен в типовых конструкциях.

## Артефакты
- `parser/exporters/etp/morphology.py` — модуль склонения. Singleton `MorphAnalyzer`, кэшированный `_inflect_word`, smart-skip gent-форм при не-gent падежах.
- `parser/exporters/etp/text_render.py` — регистрация 6 Jinja-фильтров (`inflect_nom`/`gen`/`dat`/`acc`/`ins`/`loc`).
- `parser/exporters/etp/templates/torgi_long_description.j2` — применены фильтры в 5 местах (3 ветви `purpose`, `paragraph_legal`, `paragraph_location`).
- `docs/etp_export/05_jinja_шаблон_все_платформы.md` — те же правки в spec-источнике.
- `parser/tests/test_morphology.py` — 15 тестов.
- `parser/tests/golden/etp/*.txt` — регенерированы 6 файлов (caseB без inflectable полей).
- `parser/pyproject.toml` — `pymorphy3>=2.0`, `pymorphy3-dicts-ru>=2.4`.
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы», «Шаблон-источник истины».

## Закрытые баги

| Было | Стало |
|---|---|
| `Нежилое помещение офис назначения` | `Нежилое помещение офиса назначения` |
| `Объект расположен в зона смешанной…` | `Объект расположен в зоне смешанной…` |
| `по удовлетворительная улично-дорожной сети` | `по удовлетворительной улично-дорожной сети` |
| `Право собственность зарегистрировано за Российская Федерация` | `Право собственности зарегистрировано за Российской Федерацией` |
| `центральной части города` (был побочный регресс при наивном word-by-word) | `центральной части города` (smart-skip gent сохранил корректность) |

## Контракт morphology.py

```python
inflect(phrase: str | None, case: str) -> str
# case ∈ {nom|gen|dat|acc|ins|loc} или pymorphy3 grammeme.
# Возвращает фразу с per-word склонением; сохраняет регистр первой буквы,
# пробелы, пунктуацию. Слова в gent-падеже не трогаются при не-gent целях
# (защита составных конструкций с приложениями).
```

Шорткаты: `inflect_nom` / `inflect_gen` / `inflect_dat` / `inflect_acc` / `inflect_ins` / `inflect_loc`.

## Применение в Jinja

```jinja
{{ ctx.legal.right_type | inflect_gen }}           {# собственности #}
{{ ctx.legal.right_holder | inflect_ins }}          {# Российской Федерацией #}
{{ ctx.location.environment_short | inflect_loc }}  {# зоне смешанной... #}
{{ ctx.location.transport_access | inflect_loc }}   {# удовлетворительной #}
{{ ctx.identity.purpose | inflect_gen }}            {# офиса #}
```

## Тесты (15/15 morphology, 198/198 в полном прогоне)

- 4 базовых случая (loc/gen/ins одиночные + фразы с согласованием).
- 2 капитализации (первая буква сохраняется).
- 2 многословные фразы с разделителями.
- 6 fallback (None, пустая строка, числа, неизвестные слова, аббревиатуры, short/full форма case-имени, неизвестный case).

## Известные ограничения

- `pymorphy3` использует словарь — экзотические слова (специфические термины, иностранные названия) могут не склоняться → возвращаются как есть.
- Род и число определяются first-parse heuristic'ом, без learning контекста. В двусмысленных случаях («стали» — глагол или сущ.) можно выбрать неверную лемму.
- Smart-skip защищает основной use-case (loc/ins/dat фразы с приложениями в gen), но не покрывает все возможные синтаксические комбинации.

## Связи
- PR #70 (Jinja-grammar refactor) — закрыл whitespace + structural баги, этот PR закрывает падежи.
- Контракт `etl-osv.md` не тронут.

## Что осталось
- EXIF v1.2 per-photo заметки — требует bump схемы EXIF.
