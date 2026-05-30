"""Идемпотентная инициализация `Memorandum/` (orchestrator_spec.md §4 Фаза 1).

Использует canonical fuzzy-match из `parser.utils.folder_match.best_match` —
покрывает регистр / разделители, layout-swap (ЙЦУКЕН↔QWERTY), анаграммы.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from parser.utils.folder_match import best_match


_SUBDIRS = ("_data", "incoming")
_CANON = "Memorandum"


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path
    memorandum: Path
    data: Path
    incoming: Path

    @property
    def graph_canonical(self) -> Path:
        return self.memorandum / "graph.html"

    @property
    def market_template_canonical(self) -> Path:
        return self.memorandum / "market_template.md"

    def enrich_path(self, lot_id: str) -> Path:
        return self.data / f"enrich_{lot_id}.json"


def init_workspace(
    root: Path,
    *,
    fuzzy_threshold: float = 0.7,
    auto_yes: bool = True,
) -> WorkspaceLayout:
    """Создаёт `Memorandum/`, `Memorandum/_data/`, `Memorandum/incoming/`.

    Идемпотентно: повторный вызов не пересоздаёт и не перезаписывает существующие файлы.
    Если существует директория с похожим (но не каноничным) именем
    (`name_similarity` ≥ `fuzzy_threshold`) — переиспользует её при `auto_yes=True`.
    """
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"workspace_path не найден или не директория: {root}")

    memorandum = _resolve_or_create(root, _CANON, fuzzy_threshold, auto_yes)
    data = memorandum / _SUBDIRS[0]
    incoming = memorandum / _SUBDIRS[1]
    data.mkdir(exist_ok=True)
    incoming.mkdir(exist_ok=True)
    return WorkspaceLayout(root=root, memorandum=memorandum, data=data, incoming=incoming)


def _resolve_or_create(
    root: Path, canonical: str, threshold: float, auto_yes: bool
) -> Path:
    canon_path = root / canonical
    if canon_path.exists():
        return canon_path

    if auto_yes:
        siblings = [c.name for c in root.iterdir() if c.is_dir()]
        match = best_match(canonical, siblings, threshold=threshold)
        if match is not None:
            return root / match[0]

    canon_path.mkdir()
    return canon_path
