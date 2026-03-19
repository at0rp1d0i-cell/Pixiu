#!/usr/bin/env python3
"""
scripts/download_margin_history.py

Tushare 融资融券历史数据批量下载脚本。

数据源：pro.margin API（按日期查询，每次最多返回 200 条）
输出：data/fundamental_staging/margin_history/margin_history.parquet

字段：
  trade_date   — 交易日期 (YYYYMMDD)
  exchange_id  — 交易所（SSE / SZSE）
  rzye         — 融资余额（元）
  rqye         — 融券余额（元）
  rzrqye       — 融资融券余额（元）
  rzmre        — 融资买入额（元）
  rqyl         — 融券余量（股）

增量逻辑：
  - 若 parquet 文件已存在，读取 max(trade_date)，从 max+1 日起下载
  - 若文件不存在，从 20100101 全量下载

分段下载：
  - 按月分段（每次 start_date/end_date 覆盖一个自然月）
  - 请求间隔 0.2 秒，规避 Tushare 限速

Usage:
  TUSHARE_TOKEN=<your_token> uv run python scripts/download_margin_history.py
"""

import logging
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.env import clear_localhost_proxy_env, load_dotenv_if_available

load_dotenv_if_available()
_cleared_proxy_vars = clear_localhost_proxy_env()

# ── Logging ─────────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "margin_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("margin_downloader")
if _cleared_proxy_vars:
    logger.info("Cleared localhost proxy vars for direct Tushare access: %s", ", ".join(_cleared_proxy_vars))

# ── Config ───────────────────────────────────────────────────────────────────────

OUTPUT_DIR   = PROJECT_ROOT / "data" / "fundamental_staging" / "margin_history"
OUTPUT_FILE  = OUTPUT_DIR / "margin_history.parquet"

FULL_START_DATE = "20100101"   # 融资融券制度正式推行
SLEEP_BETWEEN   = 0.2          # seconds between API calls

MARGIN_COLUMNS = [
    "trade_date",
    "exchange_id",
    "rzye",
    "rqye",
    "rzrqye",
    "rzmre",
    "rqyl",
]


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> date:
    """Parse YYYYMMDD string to date object."""
    return datetime.strptime(date_str, "%Y%m%d").date()


def _fmt(d: date) -> str:
    """Format date to YYYYMMDD string."""
    return d.strftime("%Y%m%d")


def _month_segments(start: date, end: date) -> list[tuple[str, str]]:
    """
    Split [start, end] into monthly segments.
    Each segment is (segment_start_YYYYMMDD, segment_end_YYYYMMDD).

    Example: 2023-11-15 ~ 2024-01-20 produces:
      [('20231115', '20231130'), ('20240101', '20240131'), ('20240101', '20240120')]
    Actually produces non-overlapping month boundaries:
      [('20231115', '20231130'), ('20240101', '20240131'), ('20240101', '20240120')]
    """
    segments = []
    cursor = start
    while cursor <= end:
        # Last day of the cursor's month
        if cursor.month == 12:
            month_end = date(cursor.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(cursor.year, cursor.month + 1, 1) - timedelta(days=1)

        seg_end = min(month_end, end)
        segments.append((_fmt(cursor), _fmt(seg_end)))

        # Advance to first day of next month
        cursor = seg_end + timedelta(days=1)

    return segments


def _load_existing() -> pd.DataFrame | None:
    """Load existing parquet if present; return None if not."""
    if OUTPUT_FILE.exists():
        df = pd.read_parquet(OUTPUT_FILE)
        logger.info("Existing file loaded: %d rows", len(df))
        return df
    return None


def _determine_start(existing: pd.DataFrame | None) -> date:
    """
    Return the start date for incremental download.
    If existing data present, start from max(trade_date) + 1 day.
    Otherwise start from FULL_START_DATE.
    """
    if existing is not None and not existing.empty:
        max_date_str = existing["trade_date"].max()
        max_date = _parse_date(str(max_date_str))
        start = max_date + timedelta(days=1)
        logger.info("Incremental mode: max existing trade_date=%s, downloading from %s", _fmt(max_date), _fmt(start))
        return start

    logger.info("Full download mode: starting from %s", FULL_START_DATE)
    return _parse_date(FULL_START_DATE)


# ── Download ─────────────────────────────────────────────────────────────────────

def fetch_segment(pro, start_str: str, end_str: str) -> pd.DataFrame:
    """
    Fetch margin data for one date range.
    Queries both SSE and SZSE to ensure complete coverage.
    Returns concatenated DataFrame (may be empty if no data).
    """
    frames = []
    for exchange in ("SSE", "SZSE"):
        try:
            df = pro.margin(
                start_date=start_str,
                end_date=end_str,
                exchange_id=exchange,
            )
            if df is not None and not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning("Error fetching %s [%s~%s]: %s", exchange, start_str, end_str, e)
        time.sleep(SLEEP_BETWEEN)

    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=MARGIN_COLUMNS)


def download_all(pro, start: date, end: date) -> pd.DataFrame:
    """
    Download all margin data from start to end in monthly segments.
    Returns a cleaned, sorted DataFrame.
    """
    segments = _month_segments(start, end)
    logger.info("Downloading %d monthly segments (%s ~ %s)", len(segments), _fmt(start), _fmt(end))

    all_frames = []
    for i, (seg_start, seg_end) in enumerate(segments, 1):
        logger.info("[%d/%d] Fetching %s ~ %s ...", i, len(segments), seg_start, seg_end)
        df = fetch_segment(pro, seg_start, seg_end)
        if not df.empty:
            all_frames.append(df)
            logger.info("  -> %d rows", len(df))
        else:
            logger.info("  -> 0 rows (no trading data or holiday period)")

    if not all_frames:
        logger.info("No new data fetched.")
        return pd.DataFrame(columns=MARGIN_COLUMNS)

    combined = pd.concat(all_frames, ignore_index=True)
    return combined


# ── Merge & Save ─────────────────────────────────────────────────────────────────

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize types: trade_date as str YYYYMMDD, numeric columns as float64.
    Drop rows missing trade_date. Deduplicate on (trade_date, exchange_id).
    """
    if df.empty:
        return df

    df = df.copy()

    # Retain only known columns that are present
    present = [c for c in MARGIN_COLUMNS if c in df.columns]
    df = df[present]

    # trade_date: coerce to string, strip whitespace
    df["trade_date"] = df["trade_date"].astype(str).str.strip()
    df = df[df["trade_date"].str.match(r"^\d{8}$")]

    # Numeric columns
    for col in ["rzye", "rqye", "rzrqye", "rzmre", "rqyl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def merge_and_save(existing: pd.DataFrame | None, new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge existing and new data, deduplicate, sort, and save to parquet.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    new_df = _clean(new_df)

    if existing is not None and not existing.empty:
        existing = _clean(existing)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    if combined.empty:
        logger.warning("Combined DataFrame is empty — nothing to save.")
        return combined

    # Deduplicate on (trade_date, exchange_id) if both columns present
    dedup_keys = [c for c in ["trade_date", "exchange_id"] if c in combined.columns]
    combined = combined.drop_duplicates(subset=dedup_keys)

    # Sort by trade_date (and exchange_id for determinism)
    sort_keys = [c for c in ["trade_date", "exchange_id"] if c in combined.columns]
    combined = combined.sort_values(sort_keys).reset_index(drop=True)

    combined.to_parquet(OUTPUT_FILE, index=False)
    logger.info("Saved to %s", OUTPUT_FILE)

    return combined


# ── Entry Point ───────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        logger.error("TUSHARE_TOKEN environment variable is not set or empty.")
        sys.exit(1)

    # Import here so missing package gives a clear error message
    try:
        import tushare as ts
    except ImportError:
        logger.error("tushare is not installed. Run: uv add tushare")
        sys.exit(1)

    ts.set_token(token)
    pro = ts.pro_api()
    logger.info("Tushare pro API initialised.")

    today = date.today()

    # Load existing data and determine incremental start date
    existing = _load_existing()
    start = _determine_start(existing)

    if start > today:
        logger.info("Data is already up to date (start=%s > today=%s). Nothing to download.", _fmt(start), _fmt(today))
    else:
        new_df = download_all(pro, start, today)
        existing = merge_and_save(existing, new_df)

    # Final summary
    if existing is not None and not existing.empty:
        total_rows  = len(existing)
        date_min    = existing["trade_date"].min()
        date_max    = existing["trade_date"].max()
        logger.info("=" * 50)
        logger.info("total_rows=%d, date_range=%s~%s", total_rows, date_min, date_max)
        print(f"total_rows={total_rows}, date_range={date_min}~{date_max}")
    else:
        logger.info("No data available.")
        print("total_rows=0, date_range=N/A")


if __name__ == "__main__":
    main()
