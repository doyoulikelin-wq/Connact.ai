"""LLM Service - Abstraction layer for AI model calls.

This module provides a unified interface for calling different LLM providers
(Gemini, OpenAI) with consistent error handling and response formatting.

Interface Contract:
- All methods return str (raw text) or dict (parsed JSON)
- All methods raise LLMServiceError on failure
- Callers should not depend on specific LLM provider details

Owner: Core Team (Senior)
Status: Interface Defined - Implementation Pending
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

# Optional Gemini dependency (keep import-time light for tests/CI)
try:
    import google.generativeai as genai  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    genai = None  # type: ignore
from openai import OpenAI

from config import DEFAULT_MODEL, GEMINI_SEARCH_MODEL


class LLMServiceError(Exception):
    """Raised when LLM call fails."""
    pass


@dataclass
class LLMResponse:
    """Standardized response from LLM calls."""
    content: str
    model: str
    provider: Literal["gemini", "openai"]
    raw_response: Any = None


def _extract_openai_error_info(exc: Exception) -> dict[str, Any] | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err
        return body

    response = getattr(exc, "response", None)
    if response is not None:
        try:
            data = response.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return err
            return data

    return None


def _get_openai_unsupported_param(exc: Exception) -> str | None:
    info = _extract_openai_error_info(exc) or {}
    param = info.get("param") if isinstance(info, dict) else None
    code = info.get("code") if isinstance(info, dict) else None
    if isinstance(param, str) and code in {"unsupported_value", "unsupported_parameter"}:
        return param.split(".", 1)[0]

    message = str(info.get("message") if isinstance(info, dict) else "") or str(exc)
    match = re.search(r"Unsupported value: '([^']+)'", message)
    if match:
        return match.group(1).split(".", 1)[0]
    return None


_OPENAI_UNSUPPORTED_PARAMS_BY_MODEL: dict[str, set[str]] = {}


def _openai_chat_completions_create_with_fallback(client: OpenAI, create_kwargs: dict[str, Any]) -> Any:
    attempt_kwargs = dict(create_kwargs)
    model = str(attempt_kwargs.get("model") or "")

    known_unsupported = _OPENAI_UNSUPPORTED_PARAMS_BY_MODEL.get(model)
    if known_unsupported:
        for param in known_unsupported:
            attempt_kwargs.pop(param, None)

    for _attempt in range(6):
        try:
            return client.chat.completions.create(**attempt_kwargs)
        except Exception as exc:
            unsupported_param = _get_openai_unsupported_param(exc)
            if unsupported_param and unsupported_param in attempt_kwargs and unsupported_param not in {"model", "messages"}:
                attempt_kwargs.pop(unsupported_param, None)
                if model:
                    _OPENAI_UNSUPPORTED_PARAMS_BY_MODEL.setdefault(model, set()).add(unsupported_param)
                print(f"[OpenAI compat] model={model} dropped unsupported param={unsupported_param}")
                continue
            raise

    return client.chat.completions.create(**attempt_kwargs)


def _extract_json_from_text(text: str) -> str:
    json_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(json_block_pattern, text)
    if matches:
        for match in matches:
            candidate = match.strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

    brace_start = text.find("{")
    if brace_start != -1:
        depth = 0
        for i, char in enumerate(text[brace_start:], brace_start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[brace_start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        continue

    return text


def _ensure_strict_json(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        extracted = _extract_json_from_text(cleaned)
        json.loads(extracted)
        return extracted


class BaseLLMService(ABC):
    """Abstract base class for LLM services."""
    
    @abstractmethod
    def call(self, prompt: str, *, json_mode: bool = False) -> str:
        """Call the LLM with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            json_mode: If True, expect JSON response
            
        Returns:
            str: The LLM response text
            
        Raises:
            LLMServiceError: If the call fails
        """
        pass
    
    @abstractmethod
    def call_with_search(self, prompt: str, *, json_mode: bool = False) -> str:
        """Call the LLM with web search grounding.
        
        Args:
            prompt: The prompt to send to the LLM
            json_mode: If True, expect JSON response
            
        Returns:
            str: The LLM response text with web-grounded information
            
        Raises:
            LLMServiceError: If the call fails
        """
        pass


class GeminiService(BaseLLMService):
    """Google Gemini LLM service implementation."""
    
    def __init__(self, model: str = DEFAULT_MODEL, search_model: str = GEMINI_SEARCH_MODEL):
        self.model = model
        self.search_model = search_model
        self._configured = False
    
    def _configure(self) -> None:
        """Configure Gemini API (lazy initialization)."""
        if self._configured:
            return
        if genai is None:
            raise LLMServiceError(
                "google-generativeai is not installed. Install dependencies with `python -m pip install -r requirements.txt`."
            )
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise LLMServiceError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        self._configured = True
    
    def call(self, prompt: str, *, json_mode: bool = False) -> str:
        """Call Gemini model."""
        self._configure()
        try:
            gen_config = None
            if json_mode:
                gen_config = genai.GenerationConfig(
                    response_mime_type="application/json"
                )
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt, generation_config=gen_config)
            return response.text
        except Exception as e:
            raise LLMServiceError(f"Gemini call failed: {e}") from e
    
    def call_with_search(self, prompt: str, *, json_mode: bool = False) -> str:
        """Call Gemini with Google Search grounding."""
        self._configure()
        try:
            from google.generativeai import protos
            
            gen_config = None
            if json_mode:
                gen_config = genai.GenerationConfig(
                    response_mime_type="application/json"
                )
            
            model = genai.GenerativeModel(self.search_model)
            google_search_tool = genai.Tool(
                google_search=protos.GoogleSearch()
            )
            response = model.generate_content(
                prompt,
                tools=[google_search_tool],
                generation_config=gen_config,
            )
            return response.text
        except Exception as e:
            raise LLMServiceError(f"Gemini search call failed: {e}") from e


class OpenAIService(BaseLLMService):
    """OpenAI LLM service implementation."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._client: OpenAI | None = None
    
    def _get_client(self) -> OpenAI:
        """Get or create OpenAI client (lazy initialization)."""
        if self._client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise LLMServiceError("OPENAI_API_KEY environment variable not set")
            self._client = OpenAI(api_key=api_key)
        return self._client
    
    def call(self, prompt: str, *, json_mode: bool = False) -> str:
        """Call OpenAI model."""
        try:
            client = self._get_client()
            create_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
            if json_mode:
                create_kwargs["response_format"] = {"type": "json_object"}

            response = _openai_chat_completions_create_with_fallback(client, create_kwargs)
            content = response.choices[0].message.content or ""
            if json_mode:
                return _ensure_strict_json(content)
            return content
        except Exception as e:
            raise LLMServiceError(f"OpenAI call failed: {e}") from e
    
    def call_with_search(self, prompt: str, *, json_mode: bool = False) -> str:
        """OpenAI does not support native web search - falls back to regular call."""
        # Note: OpenAI's web_search tool type is not supported in standard API
        return self.call(prompt, json_mode=json_mode)


# Default service instance (can be swapped for testing)
class LLMService:
    """Facade for LLM services with provider switching."""
    
    _instance: BaseLLMService | None = None
    
    @classmethod
    def get_instance(cls) -> BaseLLMService:
        """Get the configured LLM service instance."""
        if cls._instance is None:
            cls._instance = GeminiService()
        return cls._instance
    
    @classmethod
    def set_instance(cls, service: BaseLLMService) -> None:
        """Set a custom LLM service (useful for testing)."""
        cls._instance = service
    
    @classmethod
    def reset(cls) -> None:
        """Reset to default service."""
        cls._instance = None


# Convenience functions for backward compatibility
def call_llm(prompt: str, *, json_mode: bool = False) -> str:
    """Call the default LLM service."""
    return LLMService.get_instance().call(prompt, json_mode=json_mode)


def call_llm_with_search(prompt: str, *, json_mode: bool = False) -> str:
    """Call the default LLM service with web search."""
    return LLMService.get_instance().call_with_search(prompt, json_mode=json_mode)
