from __future__ import annotations

from pathlib import Path

import pytest

from src.core.env import load_dotenv_if_available

pytestmark = pytest.mark.unit


def test_load_dotenv_if_available_reads_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("TUSHARE_TOKEN=test-token\n", encoding="utf-8")

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    load_dotenv_if_available(dotenv_path)

    assert __import__("os").environ.get("TUSHARE_TOKEN") == "test-token"
