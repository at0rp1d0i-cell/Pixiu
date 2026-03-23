from __future__ import annotations

from pathlib import Path

import pytest

from src.core.orchestrator import config as orchestrator_config

pytestmark = pytest.mark.unit


def test_reports_dir_defaults_to_repo_data_reports():
    repo_root = Path(__file__).resolve().parents[1]
    expected = repo_root / "data" / "reports"

    assert orchestrator_config.REPORTS_DIR == expected
    assert orchestrator_config.REPORTS_DIR.parent.name == "data"
    assert orchestrator_config.REPORTS_DIR.name == "reports"
