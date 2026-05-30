"""Поиск входов с fallback-цепочкой (orchestrator_spec.md §4 Фаза 1.6-1.8)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "dist", "build",
})


@dataclass(frozen=True)
class FoundInput:
    path: Path
    source: str  # "canonical" | "recursive"


def find_canonical_or_recursive(
    root: Path, canonical_relative: Path, pattern: str
) -> FoundInput | None:
    """Сначала канонический путь; если нет — рекурсивный поиск по regex.

    Возвращает максимально свежий (по mtime) из найденных, либо None.
    """
    canonical = root / canonical_relative
    if canonical.exists() and canonical.is_file():
        return FoundInput(path=canonical, source="canonical")
    matches = find_recursive(root, pattern)
    return FoundInput(path=matches[0], source="recursive") if matches else None


def find_recursive(root: Path, pattern: str) -> list[Path]:
    """Все совпадения regex (по basename) в дереве `root`, отсортированные по mtime desc.

    Пропускает service-директории (см. `_SKIP_DIRS`).
    """
    rx = re.compile(pattern)
    found: list[Path] = []
    for path in _walk(root):
        if path.is_file() and rx.match(path.name):
            found.append(path)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def _walk(root: Path):
    """Рекурсивный обход с пропуском `_SKIP_DIRS`."""
    stack: list[Path] = [root]
    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    continue
                stack.append(entry)
            else:
                yield entry
