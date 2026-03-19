from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _load_script_module(filename: str, module_name: str):
    module_path = Path(__file__).resolve().parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_day_bin(path: Path) -> np.ndarray:
    with open(path, "rb") as handle:
        _ = struct.unpack("<I", handle.read(4))[0]
        return np.fromfile(handle, dtype=np.float32)


@pytest.mark.unit
def test_convert_daily_basic_supports_overwrite(tmp_path: Path):
    module = _load_script_module("convert_daily_basic_to_qlib.py", "convert_daily_basic_to_qlib_test")
    module.FEATURES_DIR = tmp_path / "features"

    parquet_path = tmp_path / "000001.SZ.parquet"
    pd.DataFrame(
        {
            "trade_date": ["20250317"],
            "pe_ttm": [10.0],
            "pb": [1.5],
            "turnover_rate": [2.0],
            "circ_mv": [100.0],
        }
    ).to_parquet(parquet_path, index=False)

    calendar = ["2025-03-17"]
    assert module.convert_stock(parquet_path, calendar, overwrite=False) is True

    qlib_dir = module.FEATURES_DIR / "sz000001"
    pb_bin = qlib_dir / "pb.day.bin"
    np.testing.assert_allclose(_read_day_bin(pb_bin), np.array([1.5], dtype=np.float32))

    pd.DataFrame(
        {
            "trade_date": ["20250317"],
            "pe_ttm": [11.0],
            "pb": [2.5],
            "turnover_rate": [3.0],
            "circ_mv": [110.0],
        }
    ).to_parquet(parquet_path, index=False)

    assert module.convert_stock(parquet_path, calendar, overwrite=False) is False
    np.testing.assert_allclose(_read_day_bin(pb_bin), np.array([1.5], dtype=np.float32))

    assert module.convert_stock(parquet_path, calendar, overwrite=True) is True
    np.testing.assert_allclose(_read_day_bin(pb_bin), np.array([2.5], dtype=np.float32))


@pytest.mark.unit
def test_daily_basic_download_retries_empty_response_on_next_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_script_module("download_daily_basic_data.py", "download_daily_basic_data_test")
    module.PROGRESS_FILE = tmp_path / "daily_basic_progress.json"
    module.DAILY_BASIC_STAGING_DIR = tmp_path / "daily_basic"
    module.CHECKPOINT_EVERY = 1
    module.SLEEP_BETWEEN_STOCKS = 0

    progress = module.load_progress()
    stock_code = "000001.SZ"

    monkeypatch.setattr(module, "fetch_daily_basic", lambda ts_code: pd.DataFrame())
    module.download_all(progress, [stock_code])

    assert stock_code not in progress["done"]
    assert progress["empty_counts"][stock_code] == 1
    assert stock_code not in progress["empty_done"]

    non_empty = pd.DataFrame(
        {
            "ts_code": [stock_code],
            "trade_date": ["20250317"],
            "turnover_rate": [1.2],
            "pe_ttm": [10.0],
            "pb": [1.1],
            "circ_mv": [100.0],
        }
    )
    monkeypatch.setattr(module, "fetch_daily_basic", lambda ts_code: non_empty)
    module.download_all(progress, [stock_code])

    assert stock_code in progress["done"]
    assert stock_code not in progress["empty_counts"]
    assert stock_code not in progress["empty_done"]
    assert (module.DAILY_BASIC_STAGING_DIR / f"{stock_code}.parquet").exists()
