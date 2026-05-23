# 011 — Интеграция v17 chain от третьей parser-команды (append, без правки контракта)

- **From:** parser (A)
- **To:** parser (B); FYI: viewer
- **Date:** 2026-05-23
- **Re:** v17-цепочка скриптов: `03_enrich_v17`, `07_v2`, `08_v2_2`, `052_v2_1`;
  контракт 2.11.0 §2 / §6 / §9; `docs/CHANGELOG_enrich_v14_to_v17.md`
- **Status:** accepted with hotfix + 4 open clarifications для команды B

## 1. Что пришло

Третья parser-команда (B) прислала ZIP с 4 файлами-преемниками + CHANGELOG:

| Файл (источник)                                     | Назначение                                              |
|-----------------------------------------------------|---------------------------------------------------------|
| `03_enrich_v17.py`                                   | PDF ЕГРЮЛ/ЕГРИП + PERSON + залоги долей + держатель реестра АО; новые `_kind ∈ {ip, person, legal_text}`; рёбра `kind="person_to_legal"` |
| `pirushin_sosn_rocha_07_init_project_v2.py`          | Конвенция КН-маски: `:` → `_`, `/` → `__` (часть КН); расширенный `CN_UND_RE`; alias `cad_to_token = _cn_to_mask` |
| `pirushin_sosn_rocha_08_build_kmz_v2_2.py`           | `cn_to_id_part`: `/N` → `__N` для **Style id / styleUrl-якоря** (контрактный `<name>`/`description` идут напрямую — §6 не нарушается) |
| `pirushin_sosn_rocha_052_make_structure_v2_1.py`     | `link_with_enriched`: фильтр `_kind ∈ {ip, person}` + fallback на `ben["attrs"]` |
| `CHANGELOG_enrich_v14_to_v17.md`                    | Информативный |

Все правки — **parser-internal**. Wire-формат KMZ 2.11.0 §2 (ExtendedData
имена/типы), §6 (регексы `cadastral_number` и `graph_node_id`), §5
(`graph.html` контракт) не затронуты.

## 2. Что принимаем без правок (append рядом со старыми)

Файлы скопированы в `parser/scripts/` под их именами; v14/v1/v2 остаются
рядом (паттерн append, как в прошлых раундах: 052_v1 → 052_v2 → 052_v2_1,
08_v1 → 08_v2 → 08_v2_2).

- `03_enrich_v17.py` — рядом с `03_enrich_v14.py`.
- `pirushin_sosn_rocha_07_init_project_v2.py` — рядом с `_v1`.
- `pirushin_sosn_rocha_08_build_kmz_v2_2.py` — рядом с `_v2`.

Проверки:
- `python3 -m py_compile` всех 4 файлов — OK.
- Покрытие в `parser/tests/test_v17_chain.py` (новый, 8 кейсов) — все
  passing; полный набор `parser/tests/test_build_kmz_v2.py +
  test_graph_node_id.py + test_v17_chain.py` = **36 passed**.
- Регресс старых тестов (28) против main — нулевой.

## 3. Что патчим поверх (hotfix к `052_v2_1`)

Найдена скрытая bug в `load_enriched_extras` (стр. 528–546 в присланном
v2_1): через `folder.rglob("*.json")` идёт `.append(...)` для
`business_units`, и если в папке окажутся одновременно canonical
`enriched.json` (новая v17-конвенция) и legacy `enriched_<timestamp>.json`
(v14), список BU **дублируется**. Бенефициары (`dict`) безопасны
(overwrite по ключу), а BU — нет.

Наложен патч поверх присланной версии (минимальный, локально в той же
функции):

```python
canonical = folder / "enriched.json"
if canonical.exists():
    files = [canonical]                                   # детерминизм v17
else:
    files = sorted(folder.rglob("enriched_*.json")) or \
            sorted(folder.rglob("*.json"))                 # legacy v14 fallback
for jp in files:
    ...
```

Покрыто тестами `test_052_load_enriched_priority_canonical` и
`test_052_load_enriched_fallback_to_legacy`.

## 4. Что отложено в S6+ (без сиюминутной правки)

`04_nspd_graph_v14` (parser-side overlay графа) сегодня:
- узлы `_kind = "ip" | "legal_text"` визуально рисуются как ЮЛ (красный)
  — связи целые, но без визуального различения ИП / ФЛ-текста / ЮЛ;
- ребро `kind = "person_to_legal"` отрисуется обычным `founder`-стилем —
  семантика корректна, но без visual cue.

Это viewer/parser overlay UX (не wire). Зафиксировано в §9 строкой
S6+ (расширение существующего bullet). Контракт SemVer не двигается —
`2.11.0` стабилен.

## 5. Открытые вопросы команде B (отдельным письмом передаются)

1. **§2 формат `beneficiaries`** в письме команды B: показано «поля на
   верхнем уровне», но в коде (и v14, и v17) поля живут в `ben["attrs"]`.
   В коде 052_v2_1 (стр. 1042–1068) на это уже есть fallback — но это
   именно **bug-fix к скрытому багу 052_v2**: на main без вашего v2_1
   `enterprise.inn/ogrn/kpp` всегда `None` (наш `link_with_enriched`
   ищет ИНН/ОГРН/КПП на верхнем уровне `ben`, где их нет). Просьба
   отразить этот fact в `CHANGELOG_enrich_v14_to_v17.md` или CHANGELOG
   к 052_v2_1 — это не «защитный код», а tacit-fix.

2. **Двойная агрегация BU в `load_enriched_extras`** — мы наложили
   hotfix приоритета canonical `enriched.json` (см. §3 выше). Просим
   либо инкорпорировать в ваш будущий 052_v2_2, либо санкционировать
   наш патч в нашей копии.

3. **`04_nspd_graph_v14`** — `_kind = "ip" | "legal_text"` и ребро
   `person_to_legal`: подтвердите, что 04 — ваша зона (parser-domain
   overlay), и S6+ TODO без сиюминутной правки приемлемо (alternative:
   вы выпускаете `04_v2` со стилями и мы интегрируем как append).

4. **CHANGELOG §5 «ASCII» префиксы** — `[Р]`, `[АО]` названы «ASCII»,
   но это кириллица. Уточнить: оговорка в комментарии (имелось в виду
   single-byte-safe / визуально-краткий префикс)? Или планируется
   латинизация (`[D]` / `[JSC]`)? Косметика, без срочности.

## 6. Виду из viewer-team — FYI

Wire-формат KMZ 2.11.0 не меняется. Возможно появление новых узлов
`_kind = ip | legal_text` в графе и ребра `person_to_legal` —
сейчас они визуально неотличимы от ЮЛ / обычного `founder`-ребра
соответственно (см. §4). Никаких изменений в viewer не требуется,
действия не нужны.

## 7. Ссылки

- `docs/CHANGELOG_enrich_v14_to_v17.md` (информативный, скопирован)
- `parser/scripts/03_enrich_v17.py`
- `parser/scripts/pirushin_sosn_rocha_07_init_project_v2.py`
- `parser/scripts/pirushin_sosn_rocha_08_build_kmz_v2_2.py`
- `parser/scripts/pirushin_sosn_rocha_052_make_structure_v2_1.py`
  (присланная версия + hotfix `load_enriched_extras` приоритет canonical)
- `parser/tests/test_v17_chain.py` (8 новых тестов)
- `docs/CONTRACT_KMZ.md` §9 — обновлён S6+ bullet (визуальные стили
  `_kind` и ребра `person_to_legal`)

— parser-team (A)
