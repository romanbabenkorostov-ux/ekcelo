"""LLM-клиент: тонкая обёртка над anthropic SDK с retry × N
(orchestrator_spec.md §4 Фаза 3.1)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    usage: dict | None = None


class LLMClient(Protocol):
    def send(self, system: str, user: str) -> LLMResponse: ...


class AnthropicClient:
    """Реальный клиент. Импорт anthropic делается лениво, чтобы тесты могли мочить."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        *,
        max_tokens: int = 8192,
        timeout_s: int = 120,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY не задан")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._retries = max(1, retries)
        self._sleep = sleep

    def send(self, system: str, user: str) -> LLMResponse:
        import anthropic  # lazy

        client = anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout_s)
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                msg = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(
                    block.text for block in msg.content if getattr(block, "type", None) == "text"
                )
                usage = getattr(msg, "usage", None)
                return LLMResponse(
                    text=text,
                    model=self._model,
                    usage=usage.model_dump() if usage and hasattr(usage, "model_dump") else None,
                )
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    self._sleep(2 ** (attempt + 1))
                    continue
                raise
            except anthropic.APIStatusError:
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("LLM call exhausted retries without exception")


class MockClient:
    """Тестовый клиент — возвращает заранее заданный текст."""

    def __init__(self, text: str = "MOCK_RESPONSE", model: str = "mock"):
        self._text = text
        self._model = model
        self.calls: list[tuple[str, str]] = []

    def send(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        return LLMResponse(text=self._text, model=self._model)
