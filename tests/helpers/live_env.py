"""Helpers for live / e2e researcher environment setup."""
from __future__ import annotations

import os
from functools import lru_cache

import pytest

_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def load_researcher_dotenv() -> None:
    """Load researcher env from .env if present."""
    from src.core.env import load_dotenv_if_available

    load_dotenv_if_available()


def researcher_api_key_available() -> bool:
    """Return whether the live researcher API key is available."""
    return bool(os.getenv("RESEARCHER_API_KEY"))


@lru_cache(maxsize=1)
def researcher_live_env_ready() -> bool:
    """Return whether live/e2e researcher env is ready after one dotenv load."""
    load_researcher_dotenv()
    return researcher_api_key_available()


def ensure_researcher_live_env_or_skip() -> None:
    """Skip the current live/e2e test when researcher credentials are unavailable."""
    if not researcher_live_env_ready():
        pytest.skip("RESEARCHER_API_KEY 未设置，跳过真实场景测试")


def clear_proxy_env(monkeypatch) -> None:
    """Clear proxy env vars that break httpx / ChatOpenAI initialization."""
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
