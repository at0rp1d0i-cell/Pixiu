#!/usr/bin/env python3
"""
Download Tushare moneyflow_hsgt history to a single parquet file.

Output:
  data/fundamental_staging/moneyflow_hsgt/moneyflow_hsgt.parquet
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.env import clear_localhost_proxy_env, load_dotenv_if_available
from src.data_pipeline.moneyflow_hsgt import (
    MONEYFLOW_HSGT_COLUMNS,
    MONEYFLOW_HSGT_FILE,
    MONEYFLOW_HSGT_DIR,
    MONEYFLOW_HSGT_START_DATE,
    clean_moneyflow_hsgt_frame,
)

load_dotenv_if_available()
_cleared_proxy_vars = clear_localhost_proxy_env()

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "moneyflow_hsgt_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("moneyflow_hsgt_downloader")
if _cleared_proxy_vars:
    logger.info("Cleared localhost proxy vars for direct Tushare access: %s", ", ".join(_cleared_proxy_vars))

SLEEP_BETWEEN = 0.2


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y%m%d").date()


def _fmt(day: date) -> str:
    return day.strftime("%Y%m%d")


def _month_segments(start: date, end: date) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            month_end = date(cursor.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(cursor.year, cursor.month + 1, 1) - timedelta(days=1)
        seg_end = min(month_end, end)
        segments.append((_fmt(cursor), _fmt(seg_end)))
        cursor = seg_end + timedelta(days=1)
    return segments


def _get_pro():
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set.")
    return ts.pro_api(token)


def _load_existing() -> pd.DataFrame | None:
    if MONEYFLOW_HSGT_FILE.exists():
        existing = pd.read_parquet(MONEYFLOW_HSGT_FILE)
        logger.info("Existing moneyflow_hsgt loaded: %d rows", len(existing))
        return existing
    return None


def _determine_start(existing: pd.DataFrame | None) -> date:
    if existing is not None and not existing.empty:
        max_date = _parse_date(str(existing["trade_date"].max()))
        start = max_date + timedelta(days=1)
        logger.info("Incremental mode: max trade_date=%s, downloading from %s", _fmt(max_date), _fmt(start))
        return start
    logger.info("Full download mode: starting from %s", MONEYFLOW_HSGT_START_DATE)
    return _parse_date(MONEYFLOW_HSGT_START_DATE)


def _fetch_segment(pro, start_str: str, end_str: str) -> pd.DataFrame:
    df = pro.moneyflow_hsgt(start_date=start_str, end_date=end_str)
    time.sleep(SLEEP_BETWEEN)
    if df is None:
        return pd.DataFrame(columns=MONEYFLOW_HSGT_COLUMNS)
    return clean_moneyflow_hsgt_frame(df)


def _download_all(pro, start: date, end: date) -> pd.DataFrame:
    segments = _month_segments(start, end)
    logger.info("Downloading %d monthly segments (%s ~ %s)", len(segments), _fmt(start), _fmt(end))

    frames: list[pd.DataFrame] = []
    for idx, (seg_start, seg_end) in enumerate(segments, 1):
        logger.info("[%d/%d] Fetching %s ~ %s", idx, len(segments), seg_start, seg_end)
        df = _fetch_segment(pro, seg_start, seg_end)
        if not df.empty:
            frames.append(df)
            logger.info("  -> %d rows", len(df))
        else:
            logger.info("  -> 0 rows")

    if not frames:
        return pd.DataFrame(columns=MONEYFLOW_HSGT_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _merge_and_save(existing: pd.DataFrame | None, new_df: pd.DataFrame) -> pd.DataFrame:
    MONEYFLOW_HSGT_DIR.mkdir(parents=True, exist_ok=True)
    new_df = clean_moneyflow_hsgt_frame(new_df)
    if existing is not None and not existing.empty:
        combined = pd.concat([clean_moneyflow_hsgt_frame(existing), new_df], ignore_index=True)
    else:
        combined = new_df

    if combined.empty:
        logger.warning("Combined DataFrame is empty — nothing to save.")
        return combined

    combined = clean_moneyflow_hsgt_frame(combined)
    combined.to_parquet(MONEYFLOW_HSGT_FILE, index=False)
    logger.info("Saved %d rows to %s", len(combined), MONEYFLOW_HSGT_FILE)
    return combined


def main() -> None:
    logger.info("=" * 60)
    logger.info("Pixiu — Tushare moneyflow_hsgt Downloader")
    logger.info("Output: %s", MONEYFLOW_HSGT_FILE)
    logger.info("=" * 60)

    existing = _load_existing()
    start = _determine_start(existing)
    end = date.today()

    if start > end:
        logger.info("moneyflow_hsgt is already up to date.")
        return

    pro = _get_pro()
    new_df = _download_all(pro, start, end)
    merged = _merge_and_save(existing, new_df)
    logger.info("Done. total_rows=%d", len(merged))


if __name__ == "__main__":
    main()
