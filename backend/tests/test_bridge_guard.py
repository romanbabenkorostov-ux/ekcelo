"""Bridge-guard (cycle 15 M2 burst 1) — slice ⊆ full C2.

Инвариант: каждая таблица из `contracts/bundle-db-slice/schema.json`
(моя 8-таблиц wire-форма для Bundle) должна существовать в полной
backend C2-схеме (parser-team work в `contracts/db/`).

Если parser-team удалит/переименует таблицу, которую переносит Bundle —
этот тест падает. Соответственно, если я добавлю новую таблицу в slice,
которой нет в их full — тоже падает.

Soft-guard: если файлы parser-team отсутствуют в репо (например свежий
клон до их работы), тест пропускается с `pytest.skip`. На production main
файлы есть.

См. также:
- `contracts/bundle-db-slice/schema.json` (моё).
- `contracts/db/SCHEMA_SPEC.md` (parser-team) — ожидается.
- `docs/CORRESPONDENCE/029-bundle-db-slice-namespace.md` (post 029).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SLICE = _REPO_ROOT / "contracts" / "bundle-db-slice" / "schema.json"
_FULL_SPEC = _REPO_ROOT / "contracts" / "db" / "SCHEMA_SPEC.md"
_FULL_MODELS = _REPO_ROOT / "contracts" / "db" / "models.py"


def _slice_table_names() -> set[str]:
    data = json.loads(_SLICE.read_text(encoding="utf-8"))
    return set(data["tables"].keys())


def _slice_tables_for_bridge() -> set[str]:
    """Таблицы slice, для которых ожидаем синхрон с parser-team full C2.

    §7 (geo entities, ADR-002) — наш не-ЕГРН локальный слой; parser-team пока
    про него не знает (post 029-stream ещё не отправлен). До adoption — этот
    слой исключаем из bridge-проверки. Когда parser-team добавит §7 в full C2,
    фильтр снять.
    """
    data = json.loads(_SLICE.read_text(encoding="utf-8"))
    return {
        name for name, tdef in data["tables"].items()
        if str(tdef.get("section")) != "7"
    }


def _read_any(paths: list[Path]) -> str | None:
    """Возвращает контент первого существующего файла; None если все отсутствуют."""
    for p in paths:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты bridge-guard
# ─────────────────────────────────────────────────────────────────────────────

def test_slice_schema_exists() -> None:
    """Моя slice-схема должна быть на месте."""
    assert _SLICE.is_file(), f"отсутствует {_SLICE}"
    tables = _slice_table_names()
    assert tables, "slice пустой"


def test_each_slice_table_appears_in_full_c2() -> None:
    """Каждая slice-таблица должна упоминаться в parser-team's full C2."""
    content = _read_any([_FULL_SPEC, _FULL_MODELS])
    if content is None:
        pytest.skip(
            "parser-team's contracts/db/SCHEMA_SPEC.md или models.py отсутствуют "
            "(свежий клон до их работы) — bridge-guard пропущен"
        )
    missing: list[str] = []
    for tname in sorted(_slice_tables_for_bridge()):
        # ищем "objects" как `objects`, "objects ", "objects(", "objects:" и т.п.
        # без жёсткой привязки к синтаксису — текстовый match достаточен.
        if tname not in content:
            missing.append(tname)
    assert not missing, (
        "slice-таблицы НЕ найдены в parser-team's full C2:\n"
        + "\n".join(f"  - {t}" for t in missing)
        + f"\n(искали в {[_FULL_SPEC.name, _FULL_MODELS.name]})\n"
        "Если parser-team переименовали/удалили — обсудить в post 029."
    )


def test_slice_namespace_isolated_from_full() -> None:
    """contracts/db/ не должен содержать наш schema.json (после переноса)."""
    legacy = _REPO_ROOT / "contracts" / "db" / "schema.json"
    legacy_spec = _REPO_ROOT / "contracts" / "db" / "DB_SPEC.md"
    assert not legacy.is_file(), (
        f"{legacy} остался — namespace не разделён. См. post 029."
    )
    assert not legacy_spec.is_file(), (
        f"{legacy_spec} остался — namespace не разделён. См. post 029."
    )
