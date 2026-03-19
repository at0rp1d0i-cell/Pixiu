#!/usr/bin/env python3
"""
scripts/download_fundamental_data.py

Tushare fina_indicator batch downloader for A-share fundamental data.

Phases:
  1. Fetch full stock list via pro.stock_basic(list_status="L")
  2. Download historical fina_indicator for each stock, store as parquet

Resilience:
  - Progress checkpointed to data/fundamental_download_progress.json every 50 stocks
  - On restart, already-downloaded stocks (in "done" list) are skipped automatically
  - Failed stocks are recorded with error messages in "failed" dict
  - Safe to re-run after any interruption

Output layout (consumed by Codex 2):
  data/fundamental_staging/fina_indicator/{ts_code}.parquet
  data/fundamental_download_progress.json

Usage:
  # Full run (background):
  nohup uv run python scripts/download_fundamental_data.py > logs/fundamental_download.log 2>&1 &

  # Check progress:
  tail -f logs/fundamental_download.log

  # Resume after interruption (just re-run):
  uv run python scripts/download_fundamental_data.py

  # Dry-run: only fetch stock list, no downloads:
  uv run python scripts/download_fundamental_data.py --list-only

环境变量：
  TUSHARE_TOKEN  — Tushare Pro token（必须设置）
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline.tushare_batch import (  # noqa: E402
    bootstrap_tushare_script,
    fetch_listed_stock_codes,
    get_tushare_pro,
    load_progress_file,
    log_batch_banner,
    run_per_stock_download,
    save_progress_file,
)

# ── Logging ────────────────────────────────────────────────────────────────────

logger = bootstrap_tushare_script(
    project_root=PROJECT_ROOT,
    logger_name="fundamental_downloader",
    log_filename="fundamental_download.log",
)

# ── Config ─────────────────────────────────────────────────────────────────────

DATA_DIR       = PROJECT_ROOT / "data"
STAGING_DIR    = DATA_DIR / "fundamental_staging" / "fina_indicator"
PROGRESS_FILE  = DATA_DIR / "fundamental_download_progress.json"

FINA_FIELDS = (
    "ts_code,ann_date,end_date,eps,dt_eps,roe,roe_waa,roe_dt,roa,"
    "netprofit_margin,gross_margin,current_ratio,quick_ratio,"
    "debt_to_assets,assets_turn"
)

SLEEP_BETWEEN_STOCKS = 0.3   # seconds — ~200 calls/min, conservative
CHECKPOINT_EVERY     = 50    # save progress every N stocks

# ── Tushare Pro init ────────────────────────────────────────────────────────────

_pro = None


def _get_pro():
    """Lazy-init Tushare Pro API instance (mirrors tushare_server.py pattern)."""
    global _pro
    if _pro is None:
        _pro = get_tushare_pro(logger)
    return _pro


# ── Progress helpers ───────────────────────────────────────────────────────────

def load_progress() -> dict:
    return load_progress_file(PROGRESS_FILE, track_empty_retries=False, logger=logger)


def save_progress(progress: dict) -> None:
    save_progress_file(PROGRESS_FILE, progress)


# ── Phase 1: Stock list ────────────────────────────────────────────────────────

def fetch_stock_list() -> list[str]:
    """Return all listed A-share ts_codes via pro.stock_basic."""
    return fetch_listed_stock_codes(_get_pro(), logger)


# ── Phase 2: Download fina_indicator ──────────────────────────────────────────

def fetch_fina_indicator(ts_code: str) -> pd.DataFrame | None:
    """
    Download full historical fina_indicator for one stock.
    Returns None on failure (error message logged by caller).
    """
    try:
        pro = _get_pro()
        df = pro.fina_indicator(ts_code=ts_code, fields=FINA_FIELDS)
        return df
    except Exception as e:
        raise RuntimeError(str(e)) from e


def download_all(progress: dict, stock_codes: list[str]) -> None:
    """
    Phase 2: iterate stock_codes, skip done, download and save parquet.
    Checkpoints every CHECKPOINT_EVERY stocks.
    """
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    run_per_stock_download(
        progress=progress,
        progress_file=PROGRESS_FILE,
        stock_codes=stock_codes,
        fetch_frame=fetch_fina_indicator,
        persist_frame=lambda ts_code, df: df.to_parquet(
            STAGING_DIR / f"{ts_code}.parquet",
            index=False,
        ),
        logger=logger,
        checkpoint_every=CHECKPOINT_EVERY,
        sleep_between=SLEEP_BETWEEN_STOCKS,
        empty_retry_limit=None,
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Tushare fina_indicator for all A-share stocks.\n"
            "Reads TUSHARE_TOKEN from environment. Supports resume on interruption."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python scripts/download_fundamental_data.py\n"
            "  uv run python scripts/download_fundamental_data.py --list-only\n"
            "  nohup uv run python scripts/download_fundamental_data.py "
            "> logs/fundamental_download.log 2>&1 &"
        ),
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only fetch and print the stock list, do not download fina_indicator.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_batch_banner(
        logger,
        title="Pixiu — Tushare fina_indicator Batch Downloader",
        output_path=STAGING_DIR,
        progress_file=PROGRESS_FILE,
    )

    # Validate token early
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        logger.error("TUSHARE_TOKEN is not set. Aborting.")
        sys.exit(1)

    progress = load_progress()

    try:
        # Phase 1: stock list
        stock_codes = fetch_stock_list()

        if args.list_only:
            logger.info("[--list-only] Stock list fetched. Sample: %s", stock_codes[:5])
            print(f"Total stocks: {len(stock_codes)}")
            return

        # Phase 2: download fina_indicator
        download_all(progress, stock_codes)

    except KeyboardInterrupt:
        logger.info("Interrupted by user — progress saved, safe to resume.")
        save_progress(progress)
        sys.exit(0)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        save_progress(progress)
        sys.exit(1)

    # Summary
    done_count    = len(progress.get("done", []))
    failed_count  = len(progress.get("failed", {}))
    total         = len(stock_codes)
    skipped_count = total - done_count - failed_count

    logger.info("=" * 60)
    logger.info("Download complete.")
    logger.info("  Total stocks : %d", total)
    logger.info("  Done         : %d", done_count)
    logger.info("  Failed       : %d", failed_count)
    logger.info("  Skipped      : %d (already done in prior run)", skipped_count if skipped_count >= 0 else 0)
    logger.info("  Parquet dir  : %s", STAGING_DIR)
    logger.info("  Progress file: %s", PROGRESS_FILE)
    logger.info("=" * 60)

    if failed_count > 0:
        logger.warning("Failed stocks (re-run to retry):")
        for code, msg in list(progress["failed"].items())[:20]:
            logger.warning("  %s: %s", code, msg)
        if failed_count > 20:
            logger.warning("  ... and %d more. See progress file for full list.", failed_count - 20)


if __name__ == "__main__":
    main()
