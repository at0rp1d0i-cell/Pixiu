from __future__ import annotations

import runpy
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "script_name",
    [
        "download_fundamental_data.py",
        "download_daily_basic_data.py",
        "download_moneyflow_data.py",
        "download_moneyflow_hsgt.py",
        "download_stk_limit_data.py",
        "download_margin_history.py",
        "convert_daily_basic_to_qlib.py",
    ],
)
def test_script_entrypoints_can_import_src_modules(script_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    runpy.run_path(str(script_path), run_name="pixiu_script_import_test")
