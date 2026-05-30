"""Идемпотентная инициализация `Memorandum/` (orchestrator_spec.md §4 Фаза 1).

MVP: простой mkdir-pass. Полная fuzzy-match-логика (`_resolve_existing_or_new` +
`best_match` ≥ FUZZY_MATCH_THRESHOLD) — отдельный PR
`parser/utils/folder_match.py` (extraction из `pirushin_sosn_rocha_07_init_project_v3.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


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
    (≥ `fuzzy_threshold` по SequenceMatcher) — переиспользует её при `auto_yes=True`.
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

    canon_lower = canonical.lower()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        ratio = SequenceMatcher(None, child.name.lower(), canon_lower).ratio()
        if ratio >= threshold and auto_yes:
            return child

    canon_path.mkdir()
    return canon_path
