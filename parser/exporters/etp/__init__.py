"""parser/exporters/etp — экспорт объектов сюрвея в ЭТП.

См. SPEC `docs/etp_export/SPEC_etp_export.md` §6.

Stage 1 (этот PR): build_lot_context — собирает ctx из БД для одного лота.
Stage 2: text_render (Jinja-шаблоны из docs/etp_export/05_*.md).
Stage 3: pdf_appendix + CLI.
"""
from parser.exporters.etp.build_lot_context import build_lot_context

__all__ = ["build_lot_context"]
