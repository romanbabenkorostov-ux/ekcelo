"""AnthropicClient via mocked anthropic SDK (boost coverage to 95%+)."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from lot_orchestrator.llm_client import AnthropicClient, LLMResponse, MockClient


# ─────────────────────────────────────────────────────────────────────────────
#  MockClient sanity
# ─────────────────────────────────────────────────────────────────────────────

def test_mock_client_returns_configured_text():
    mc = MockClient(text="hello")
    response = mc.send("sys", "user")
    assert response.text == "hello"
    assert response.model == "mock"
    assert mc.calls == [("sys", "user")]


# ─────────────────────────────────────────────────────────────────────────────
#  AnthropicClient: тесты через monkeypatch фейкового модуля
# ─────────────────────────────────────────────────────────────────────────────

class _FakeUsage:
    def model_dump(self):
        return {"input_tokens": 100, "output_tokens": 50}


class _FakeContentBlock:
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeContentBlock(text)]
        self.usage = _FakeUsage()


def _build_fake_anthropic(*, raise_on_call: Exception | None = None,
                          raise_n_times: int = 0,
                          response_text: str = "OK"):
    """Создаёт fake-модуль anthropic с указанным поведением."""
    fake = types.ModuleType("anthropic")

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class APIStatusError(Exception):
        pass

    fake.APIConnectionError = APIConnectionError
    fake.APITimeoutError = APITimeoutError
    fake.APIStatusError = APIStatusError

    call_count = {"n": 0}

    class _Messages:
        def create(self, **kw):
            call_count["n"] += 1
            if raise_on_call is not None and call_count["n"] <= raise_n_times:
                raise raise_on_call
            return _FakeMessage(response_text)

    class Anthropic:
        def __init__(self, api_key, timeout):
            self.api_key = api_key
            self.timeout = timeout
            self.messages = _Messages()

    fake.Anthropic = Anthropic
    fake._call_count = call_count
    return fake


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Подменяет anthropic в sys.modules перед тестами."""
    fake = _build_fake_anthropic()
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def test_anthropic_client_requires_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(api_key="")


def test_anthropic_client_happy_path(fake_anthropic):
    client = AnthropicClient(api_key="sk-test", model="m1")
    response = client.send("sys", "user")
    assert isinstance(response, LLMResponse)
    assert response.text == "OK"
    assert response.model == "m1"
    assert response.usage == {"input_tokens": 100, "output_tokens": 50}


def test_anthropic_client_retries_on_connection_error(monkeypatch):
    fake = _build_fake_anthropic(
        raise_on_call=None,
        raise_n_times=0,
        response_text="recovered",
    )
    # Подменим create чтобы первые 2 вызова падали с APIConnectionError.
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    state = {"calls": 0}
    original_create = fake.Anthropic(api_key="x", timeout=1).messages.create

    class _RetryMessages:
        def create(self, **kw):
            state["calls"] += 1
            if state["calls"] <= 2:
                raise fake.APIConnectionError("network down")
            return _FakeMessage("recovered")

    class _Anthropic:
        def __init__(self, api_key, timeout):
            self.messages = _RetryMessages()

    fake.Anthropic = _Anthropic
    sleeps = []
    client = AnthropicClient(
        api_key="sk-test",
        retries=3,
        sleep=lambda s: sleeps.append(s),
    )
    response = client.send("sys", "user")
    assert response.text == "recovered"
    assert state["calls"] == 3
    assert sleeps == [2, 4]  # exp backoff после первых двух попыток


def test_anthropic_client_raises_after_max_retries(monkeypatch):
    fake = _build_fake_anthropic()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    class _AlwaysFailMessages:
        def create(self, **kw):
            raise fake.APITimeoutError("always timeout")

    class _Anthropic:
        def __init__(self, api_key, timeout):
            self.messages = _AlwaysFailMessages()

    fake.Anthropic = _Anthropic
    client = AnthropicClient(api_key="sk-test", retries=2, sleep=lambda s: None)
    with pytest.raises(fake.APITimeoutError):
        client.send("sys", "user")


def test_anthropic_client_status_error_not_retried(monkeypatch):
    fake = _build_fake_anthropic()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    state = {"calls": 0}

    class _ApiErrorMessages:
        def create(self, **kw):
            state["calls"] += 1
            raise fake.APIStatusError("4xx")

    class _Anthropic:
        def __init__(self, api_key, timeout):
            self.messages = _ApiErrorMessages()

    fake.Anthropic = _Anthropic
    client = AnthropicClient(api_key="sk-test", retries=3, sleep=lambda s: None)
    with pytest.raises(fake.APIStatusError):
        client.send("sys", "user")
    assert state["calls"] == 1  # без retry
