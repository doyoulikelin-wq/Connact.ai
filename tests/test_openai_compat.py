"""OpenAI model-parameter compatibility tests."""

from __future__ import annotations

import types

import pytest

import src.email_agent as email_agent
import src.web_scraper as web_scraper


class DummyResponse:
    def __init__(self, content: str, *, prompt_tokens: int = 1, completion_tokens: int = 1):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]
        self.usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class DummyChatCompletions:
    def __init__(self, response: DummyResponse):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return self._response


class DummyClient:
    def __init__(self, response: DummyResponse):
        self.chat = types.SimpleNamespace(completions=DummyChatCompletions(response))


def test_email_agent_json_omits_temperature_for_gpt5_base(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = DummyClient(DummyResponse("```json\n{\"ok\": true}\n```", prompt_tokens=3, completion_tokens=2))
    monkeypatch.setattr(email_agent, "_get_openai_client", lambda: dummy)

    content, _usage = email_agent._call_openai_json_with_usage("prompt", model="gpt-5-nano", step="test")

    assert content == '{"ok": true}'
    calls = dummy.chat.completions.calls
    assert len(calls) == 1
    assert "temperature" not in calls[0]
    assert "response_format" in calls[0]


def test_email_agent_chat_omits_temperature_for_o1_models(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = DummyClient(DummyResponse("hello"))
    monkeypatch.setattr(email_agent, "_get_openai_client", lambda: dummy)

    content, _usage = email_agent._call_openai_chat_with_usage(
        "sys",
        "user",
        model="o1-mini",
        temperature=0,
        step="test",
    )

    assert content == "hello"
    calls = dummy.chat.completions.calls
    assert len(calls) == 1
    assert "temperature" not in calls[0]


def test_web_scraper_json_omits_temperature_for_gpt5_base(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = DummyClient(DummyResponse("{\"name\": \"X\", \"education\": [], \"experiences\": [], \"skills\": [], \"projects\": []}"))
    monkeypatch.setattr(web_scraper, "_get_openai_client", lambda: dummy)

    content = web_scraper._call_openai_json("prompt", model="gpt-5-nano")

    assert content.startswith("{")
    calls = dummy.chat.completions.calls
    assert len(calls) == 1
    assert "temperature" not in calls[0]
    assert "response_format" in calls[0]

