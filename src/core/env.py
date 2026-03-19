"""Shared environment helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def load_dotenv_if_available(dotenv_path: Optional[str | Path] = None) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=dotenv_path)
    except ImportError:
        pass


def clear_localhost_proxy_env() -> list[str]:
    """Remove localhost proxy variables that break direct vendor API calls.

    This keeps explicit non-local proxies intact while stripping stale local
    proxy settings such as `127.0.0.1:17890`, which frequently appear in shell
    startup files and cause Tushare downloads to fail in unattended runs.
    """

    cleared: list[str] = []
    for key in _PROXY_VARS:
        value = os.environ.get(key)
        if value and ("127.0.0.1" in value or "localhost" in value):
            os.environ.pop(key, None)
            cleared.append(key)
    return cleared
