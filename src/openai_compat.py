"""OpenAI model-parameter compatibility helpers.

This project supports developer-selected OpenAI models. Some model families
reject certain request parameters (e.g. GPT-5 base models reject `temperature`).

We keep a small, explicit mapping here (no runtime auto-learning) so behavior is
predictable and easy to adjust.
"""

from __future__ import annotations

from typing import Any


_UNSUPPORTED_SAMPLING_PARAMS = {"temperature", "top_p", "logprobs"}
_UNSUPPORTED_PENALTY_PARAMS = {"frequency_penalty", "presence_penalty"}


def _is_gpt5_base_model(model: str) -> bool:
    """
    GPT-5 base family models (gpt-5, gpt-5-mini, gpt-5-nano, gpt-5-chat, dated variants)
    do not support sampling params like temperature/top_p/logprobs.

    Ref: OpenAI GPT-5 model guidance (parameter compatibility).
    """
    model = (model or "").strip()
    if not model.startswith("gpt-5"):
        return False
    # gpt-5.1 / gpt-5.2 are handled separately
    return not (model.startswith("gpt-5.1") or model.startswith("gpt-5.2"))


def _is_gpt51_or_gpt52_restricted_variant(model: str) -> bool:
    """
    Some GPT-5.1 / GPT-5.2 variants run with non-none reasoning by design
    (e.g. '*-pro', '*-thinking'), which makes sampling params unsupported.
    """
    model = (model or "").strip()
    if not (model.startswith("gpt-5.1") or model.startswith("gpt-5.2")):
        return False
    lowered = model.lower()
    return ("thinking" in lowered) or ("pro" in lowered)


def _is_o_series_model(model: str) -> bool:
    """o-series reasoning models reject sampling + penalty params."""
    model = (model or "").strip()
    return model.startswith(("o1", "o3", "o4"))


def unsupported_openai_chat_params(model: str, *, reasoning_effort: str | None = None) -> set[str]:
    """
    Return a set of Chat Completions params to omit for a given model.

    Notes:
    - GPT-5 base models: temperature/top_p/logprobs are unsupported.
    - GPT-5.1 / GPT-5.2: these params are only supported when reasoning_effort='none'.
      If the caller explicitly sets a non-none reasoning effort, we omit them.
    - o-series: sampling + penalty params are unsupported.
    """
    model = (model or "").strip()
    if not model:
        return set()

    if _is_gpt5_base_model(model):
        return set(_UNSUPPORTED_SAMPLING_PARAMS)

    if model.startswith(("gpt-5.1", "gpt-5.2")):
        if _is_gpt51_or_gpt52_restricted_variant(model):
            return set(_UNSUPPORTED_SAMPLING_PARAMS)
        if reasoning_effort is not None and reasoning_effort != "none":
            return set(_UNSUPPORTED_SAMPLING_PARAMS)

    if _is_o_series_model(model):
        return set(_UNSUPPORTED_SAMPLING_PARAMS | _UNSUPPORTED_PENALTY_PARAMS)

    return set()


def filter_openai_chat_completions_kwargs(create_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of kwargs with known-unsupported params removed."""
    model = str(create_kwargs.get("model") or "").strip()
    reasoning_effort = create_kwargs.get("reasoning_effort")
    reasoning_effort_str = reasoning_effort if isinstance(reasoning_effort, str) else None

    unsupported = unsupported_openai_chat_params(model, reasoning_effort=reasoning_effort_str)
    if not unsupported:
        return dict(create_kwargs)

    filtered = dict(create_kwargs)
    for param in unsupported:
        filtered.pop(param, None)
    return filtered

