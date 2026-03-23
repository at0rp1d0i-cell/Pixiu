"""Shared LLM configuration helpers."""

from .openai_compat import build_researcher_llm, get_researcher_llm_kwargs, load_dotenv_if_available
from .runtime_settings import (
    LLMRuntimeSettings,
    ProviderEnvSpec,
    ResolvedRuntimeProvider,
    load_llm_runtime_settings,
    resolve_role_provider_connection,
)
from .settings import get_llm_profile_settings, LLMProfileSettings

__all__ = [
    "build_researcher_llm",
    "get_researcher_llm_kwargs",
    "load_llm_runtime_settings",
    "resolve_role_provider_connection",
    "get_llm_profile_settings",
    "ProviderEnvSpec",
    "ResolvedRuntimeProvider",
    "LLMRuntimeSettings",
    "LLMProfileSettings",
    "load_dotenv_if_available",
]
