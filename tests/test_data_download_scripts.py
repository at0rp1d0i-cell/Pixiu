from __future__ import annotations

import importlib.util
import json
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


def _run_resume_contract(
    *,
    module,
    progress_file: Path,
    staging_dir: Path,
    fetch_attr: str,
    stock_code: str,
    empty_frame: pd.DataFrame,
    materialized_frame: pd.DataFrame,
) -> None:
    module.PROGRESS_FILE = progress_file
    module.CHECKPOINT_EVERY = 1
    module.SLEEP_BETWEEN_STOCKS = 0

    progress = module.load_progress()
    assert progress["done"] == []
    assert progress["failed"] == {}

    setattr(module, fetch_attr, lambda ts_code: empty_frame)
    module.download_all(progress, [stock_code])

    assert stock_code not in progress["done"]
    assert progress["empty_counts"][stock_code] == 1
    assert stock_code not in progress["empty_done"]
    assert progress_file.exists()

    with progress_file.open(encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["empty_counts"][stock_code] == 1

    reloaded = module.load_progress()
    setattr(module, fetch_attr, lambda ts_code: materialized_frame)
    module.download_all(reloaded, [stock_code])

    assert stock_code in reloaded["done"]
    assert stock_code not in reloaded["empty_counts"]
    assert stock_code not in reloaded["empty_done"]
    assert (staging_dir / f"{stock_code}.parquet").exists()


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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "module_name"),
    [
        ("download_moneyflow_data.py", "download_moneyflow_data_test"),
        ("download_stk_limit_data.py", "download_stk_limit_data_test"),
    ],
)
def test_tushare_scripts_round_trip_empty_retry_progress(
    tmp_path: Path,
    filename: str,
    module_name: str,
):
    module = _load_script_module(filename, module_name)
    progress_file = tmp_path / f"{module_name}.json"
    setattr(module, "PROGRESS_FILE", progress_file)

    progress = module.load_progress()
    assert progress["done"] == []
    assert progress["failed"] == {}
    assert progress["empty_counts"] == {}
    assert progress["empty_done"] == []

    progress["done"] = ["000001.SZ"]
    progress["failed"] = {"000002.SZ": "boom"}
    progress["empty_counts"] = {"000003.SZ": 1}
    progress["empty_done"] = ["000004.SZ"]
    module.save_progress(progress)

    reloaded = module.load_progress()
    assert reloaded["done"] == ["000001.SZ"]
    assert reloaded["failed"] == {"000002.SZ": "boom"}
    assert reloaded["empty_counts"] == {"000003.SZ": 1}
    assert reloaded["empty_done"] == ["000004.SZ"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "module_name", "fetch_attr", "staging_attr", "materialized_frame"),
    [
        (
            "download_daily_basic_data.py",
            "download_daily_basic_data_failure_test",
            "fetch_daily_basic",
            "DAILY_BASIC_STAGING_DIR",
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["20250317"],
                    "turnover_rate": [1.2],
                    "pe_ttm": [10.0],
                    "pb": [1.1],
                    "circ_mv": [100.0],
                }
            ),
        ),
        (
            "download_moneyflow_data.py",
            "download_moneyflow_data_failure_test",
            "fetch_moneyflow",
            "MONEYFLOW_STAGING_DIR",
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["20260318"],
                    "buy_sm_vol": [10],
                    "buy_sm_amount": [1.1],
                    "net_mf_amount": [0.5],
                }
            ),
        ),
        (
            "download_stk_limit_data.py",
            "download_stk_limit_data_failure_test",
            "fetch_stk_limit",
            "STK_LIMIT_STAGING_DIR",
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["20260318"],
                    "up_limit": [12.13],
                    "down_limit": [9.93],
                }
            ),
        ),
    ],
)
def test_tushare_scripts_retry_failed_entry_and_clear_failed_pool(
    tmp_path: Path,
    filename: str,
    module_name: str,
    fetch_attr: str,
    staging_attr: str,
    materialized_frame: pd.DataFrame,
):
    module = _load_script_module(filename, module_name)
    progress_file = tmp_path / f"{module_name}.json"
    setattr(module, "PROGRESS_FILE", progress_file)
    setattr(module, staging_attr, tmp_path / module_name)
    module.CHECKPOINT_EVERY = 1
    module.SLEEP_BETWEEN_STOCKS = 0

    stock_code = "000001.SZ"
    progress = module.load_progress()
    setattr(module, fetch_attr, lambda ts_code: (_ for _ in ()).throw(RuntimeError("boom")))
    module.download_all(progress, [stock_code])

    assert stock_code not in progress["done"]
    assert progress["failed"][stock_code] == "boom"

    reloaded = module.load_progress()
    setattr(module, fetch_attr, lambda ts_code: materialized_frame)
    module.download_all(reloaded, [stock_code])

    assert stock_code in reloaded["done"]
    assert stock_code not in reloaded["failed"]
    assert (getattr(module, staging_attr) / f"{stock_code}.parquet").exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "module_name", "fetch_attr", "staging_attr", "empty_frame", "materialized_frame"),
    [
        (
            "download_moneyflow_data.py",
            "download_moneyflow_data_test",
            "fetch_moneyflow",
            "MONEYFLOW_STAGING_DIR",
            pd.DataFrame(),
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["20260318"],
                    "buy_sm_vol": [10],
                    "buy_sm_amount": [1.1],
                    "net_mf_amount": [0.5],
                }
            ),
        ),
        (
            "download_stk_limit_data.py",
            "download_stk_limit_data_test",
            "fetch_stk_limit",
            "STK_LIMIT_STAGING_DIR",
            pd.DataFrame(),
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["20260318"],
                    "up_limit": [12.13],
                    "down_limit": [9.93],
                }
            ),
        ),
    ],
)
def test_tushare_scripts_resume_from_empty_then_materialize(
    tmp_path: Path,
    filename: str,
    module_name: str,
    fetch_attr: str,
    staging_attr: str,
    empty_frame: pd.DataFrame,
    materialized_frame: pd.DataFrame,
):
    module = _load_script_module(filename, module_name)
    progress_file = tmp_path / f"{module_name}.json"
    staging_dir = tmp_path / staging_attr.lower()
    setattr(module, staging_attr, staging_dir)

    _run_resume_contract(
        module=module,
        progress_file=progress_file,
        staging_dir=staging_dir,
        fetch_attr=fetch_attr,
        stock_code="000001.SZ",
        empty_frame=empty_frame,
        materialized_frame=materialized_frame,
    )
