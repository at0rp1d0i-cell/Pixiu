#!/usr/bin/env python3
"""
Download Tushare daily_basic for all listed A-share stocks.

Output:
  data/fundamental_staging/daily_basic/{ts_code}.parquet
  data/daily_basic_download_progress.json
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline.daily_basic import DAILY_BASIC_STAGING_DIR, get_daily_basic_field_string  # noqa: E402
from src.data_pipeline.tushare_batch import (  # noqa: E402
    bootstrap_tushare_script,
    fetch_listed_stock_codes,
    get_tushare_pro,
    load_progress_file,
    log_batch_banner,
    run_per_stock_download,
    save_progress_file,
)

logger = bootstrap_tushare_script(
    project_root=PROJECT_ROOT,
    logger_name="daily_basic_downloader",
    log_filename="daily_basic_download.log",
)

DATA_DIR = PROJECT_ROOT / "data"
PROGRESS_FILE = DATA_DIR / "daily_basic_download_progress.json"
START_DATE = "20100101"
END_DATE = datetime.today().strftime("%Y%m%d")
SLEEP_BETWEEN_STOCKS = 0.3
CHECKPOINT_EVERY = 50

_pro = None


def _get_pro():
    global _pro
    if _pro is None:
        _pro = get_tushare_pro(logger)
    return _pro


def load_progress() -> dict:
    return load_progress_file(PROGRESS_FILE, track_empty_retries=True, logger=logger)


def save_progress(progress: dict) -> None:
    save_progress_file(PROGRESS_FILE, progress)


def fetch_stock_list() -> list[str]:
    return fetch_listed_stock_codes(_get_pro(), logger)


def fetch_daily_basic(ts_code: str) -> pd.DataFrame | None:
    pro = _get_pro()
    return pro.daily_basic(
        ts_code=ts_code,
        start_date=START_DATE,
        end_date=END_DATE,
        fields=get_daily_basic_field_string(),
    )


def download_all(progress: dict, stock_codes: list[str]) -> None:
    DAILY_BASIC_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    run_per_stock_download(
        progress=progress,
        progress_file=PROGRESS_FILE,
        stock_codes=stock_codes,
        fetch_frame=fetch_daily_basic,
        persist_frame=lambda ts_code, df: df.to_parquet(
            DAILY_BASIC_STAGING_DIR / f"{ts_code}.parquet",
            index=False,
        ),
        logger=logger,
        checkpoint_every=CHECKPOINT_EVERY,
        sleep_between=SLEEP_BETWEEN_STOCKS,
        empty_retry_limit=2,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Tushare daily_basic for all A-share stocks.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only fetch and print the stock list, do not download daily_basic.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_batch_banner(
        logger,
        title="Pixiu — Tushare daily_basic Batch Downloader",
        output_path=DAILY_BASIC_STAGING_DIR,
        progress_file=PROGRESS_FILE,
    )

    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        logger.error("TUSHARE_TOKEN is not set. Aborting.")
        sys.exit(1)

    progress = load_progress()
    stock_codes = fetch_stock_list()
    if args.list_only:
        logger.info("[--list-only] Stock list fetched. Sample: %s", stock_codes[:5])
        print(f"Total stocks: {len(stock_codes)}")
        return

    download_all(progress, stock_codes)


if __name__ == "__main__":
    main()
