#!/usr/bin/env python3
"""
Download Tushare daily_basic for all listed A-share stocks.

Output:
  data/fundamental_staging/daily_basic/{ts_code}.parquet
  data/daily_basic_download_progress.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import tushare as ts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.env import load_dotenv_if_available
from src.data_pipeline.daily_basic import DAILY_BASIC_STAGING_DIR, get_daily_basic_field_string

load_dotenv_if_available()

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "daily_basic_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("daily_basic_downloader")

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
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError(
                "TUSHARE_TOKEN environment variable is not set. "
                "Export it before running: export TUSHARE_TOKEN=<your_token>"
            )
        _pro = ts.pro_api(token)
        logger.info("Tushare Pro API initialized.")
    return _pro


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "done": [],
        "failed": {},
        "started_at": datetime.now().isoformat(),
    }


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2, ensure_ascii=False)


def fetch_stock_list() -> list[str]:
    pro = _get_pro()
    df = pro.stock_basic(list_status="L", fields="ts_code")
    if df is None or df.empty:
        raise RuntimeError("pro.stock_basic returned empty result — check token/connection")
    codes = df["ts_code"].tolist()
    logger.info("[Phase 1] Total listed stocks: %d", len(codes))
    return codes


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
    done_set = set(progress["done"])
    failed_dict: dict[str, str] = progress.get("failed", {})

    pending = [code for code in stock_codes if code not in done_set]
    logger.info(
        "[Phase 2] Pending: %d / %d (skipped %d already done)",
        len(pending),
        len(stock_codes),
        len(stock_codes) - len(pending),
    )

    for i, ts_code in enumerate(pending, 1):
        try:
            df = fetch_daily_basic(ts_code)
            if df is not None and not df.empty:
                out_path = DAILY_BASIC_STAGING_DIR / f"{ts_code}.parquet"
                df.to_parquet(out_path, index=False)
            else:
                logger.warning("[Phase 2] [%d/%d] %s — empty result, marking done", i, len(pending), ts_code)

            done_set.add(ts_code)
            progress["done"] = list(done_set)
            failed_dict.pop(ts_code, None)
        except Exception as exc:
            failed_dict[ts_code] = str(exc)
            progress["failed"] = failed_dict
            logger.error("[Phase 2] [%d/%d] FAILED %s: %s", i, len(pending), ts_code, exc)

        if i % CHECKPOINT_EVERY == 0:
            progress["failed"] = failed_dict
            save_progress(progress)
            logger.info(
                "[Phase 2] Checkpoint %d/%d — done: %d, failed: %d",
                i,
                len(pending),
                len(done_set),
                len(failed_dict),
            )

        time.sleep(SLEEP_BETWEEN_STOCKS)

    progress["failed"] = failed_dict
    save_progress(progress)


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
    logger.info("=" * 60)
    logger.info("Pixiu — Tushare daily_basic Batch Downloader")
    logger.info("Output: %s", DAILY_BASIC_STAGING_DIR)
    logger.info("Progress: %s", PROGRESS_FILE)
    logger.info("=" * 60)

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
