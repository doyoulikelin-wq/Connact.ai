"""OpenAI compatibility tests.

These tests ensure we gracefully handle model-specific unsupported parameters,
like `temperature` or `response_format` on certain OpenAI models (e.g. o1).
"""

from __future__ import annotations

import types

import pytest

import src.email_agent as email_agent


class DummyOpenAIError(Exception):
    """Mimic OpenAI SDK errors that expose a `.body` dict."""

    def __init__(self, body: dict):
        self.body = body
        super().__init__(str(body))


class DummyResponse:
    def __init__(self, content: str, *, prompt_tokens: int = 1, completion_tokens: int = 1):
        self.choices = [
            types.SimpleNamespace(
                message=types.SimpleNamespace(content=content),
            )
        ]
        self.usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class DummyChatCompletions:
    def __init__(self, results: list[object]):
        self._results = list(results)
        self.calls: list[dict] = []

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class DummyClient:
    def __init__(self, results: list[object]):
        self.chat = types.SimpleNamespace(completions=DummyChatCompletions(results))


def _err(param: str) -> DummyOpenAIError:
    return DummyOpenAIError(
        {
            "error": {
                "message": f"Unsupported value: '{param}' does not support 0 with this model. Only the default (1) value is supported.",
                "type": "invalid_request_error",
                "param": param,
                "code": "unsupported_value",
            }
        }
    )


def test_openai_json_retries_without_unsupported_params(monkeypatch: pytest.MonkeyPatch) -> None:
    email_agent._OPENAI_UNSUPPORTED_PARAMS_BY_MODEL.clear()
    dummy = DummyClient(
        [
            _err("temperature"),
            _err("response_format"),
            DummyResponse("```json\n{\"ok\": true}\n```", prompt_tokens=3, completion_tokens=2),
        ]
    )
    monkeypatch.setattr(email_agent, "_get_openai_client", lambda: dummy)

    content, usage = email_agent._call_openai_json_with_usage("prompt", model="o1-mini", step="test")

    assert content == '{"ok": true}'
    assert usage.model == "o1-mini"
    assert usage.step == "test"

    calls = dummy.chat.completions.calls
    assert len(calls) == 3
    assert "temperature" in calls[0]
    assert "response_format" in calls[0]
    assert "temperature" not in calls[1]
    assert "response_format" in calls[1]
    assert "temperature" not in calls[2]
    assert "response_format" not in calls[2]


def test_openai_chat_retries_without_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    email_agent._OPENAI_UNSUPPORTED_PARAMS_BY_MODEL.clear()
    dummy = DummyClient([_err("temperature"), DummyResponse("hello", prompt_tokens=1, completion_tokens=1)])
    monkeypatch.setattr(email_agent, "_get_openai_client", lambda: dummy)

    content, usage = email_agent._call_openai_chat_with_usage(
        "sys",
        "user",
        model="o1-mini",
        temperature=0,
        step="test",
    )

    assert content == "hello"
    assert usage.model == "o1-mini"

    calls = dummy.chat.completions.calls
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]
