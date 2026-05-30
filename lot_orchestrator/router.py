"""Routing очищенного response_text → final_report.md + investment_slides.md
(orchestrator_spec.md §4 Фаза 4)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_MARP_MARKER = "<!-- MARP_START -->"


@dataclass(frozen=True)
class RoutingResult:
    final_report_path: Path
    investment_slides_path: Path
    warning: str | None = None


def route_outputs(cleaned_response: str, memorandum_dir: Path) -> RoutingResult:
    """Split по `<!-- MARP_START -->` → 2 файла. Если маркера нет — всё в final_report.md, slides пустой."""
    memorandum_dir.mkdir(parents=True, exist_ok=True)
    final_path = memorandum_dir / "final_report.md"
    slides_path = memorandum_dir / "investment_slides.md"

    if _MARP_MARKER in cleaned_response:
        before, _, after = cleaned_response.partition(_MARP_MARKER)
        final_path.write_text(before.rstrip() + "\n", encoding="utf-8")
        slides_path.write_text(after.lstrip(), encoding="utf-8")
        return RoutingResult(final_path, slides_path)

    final_path.write_text(cleaned_response.rstrip() + "\n", encoding="utf-8")
    slides_path.write_text("", encoding="utf-8")
    return RoutingResult(
        final_path, slides_path, warning=f"{_MARP_MARKER} не найден; slides пустой"
    )
