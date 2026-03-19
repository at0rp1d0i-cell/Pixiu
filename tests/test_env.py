from __future__ import annotations

from pathlib import Path

import pytest

from src.core.env import clear_localhost_proxy_env, load_dotenv_if_available

pytestmark = pytest.mark.unit


def test_load_dotenv_if_available_reads_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("TUSHARE_TOKEN=test-token\n", encoding="utf-8")

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    load_dotenv_if_available(dotenv_path)

    assert __import__("os").environ.get("TUSHARE_TOKEN") == "test-token"


def test_clear_localhost_proxy_env_only_removes_local_proxy_values(monkeypatch: pytest.MonkeyPatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:17890")
    monkeypatch.setenv("HTTPS_PROXY", "http://localhost:7890")
    monkeypatch.setenv("ALL_PROXY", "socks5://corp-proxy.internal:1080")

    cleared = clear_localhost_proxy_env()

    assert set(cleared) == {"http_proxy", "HTTPS_PROXY"}
    assert __import__("os").environ.get("http_proxy") is None
    assert __import__("os").environ.get("HTTPS_PROXY") is None
    assert __import__("os").environ.get("ALL_PROXY") == "socks5://corp-proxy.internal:1080"
