from __future__ import annotations
from pathlib import Path

import pytest

from src.core.env import (
    apply_resolved_env,
    clear_localhost_proxy_env,
    load_dotenv_if_available,
    resolve_layered_env,
)

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


def test_resolve_layered_env_explicit_process_env_wins_and_tracks_source(tmp_path: Path):
    runtime_env_path = tmp_path / "runtime.env"
    runtime_env_path.write_text("TUSHARE_TOKEN=runtime-token\nQLIB_DATA_DIR=/runtime/qlib\n", encoding="utf-8")

    repo_env_path = tmp_path / ".env"
    repo_env_path.write_text("TUSHARE_TOKEN=repo-token\nQLIB_DATA_DIR=/repo/qlib\n", encoding="utf-8")

    resolved = resolve_layered_env(
        keys=("TUSHARE_TOKEN", "QLIB_DATA_DIR"),
        process_env={"TUSHARE_TOKEN": "process-token"},
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path,
        defaults={"QLIB_DATA_DIR": "/default/qlib"},
    )

    assert resolved.values["TUSHARE_TOKEN"] == "process-token"
    assert resolved.sources["TUSHARE_TOKEN"] == "process_env"
    assert resolved.values["QLIB_DATA_DIR"] == "/runtime/qlib"
    assert resolved.sources["QLIB_DATA_DIR"] == "user_runtime_env"


def test_resolve_layered_env_user_runtime_beats_repo(tmp_path: Path):
    runtime_env_path = tmp_path / "runtime.env"
    runtime_env_path.write_text("TUSHARE_TOKEN=runtime-token\n", encoding="utf-8")

    repo_env_path = tmp_path / ".env"
    repo_env_path.write_text("TUSHARE_TOKEN=repo-token\n", encoding="utf-8")

    resolved = resolve_layered_env(
        keys=("TUSHARE_TOKEN",),
        process_env={},
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path,
    )

    assert resolved.values["TUSHARE_TOKEN"] == "runtime-token"
    assert resolved.sources["TUSHARE_TOKEN"] == "user_runtime_env"


def test_resolve_layered_env_can_tag_profile_defaults_and_apply_to_target(tmp_path: Path):
    resolved = resolve_layered_env(
        keys=("QLIB_DATA_DIR",),
        process_env={},
        runtime_env_path=tmp_path / "missing-runtime.env",
        repo_env_path=tmp_path / "missing-repo.env",
        defaults={"QLIB_DATA_DIR": "data/qlib_bin"},
        default_source="profile",
    )
    assert resolved.values["QLIB_DATA_DIR"] == "data/qlib_bin"
    assert resolved.sources["QLIB_DATA_DIR"] == "profile"

    target: dict[str, str] = {}
    applied = apply_resolved_env(resolved, target_env=target)
    assert applied is target
    assert target["QLIB_DATA_DIR"] == "data/qlib_bin"
