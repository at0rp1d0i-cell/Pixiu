"""Helpers for live / e2e researcher environment setup."""
from __future__ import annotations

import os

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
    """Return whether the live researcher API key is available after dotenv load."""
    load_researcher_dotenv()
    return bool(os.getenv("RESEARCHER_API_KEY"))


def clear_proxy_env(monkeypatch) -> None:
    """Clear proxy env vars that break httpx / ChatOpenAI initialization."""
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)

