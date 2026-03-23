"""Helpers for building OpenAI-compatible LLM clients with consistent env resolution."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from langchain_openai import ChatOpenAI

from src.core.env import load_dotenv_if_available
from .settings import get_llm_profile_settings
from .usage_ledger import UsageLedgerCallback, get_usage_ledger_callback

_ROLE_BY_PROFILE = {
    "market_analyst": "market_analyst",
    "researcher": "alpha_researcher",
    "alignment_checker": "alignment_checker",
    "exploration_agent": "exploration_agent",
}


def _ensure_runtime_metadata(kwargs: dict[str, Any], *, profile: str | None) -> None:
    existing_metadata = kwargs.get("metadata")
    metadata: dict[str, Any] = {}
    if isinstance(existing_metadata, Mapping):
        metadata = dict(existing_metadata)

    if profile and "llm_profile" not in metadata:
        metadata["llm_profile"] = profile
    if profile and "agent_role" not in metadata:
        metadata["agent_role"] = _ROLE_BY_PROFILE.get(profile, profile)
    if "provider" not in metadata:
        metadata["provider"] = "openai_compatible"
    if "model" not in metadata and kwargs.get("model"):
        metadata["model"] = kwargs["model"]

    kwargs["metadata"] = metadata


def _ensure_usage_callback(kwargs: dict[str, Any]) -> None:
    usage_callback = get_usage_ledger_callback()

    callback_manager = kwargs.get("callback_manager")
    if callback_manager is not None:
        handlers = getattr(callback_manager, "handlers", None)
        if isinstance(handlers, list) and not any(
            isinstance(handler, UsageLedgerCallback) for handler in handlers
        ):
            try:
                callback_manager.add_handler(usage_callback, inherit=True)
            except TypeError:
                callback_manager.add_handler(usage_callback)

    callbacks = kwargs.get("callbacks")
    if callbacks is None:
        kwargs["callbacks"] = [usage_callback]
        return

    if isinstance(callbacks, tuple):
        callbacks = list(callbacks)
    if isinstance(callbacks, list):
        if not any(isinstance(cb, UsageLedgerCallback) for cb in callbacks):
            callbacks.append(usage_callback)
        kwargs["callbacks"] = callbacks


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

    _ensure_runtime_metadata(kwargs, profile=profile)
    _ensure_usage_callback(kwargs)
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
