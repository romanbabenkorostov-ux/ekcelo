"""Перехват служебного блока `<SYSTEM_MARKET_TEMPLATE>` из LLM-ответа
(orchestrator_spec.md §4 Фаза 3.2)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_SMT_RE = re.compile(r"<SYSTEM_MARKET_TEMPLATE>(.*?)</SYSTEM_MARKET_TEMPLATE>", re.DOTALL)


@dataclass(frozen=True)
class MarketTemplateExtraction:
    cleaned_response: str
    template_written: bool
    template_path: Path | None
    warning: str | None = None


def extract_and_write_market_template(
    response_text: str, canonical_path: Path
) -> MarketTemplateExtraction:
    """Если найден блок — извлекает, перезаписывает `canonical_path`, удаляет из ответа.

    Идемпотентно: повторный запуск с тем же содержимым → файл идентичен (overwrite same bytes).
    """
    match = _SMT_RE.search(response_text)
    if not match:
        return MarketTemplateExtraction(
            cleaned_response=response_text,
            template_written=False,
            template_path=None,
            warning="SYSTEM_MARKET_TEMPLATE block not found",
        )

    content = match.group(1).strip()
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text(content + "\n", encoding="utf-8")

    cleaned = _SMT_RE.sub("", response_text, count=1).strip()
    return MarketTemplateExtraction(
        cleaned_response=cleaned,
        template_written=True,
        template_path=canonical_path,
    )
