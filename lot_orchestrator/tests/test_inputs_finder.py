"""inputs_finder: canonical + fallback recursive + skip-dirs + mtime ordering."""
from __future__ import annotations

import os
import time
from pathlib import Path

from lot_orchestrator.inputs_finder import find_canonical_or_recursive, find_recursive


def test_canonical_wins_when_present(tmp_path):
    canon = tmp_path / "Memorandum" / "incoming" / "market_analysis.txt"
    canon.parent.mkdir(parents=True)
    canon.write_text("canonical", encoding="utf-8")
    (tmp_path / "deep" / "level").mkdir(parents=True)
    (tmp_path / "deep" / "level" / "market_analysis.txt").write_text("fallback", encoding="utf-8")
    found = find_canonical_or_recursive(
        tmp_path, Path("Memorandum/incoming/market_analysis.txt"), r"^market_analysis.*\.txt$"
    )
    assert found is not None
    assert found.source == "canonical"
    assert found.path.read_text(encoding="utf-8") == "canonical"


def test_finds_market_analysis_recursively(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "market_analysis.txt").write_text("deep", encoding="utf-8")
    found = find_canonical_or_recursive(
        tmp_path, Path("Memorandum/incoming/market_analysis.txt"), r"^market_analysis.*\.txt$"
    )
    assert found is not None
    assert found.source == "recursive"
    assert found.path.read_text(encoding="utf-8") == "deep"


def test_skips_service_dirs(tmp_path):
    for skip in (".git", "node_modules", "__pycache__"):
        d = tmp_path / skip
        d.mkdir()
        (d / "market_analysis.txt").write_text("hidden", encoding="utf-8")
    matches = find_recursive(tmp_path, r"^market_analysis\.txt$")
    assert matches == []


def test_mtime_ordering_picks_newest(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "market_analysis.txt").write_text("old", encoding="utf-8")
    (b / "market_analysis.txt").write_text("new", encoding="utf-8")
    older = time.time() - 60
    os.utime(a / "market_analysis.txt", (older, older))
    matches = find_recursive(tmp_path, r"^market_analysis\.txt$")
    assert len(matches) == 2
    assert matches[0].read_text(encoding="utf-8") == "new"


def test_returns_none_when_nothing_found(tmp_path):
    found = find_canonical_or_recursive(
        tmp_path, Path("Memorandum/incoming/x.txt"), r"^market_analysis.*\.txt$"
    )
    assert found is None
