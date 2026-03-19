"""Shared LLM configuration helpers."""

from .openai_compat import build_researcher_llm, get_researcher_llm_kwargs, load_dotenv_if_available

__all__ = [
    "build_researcher_llm",
    "get_researcher_llm_kwargs",
    "load_dotenv_if_available",
]
