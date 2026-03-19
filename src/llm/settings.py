"""Recommended stage-specific LLM settings for OpenAI-compatible models."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMProfileSettings:
    temperature: float
    max_tokens: int | None = None
    top_p: float | None = None
    request_timeout: int | None = None
    max_retries: int | None = None

    def to_kwargs(self) -> dict[str, float | int]:
        kwargs: dict[str, float | int] = {
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        if self.request_timeout is not None:
            kwargs["request_timeout"] = self.request_timeout
        if self.max_retries is not None:
            kwargs["max_retries"] = self.max_retries
        return kwargs


LLM_PROFILES: dict[str, LLMProfileSettings] = {
    "market_analyst": LLMProfileSettings(
        temperature=0.1,
        max_tokens=1400,
        top_p=0.95,
        request_timeout=60,
        max_retries=2,
    ),
    "researcher": LLMProfileSettings(
        temperature=0.65,
        max_tokens=2200,
        top_p=0.95,
        request_timeout=90,
        max_retries=2,
    ),
    "alignment_checker": LLMProfileSettings(
        temperature=0.0,
        max_tokens=120,
        top_p=1.0,
        request_timeout=30,
        max_retries=1,
    ),
    "exploration_agent": LLMProfileSettings(
        temperature=0.2,
        max_tokens=1800,
        top_p=0.9,
        request_timeout=90,
        max_retries=1,
    ),
}


def get_llm_profile_settings(profile: str) -> LLMProfileSettings:
    try:
        return LLM_PROFILES[profile]
    except KeyError as exc:
        available = ", ".join(sorted(LLM_PROFILES))
        raise KeyError(f"unknown llm profile '{profile}', available: {available}") from exc
