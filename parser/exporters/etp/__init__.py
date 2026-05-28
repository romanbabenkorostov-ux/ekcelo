"""parser/exporters/etp — экспорт объектов сюрвея в ЭТП.

См. SPEC `docs/etp_export/SPEC_etp_export.md` §6.

Stage 1: build_lot_context — собирает ctx из БД для одного лота.
Stage 2: text_render — Jinja-рендер ctx → текст для платформы.
Stage 3: appendix + cli — Markdown-приложение + CLI экспорт.
Stage 4: etl_osv — импорт survey-листа экономиста в БД.
"""
from parser.exporters.etp.appendix import build_lot_appendix
from parser.exporters.etp.build_lot_context import build_lot_context
from parser.exporters.etp.etl_osv import apply_osv, load_osv
from parser.exporters.etp.text_render import (
    available_modes,
    available_platforms,
    render_lot_description,
)

__all__ = [
    "build_lot_context",
    "render_lot_description",
    "build_lot_appendix",
    "available_platforms",
    "available_modes",
    "load_osv",
    "apply_osv",
]
