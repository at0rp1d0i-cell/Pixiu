from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "convert_fundamental_to_qlib.py"
    spec = importlib.util.spec_from_file_location("convert_fundamental_to_qlib", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pit_fill_accepts_string_dates_and_merges_on_timestamps():
    module = _load_module()
    df = pd.DataFrame(
        {
            "ann_date": ["20240110", "20240120"],
            "end_date": ["20231231", "20240331"],
            "roe": [1.1, 2.2],
        }
    )
    calendar = list(pd.to_datetime(["2024-01-05", "2024-01-10", "2024-01-15", "2024-01-22"]))

    filled = module.pit_fill(df, calendar)

    assert pd.isna(filled.loc[pd.Timestamp("2024-01-05"), "roe"])
    assert filled.loc[pd.Timestamp("2024-01-10"), "roe"] == 1.1
    assert filled.loc[pd.Timestamp("2024-01-15"), "roe"] == 1.1
    assert filled.loc[pd.Timestamp("2024-01-22"), "roe"] == 2.2


def test_pit_fill_keeps_latest_end_date_when_ann_date_collides():
    module = _load_module()
    df = pd.DataFrame(
        {
            "ann_date": ["20240430", "20240430", "20240520"],
            "end_date": ["20231231", "20240331", "20240630"],
            "roe": [1.0, 9.0, 12.0],
        }
    )
    calendar = list(pd.to_datetime(["2024-04-29", "2024-04-30", "2024-05-02", "2024-05-21"]))

    filled = module.pit_fill(df, calendar)

    assert pd.isna(filled.loc[pd.Timestamp("2024-04-29"), "roe"])
    assert filled.loc[pd.Timestamp("2024-04-30"), "roe"] == 9.0
    assert filled.loc[pd.Timestamp("2024-05-02"), "roe"] == 9.0
    assert filled.loc[pd.Timestamp("2024-05-21"), "roe"] == 12.0
