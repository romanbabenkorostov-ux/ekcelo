"""Загрузка `.md` промптов из `PROMPTS_PATH` + сборка system/user prompts
(orchestrator_spec.md §4 Фаза 2)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptBundle:
    system: str
    user: str


def build_prompts(
    prompts_path: Path,
    *,
    enrich_json_text: str,
    market_analysis: str,
    existing_market_template: str,
    graph_status: bool,
) -> PromptBundle:
    """Sys = market_injector + section'а из 02_memorandum_prompt (исключая ЭТАП 0).

    User = шаблон ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ из 02 с подставленными переменными.
    """
    injector = _read(prompts_path / "market_injector_prompt_block.md")
    memorandum_md = _read(prompts_path / "02_memorandum_prompt.md")

    system_part = _extract_system_part(memorandum_md)
    user_template = _extract_user_template(memorandum_md)

    system = f"{injector.strip()}\n\n{system_part.strip()}\n"
    user = _render_user(
        user_template,
        enrich_json_text=enrich_json_text,
        market_analysis=market_analysis,
        existing_market_template=existing_market_template,
        graph_status="TRUE" if graph_status else "FALSE",
    )
    return PromptBundle(system=system, user=user)


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"prompt не найден: {path}")
    return path.read_text(encoding="utf-8")


_SYS_HEADER = "## СИСТЕМНЫЙ ПРОМПТ"
_USER_HEADER = "## ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ"
_STAGE_ZERO_HEADER = "### ЭТАП 0"


def _extract_system_part(md: str) -> str:
    """Из 02_memorandum_prompt.md берём блок СИСТЕМНЫЙ ПРОМПТ, опуская ЭТАП 0 (он в injector'е)."""
    sys_start = md.find(_SYS_HEADER)
    user_start = md.find(_USER_HEADER)
    if sys_start < 0:
        return md
    end = user_start if user_start > sys_start else len(md)
    block = md[sys_start + len(_SYS_HEADER):end]

    # Удаляем секцию "### ЭТАП 0 ..." до следующего "### " или конца.
    stage_zero = block.find(_STAGE_ZERO_HEADER)
    if stage_zero >= 0:
        next_h3 = block.find("### ", stage_zero + len(_STAGE_ZERO_HEADER))
        if next_h3 < 0:
            block = block[:stage_zero]
        else:
            block = block[:stage_zero] + block[next_h3:]
    return block


def _extract_user_template(md: str) -> str:
    user_start = md.find(_USER_HEADER)
    if user_start < 0:
        return "{{ enrich_json }}\n\n{{ market_analysis }}\n"
    return md[user_start + len(_USER_HEADER):]


def _render_user(
    template: str,
    *,
    enrich_json_text: str,
    market_analysis: str,
    existing_market_template: str,
    graph_status: str,
) -> str:
    """Лёгкая Jinja-подобная подстановка без зависимости от jinja2 в MVP."""
    out = template
    for key, value in (
        ("enrich_json", enrich_json_text),
        ("market_analysis", market_analysis),
        ("existing_market_template", existing_market_template),
        ("graph_status", graph_status),
    ):
        for placeholder in (f"{{{{ {key} }}}}", f"{{{{{key}}}}}"):
            out = out.replace(placeholder, value)
    return out
