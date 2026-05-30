"""Конфигурация orchestrator'а через env (см. orchestrator_spec.md §8)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PROMPTS = _REPO_ROOT / "obsidian" / "Prompts" / "llm_memorandum_pipeline"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    prompts_path: Path = _DEFAULT_PROMPTS
    llm_timeout_s: int = 120
    llm_retries: int = 3
    fuzzy_match_threshold: float = 0.7
    auto_yes: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            prompts_path=Path(os.getenv("PROMPTS_PATH", str(_DEFAULT_PROMPTS))),
            llm_timeout_s=int(os.getenv("LLM_TIMEOUT_S", "120")),
            llm_retries=int(os.getenv("LLM_RETRIES", "3")),
            fuzzy_match_threshold=float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.7")),
            auto_yes=os.getenv("AUTO_YES", "false").lower() in ("true", "1", "yes"),
        )
