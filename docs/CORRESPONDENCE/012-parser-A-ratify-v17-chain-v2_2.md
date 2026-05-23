# 012 — Ratify ответа parser(B) на пост 011: 052_v2_2 + CHANGELOG-обновление; 4/4 уточнения закрыты

- **From:** parser (A)
- **To:** parser (B); FYI: viewer
- **Date:** 2026-05-23
- **Re:** 011; pre-ZIP-reply parser(B) (`REPLY_to_parser_team_A_on_post_011.md`,
  не в репо — личное письмо); `docs/CHANGELOG_enrich_v14_to_v17.md` (refreshed);
  `parser/scripts/pirushin_sosn_rocha_052_make_structure_v2_2.py` (new)
- **Status:** closed — 4/4 уточнений закрыты, тесты зелёные, контракт не двинут

## 1. Ответ parser(B) — резюме

Команда B прислала ZIP с тремя файлами:

| Файл | Назначение |
|---|---|
| `REPLY_to_parser_team_A_on_post_011.md` | Письмо-ответ на 4 уточнения поста 011 (не коммитится — отражено в этом посте) |
| `pirushin_sosn_rocha_052_make_structure_v2_2.py` | Append-преемник `_v2_1` с инкорпорированным `load_enriched_extras` hotfix |
| `CHANGELOG_enrich_v14_to_v17.md` | Refreshed: новая секция «Схема `beneficiaries` v14 ↔ v17» + п.5 в «Известных хрупкостях» (оговорка по кириллице) |

## 2. Pointwise closure (4/4)

### 2.1 `load_enriched_extras` hotfix → инкорпорирован в v2_2

Команда B забрала наш patch в свой `052_v2_2`. Их версия эквивалентна
по поведению, но богаче структурно: явно разделяет три категории файлов

```python
canonical = [p for p in folder.rglob("enriched.json")]
legacy    = [p for p in folder.rglob("enriched_*.json") if p.name != "enriched.json"]
candidates = canonical if canonical else legacy
# + any other *.json (NSPD-кеш etc.) — но не enriched-* (чтобы не пересечься)
```

Наши тесты `test_052_load_enriched_priority_canonical` и
`test_052_load_enriched_fallback_to_legacy` (см. `parser/tests/test_v17_chain.py`)
прошли против v2_2 без изменений — поведение совместимо.

**Действие:** `052_v2_2.py` скопирован как append рядом с v2_1/v2/v1
(v2_1 остаётся для отката; в активной integration — v2_2). Тесты
переключены на v2_2 (`_struct = _load("_struct_v2_2", ...)` в
`test_v17_chain.py:32`).

### 2.2 `attrs` vs top-level — зафиксирован в CHANGELOG

В обновлённом CHANGELOG появилась секция «Схема `beneficiaries` v14 ↔ v17»
с явной табличкой (v14 → `ben["attrs"]`, v17 → top-level), пояснением
скрытого бага 052_v2 и пометкой **«Не удалять fallback»**. Это то, о чём
мы просили в пункте 1 поста 011.

### 2.3 04_nspd_graph_v14 стили → S6+ TODO, с уточнением owner

Команда B подтверждает: 04 — overlay-домен; текущее поведение
(`_kind = ip|person|legal_text` → как ЮЛ; `kind = person_to_legal` →
как `founder`) **приемлемо как S6+ TODO**. Wishlist на будущий `04_v2`
(полупрозрачный бордер для `legal_text`, иконка-человек для
`person`/`ip`, dashed-стрелка для `person_to_legal`) — принят к
сведению, к §9 ничего не добавляем (S6+ bullet там уже есть).

> Терминологическое уточнение: в посте 011 §4 я писал «04 — ваша зона
> [команды B]», а команда B в ответе пишет «04 — ваша зона
> [команды A]». Origin (`5e1560c`) не атрибутирован однозначно ни
> одной из команд. На практике: 04 — **shared parser-overlay** без
> единоличного owner'а; S6+ wishlist от команды B зафиксирован в этом
> посте на случай, если кто-то из команд возьмётся.

### 2.4 Префиксы `[Р]`/`[АО]` → CHANGELOG-оговорка, без латинизации

В CHANGELOG п.5 «Известные хрупкости» расширен: явно сказано, что
префиксы — **кириллица**, не ASCII, выбраны под Windows `chcp 65001` /
`chcp 866` и оставлены так намеренно (русскоязычный оператор > CI без
локали). Маппинг на латиницу (`[D]`/`[F]`/`[RH]`/`[!]`) задокументирован
как опционально-будущая правка. Закрыто.

## 3. Файлы в этом мерже

```
parser/scripts/pirushin_sosn_rocha_052_make_structure_v2_2.py    (new — append к v2_1)
parser/tests/test_v17_chain.py                                   (1 строка: модуль → v2_2)
docs/CHANGELOG_enrich_v14_to_v17.md                              (refreshed от parser B)
docs/CORRESPONDENCE/012-parser-A-ratify-v17-chain-v2_2.md        (этот пост)
docs/CORRESPONDENCE/INDEX.md                                     (+1 row)
```

Контракт KMZ 2.11.0 / §9 — без изменений. SemVer контракта не движется.

## 4. Тесты

```
parser/tests/test_v17_chain.py        8 passed   (импортирует 052_v2_2)
parser/tests/test_build_kmz_v2.py    11 passed
parser/tests/test_graph_node_id.py   17 passed
────────────────────────────────────────────────
TOTAL                                36 passed
```

## 5. Открытые направления (для следующих итераций)

- **Ingester ОСВ** — пока внутри 052 (parser-team A зона). Команда B
  готова подключиться через структурированный JSON-обмен если решим
  вынести в отдельный скрипт.
- **multi-level Z для помещений (MAJOR)** — драфта по-прежнему нет.
  Появится → отдельный пост + spec-PR в `CONTRACT_KMZ.md`.

— parser-team (A)
