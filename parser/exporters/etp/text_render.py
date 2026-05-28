"""text_render: ctx dict → текст описания лота через Jinja-шаблон.

Шаблон `templates/torgi_long_description.j2` импортирован как есть из
`docs/etp_export/05_jinja_шаблон_все_платформы.md` — содержит ветви
для всех трёх платформ (`torgi.gov.ru`, `roseltorg.ru`, `sberbank-ast.ru`)
и двух режимов (`short`, `full`).

См. SPEC §6 и §8.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import ChainableUndefined, Environment, FileSystemLoader


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "torgi_long_description.j2"

_VALID_PLATFORMS = {"torgi.gov.ru", "roseltorg.ru", "sberbank-ast.ru"}
_VALID_MODES = {"short", "full"}


# ─────────────────────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────────────────────

def render_lot_description(ctx: dict[str, Any]) -> str:
    """Отрендерить текст описания лота из ctx (см. build_lot_context).

    Платформа и режим берутся из `ctx.meta.platform` и `ctx.meta.platform_mode`.
    Шаблон сам диспатчит на нужный платформенный макрос.

    Args:
        ctx: dict совместимый с SPEC §3 (см. parser.exporters.etp.build_lot_context).

    Returns:
        Текст описания с нормализованными пробелами и переносами строк.

    Raises:
        ValueError: на неизвестную платформу или mode.
    """
    meta = ctx.get("meta") or {}
    platform = meta.get("platform")
    mode = meta.get("platform_mode", "short")
    if platform and platform not in _VALID_PLATFORMS:
        raise ValueError(f"Unknown platform: {platform!r}. Allowed: {sorted(_VALID_PLATFORMS)}")
    if mode not in _VALID_MODES:
        raise ValueError(f"Unknown platform_mode: {mode!r}. Allowed: {sorted(_VALID_MODES)}")

    template = _env().get_template(_TEMPLATE_NAME)
    raw = template.render(ctx=ctx)
    return _normalize_whitespace(raw)


def available_platforms() -> tuple[str, ...]:
    return tuple(sorted(_VALID_PLATFORMS))


def available_modes() -> tuple[str, ...]:
    return tuple(sorted(_VALID_MODES))


# ─────────────────────────────────────────────────────────────────────────────
#  Внутреннее
# ─────────────────────────────────────────────────────────────────────────────

_env_singleton: Environment | None = None


def _env() -> Environment:
    global _env_singleton
    if _env_singleton is None:
        _env_singleton = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
            # Шаблон импортирован из docs/etp_export/05_*.md и активно
            # использует `{% if obj.field %}` на словарях, которые могут не
            # содержать ключа (case C — land без building_extra). Chainable —
            # позволяет цепочки `a.b.c` молча возвращать undefined.
            undefined=ChainableUndefined,
        )
    return _env_singleton


def _normalize_whitespace(text: str) -> str:
    """Сжать множественные пустые строки и убрать висячие пробелы.

    Jinja-шаблон с массой условных вставок легко оставляет 3+ пустых
    строки подряд — нормализуем для стабильных golden-сравнений.
    """
    # Удалить trailing whitespace на каждой строке.
    text = re.sub(r"[ \t]+(?=\n)", "", text)
    # Сжать 3+ переноса до 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
