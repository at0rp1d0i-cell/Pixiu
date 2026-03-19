#!/usr/bin/env python3
"""
Convert Tushare daily_basic parquet files to qlib binary format.

Input:
  data/fundamental_staging/daily_basic/{ts_code}.parquet

Output:
  data/qlib_bin/features/{ts_code_lower}/{field}.day.bin
"""

from __future__ import annotations

import os
import struct
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline.daily_basic import (
    DAILY_BASIC_STAGING_DIR,
    QLIB_DAILY_BASIC_FIELDS,
    build_daily_basic_feature_arrays,
    ts_code_to_qlib,
)
from src.core.env import load_dotenv_if_available

load_dotenv_if_available()

_qlib_env = os.getenv("QLIB_DATA_DIR")
if _qlib_env:
    QLIB_DIR = Path(_qlib_env) if os.path.isabs(_qlib_env) else PROJECT_ROOT / _qlib_env
else:
    QLIB_DIR = PROJECT_ROOT / "data" / "qlib_bin"
CALENDAR_FILE = QLIB_DIR / "calendars" / "day.txt"
FEATURES_DIR = QLIB_DIR / "features"


def _write_bin(path: Path, start_idx: int, values: np.ndarray) -> None:
    with open(path, "wb") as handle:
        handle.write(struct.pack("<I", start_idx))
        values.astype(np.float32).tofile(handle)


def read_calendar() -> list[str]:
    return [day.strip() for day in CALENDAR_FILE.read_text().splitlines() if day.strip()]


def convert_stock(parquet_path: Path, calendar: list[str], *, overwrite: bool = False) -> bool:
    ts_code = parquet_path.stem
    qlib_dir = FEATURES_DIR / ts_code_to_qlib(ts_code)
    existing = {path.name for path in qlib_dir.glob("*.day.bin")} if qlib_dir.exists() else set()

    target_bins = {f"{field}.day.bin" for field in QLIB_DAILY_BASIC_FIELDS}
    if not overwrite and existing.issuperset(target_bins):
        return False

    df = pd.read_parquet(parquet_path)
    if df.empty or "trade_date" not in df.columns:
        return False

    arrays = build_daily_basic_feature_arrays(df, calendar)
    qlib_dir.mkdir(parents=True, exist_ok=True)

    wrote_any = False
    for field, array in arrays.items():
        bin_path = qlib_dir / f"{field}.day.bin"
        if bin_path.exists() and not overwrite:
            continue
        _write_bin(bin_path, 0, array)
        wrote_any = True

    return wrote_any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert staged Tushare daily_basic parquet files to qlib bins.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite existing daily_basic qlib bins instead of skipping them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not DAILY_BASIC_STAGING_DIR.exists():
        print(
            f"Staging directory not found: {DAILY_BASIC_STAGING_DIR}\n"
            "Run the daily_basic downloader first. Exiting.",
            flush=True,
        )
        sys.exit(0)

    if not CALENDAR_FILE.exists():
        print(
            f"Calendar file not found: {CALENDAR_FILE}\n"
            "Run scripts/download_qlib_data.py first. Exiting.",
            flush=True,
        )
        sys.exit(0)

    calendar = read_calendar()
    parquet_files = sorted(DAILY_BASIC_STAGING_DIR.glob("*.parquet"))
    if not parquet_files:
        print(f"No parquet files found in {DAILY_BASIC_STAGING_DIR}. Exiting.", flush=True)
        sys.exit(0)

    converted = 0
    skipped = 0
    for parquet_file in parquet_files:
        if convert_stock(parquet_file, calendar, overwrite=args.overwrite):
            converted += 1
        else:
            skipped += 1

    print(
        f"daily_basic conversion complete: converted={converted}, skipped={skipped}, "
        f"calendar_days={len(calendar)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
