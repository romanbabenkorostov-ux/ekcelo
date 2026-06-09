"""Идемпотентность Memorandum/ + fuzzy-match."""
from __future__ import annotations

from lot_orchestrator.workspace import init_workspace


def test_creates_memorandum_idempotent(tmp_path):
    layout1 = init_workspace(tmp_path)
    (layout1.memorandum / "marker.txt").write_text("preserved", encoding="utf-8")
    layout2 = init_workspace(tmp_path)
    assert layout1.memorandum == layout2.memorandum
    assert (layout2.memorandum / "marker.txt").read_text(encoding="utf-8") == "preserved"
    assert layout2.data.exists()
    assert layout2.incoming.exists()


def test_fuzzy_match_picks_lowercase_variant(tmp_path):
    """Существующий `memorandum/` (lowercase) переиспользуется при auto_yes=True."""
    legacy = tmp_path / "memorandum"
    legacy.mkdir()
    (legacy / "old.txt").write_text("x", encoding="utf-8")
    layout = init_workspace(tmp_path, fuzzy_threshold=0.7, auto_yes=True)
    assert layout.memorandum == legacy


def test_fuzzy_match_creates_canonical_when_no_close_match(tmp_path):
    (tmp_path / "random_dir").mkdir()
    layout = init_workspace(tmp_path, fuzzy_threshold=0.9, auto_yes=True)
    assert layout.memorandum.name == "Memorandum"


def test_raises_if_root_missing(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        init_workspace(tmp_path / "nope")


def test_fuzzy_match_picks_separator_variant(tmp_path):
    """`Memorandum_archive` ↔ `Memorandum` — separators-only diff (через canonical best_match)."""
    legacy = tmp_path / "Memorandum_old"
    legacy.mkdir()
    layout = init_workspace(tmp_path, fuzzy_threshold=0.7, auto_yes=True)
    # `Memorandum_old` нормализуется в `memorandumold` — SequenceMatcher даёт ~0.83.
    assert layout.memorandum == legacy


def test_fuzzy_match_disabled_when_auto_yes_false(tmp_path):
    """Без auto_yes — fuzzy-match не срабатывает; всегда создаётся canonical."""
    legacy = tmp_path / "memorandum"
    legacy.mkdir()
    layout = init_workspace(tmp_path, fuzzy_threshold=0.7, auto_yes=False)
    # NB: `pathlib.PureWindowsPath` сравнивает регистронезависимо
    # (`Path('Memorandum') == Path('memorandum')` на Windows = True). Поэтому
    # верифицируем КАНОНИЧЕСКОЕ имя через `.name` (str-сравнение portable).
    assert layout.memorandum.name == "Memorandum"
    assert layout.memorandum.name != legacy.name  # "Memorandum" vs "memorandum"
