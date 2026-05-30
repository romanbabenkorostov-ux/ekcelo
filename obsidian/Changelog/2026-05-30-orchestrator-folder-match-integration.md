# 2026-05-30 — Orchestrator cycle 6: интеграция canonical folder_match

## Итог
`lot_orchestrator/workspace.py` теперь использует `parser.utils.folder_match.best_match` вместо упрощённого `difflib.SequenceMatcher`. Добавлены 2 теста (separator-only diff + auto_yes=False off-switch). 33/33 orchestrator-тестов pass за 0.11s.

## Что изменилось

### Было
```python
from difflib import SequenceMatcher
# ...
ratio = SequenceMatcher(None, child.name.lower(), canon_lower).ratio()
if ratio >= threshold and auto_yes:
    return child
```
Покрывал только: регистр (`Memorandum` ↔ `memorandum`). Не покрывал layout-swap / анаграммы / разные разделители без потери символов.

### Стало
```python
from parser.utils.folder_match import best_match
# ...
siblings = [c.name for c in root.iterdir() if c.is_dir()]
match = best_match(canonical, siblings, threshold=threshold)
if match is not None:
    return root / match[0]
```
Покрывает три типичных случая (документировано в `folder_match.py`):
- **Регистр / разделители**: «Выписки PDF» ≈ «Выписки_PDF» через `normalize_name` (lowercase, ё→е, удаление пробелов / `_` / `-`).
- **Раскладка ЙЦУКЕН↔QWERTY**: «Dsgbcrb_PDF» (qwerty-набор «Выписки_PDF») → распознаётся через `detect_layout_swap`.
- **Анаграммы / перестановки**: `sorted(na) == sorted(nb)` → score=1.0.

## Артефакты

- `lot_orchestrator/workspace.py` — упрощённая реализация (-12 LOC после удаления локальной логики).
- `lot_orchestrator/tests/test_workspace.py` — +2 теста.
- `obsidian/Architecture/lot-orchestrator.md` — cycle 6 помечен ✅, удалён пункт «Нет parser.utils.folder_match» из MVP-упрощений.

## Тесты (6/6 в test_workspace.py, 33/33 в orchestrator suite)

Новые:
- `test_fuzzy_match_picks_separator_variant` — `Memorandum_old` ≈ `Memorandum` (separator diff).
- `test_fuzzy_match_disabled_when_auto_yes_false` — без `auto_yes` всегда создаётся canonical.

Существующие (без изменений):
- `test_creates_memorandum_idempotent`
- `test_fuzzy_match_picks_lowercase_variant`
- `test_fuzzy_match_creates_canonical_when_no_close_match`
- `test_raises_if_root_missing`

## Зависимости

`parser.utils.folder_match` — уже в репо, никаких новых runtime-deps. Просто перешли на canonical-источник истины.

## Дальше

- **cycle 7** — `etl_checko.py` адаптер (читает `innogrn.db` cache из `Memorandum/_data/`, пишет в `object_etp_profile.legal_extra` с `source='checko'`). См. [[ADR-002-parser-checko-integration-policy]].
- **cycle 8+** — SQLite persistence для `RunStore` + SSE streaming для статуса.
