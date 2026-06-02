"""LLM-клиент — Protocol-based abstraction.

Re-export `lot_orchestrator.llm_client.{AnthropicClient, LLMClient, MockClient}`.

API-ключ Anthropic нужен ТОЛЬКО при `AnthropicClient(api_key=...)`.
`MockClient` используется в тестах / smoke без сети.
См. `obsidian/UserGuide/install.md` раздел «Когда нужен ANTHROPIC_API_KEY».
"""
from __future__ import annotations

from lot_orchestrator.llm_client import (
    AnthropicClient,
    LLMClient,
    LLMResponse,
    MockClient,
)


__all__ = ["AnthropicClient", "LLMClient", "LLMResponse", "MockClient"]
