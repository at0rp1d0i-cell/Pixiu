"""Helpers for building OpenAI-compatible LLM clients with consistent env resolution."""
from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI

from .settings import get_llm_profile_settings


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def get_researcher_llm_kwargs(
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    profile: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a consistent OpenAI-compatible config for researcher-facing LLM calls."""
    load_dotenv_if_available()

    kwargs: dict[str, Any] = {
        "model": os.getenv("RESEARCHER_MODEL", os.getenv("OPENAI_MODEL", "deepseek-chat")),
        "base_url": os.getenv("RESEARCHER_BASE_URL", os.getenv("OPENAI_API_BASE")),
        "api_key": os.getenv("RESEARCHER_API_KEY", os.getenv("OPENAI_API_KEY")),
    }

    profile_kwargs: dict[str, Any] = {}
    if profile is not None:
        profile_kwargs = get_llm_profile_settings(profile).to_kwargs()
        kwargs.update(profile_kwargs)

    if temperature is not None:
        kwargs["temperature"] = temperature
    elif "temperature" not in kwargs:
        raise TypeError("temperature is required when no llm profile is provided")

    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    for key, value in overrides.items():
        if value is not None:
            kwargs[key] = value
    return kwargs


def build_researcher_llm(
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    profile: str | None = None,
    **overrides: Any,
) -> ChatOpenAI:
    """Create a ChatOpenAI client using the shared OpenAI-compatible config."""
    return ChatOpenAI(
        **get_researcher_llm_kwargs(
            temperature=temperature,
            max_tokens=max_tokens,
            profile=profile,
            **overrides,
        )
    )
