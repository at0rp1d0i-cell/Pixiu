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
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import tushare as ts

from src.core.env import load_dotenv_if_available

# ── Logging ────────────────────────────────────────────────────────────────────

load_dotenv_if_available()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "fundamental_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fundamental_downloader")

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
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError(
                "TUSHARE_TOKEN environment variable is not set. "
                "Export it before running: export TUSHARE_TOKEN=<your_token>"
            )
        _pro = ts.pro_api(token)
        logger.info("Tushare Pro API initialized.")
    return _pro


# ── Progress helpers ───────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(
            "Loaded progress: %d done, %d failed",
            len(data.get("done", [])),
            len(data.get("failed", {})),
        )
        return data
    return {
        "done": [],
        "failed": {},
        "started_at": datetime.now().isoformat(),
    }


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


# ── Phase 1: Stock list ────────────────────────────────────────────────────────

def fetch_stock_list() -> list[str]:
    """Return all listed A-share ts_codes via pro.stock_basic."""
    pro = _get_pro()
    df = pro.stock_basic(list_status="L", fields="ts_code")
    if df is None or df.empty:
        raise RuntimeError("pro.stock_basic returned empty result — check token/connection")
    codes = df["ts_code"].tolist()
    logger.info("[Phase 1] Total listed stocks: %d", len(codes))
    return codes


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

    done_set = set(progress["done"])
    failed_dict: dict[str, str] = progress.get("failed", {})

    pending = [c for c in stock_codes if c not in done_set]
    skipped = len(stock_codes) - len(pending)
    logger.info(
        "[Phase 2] Pending: %d / %d  (skipped %d already done)",
        len(pending), len(stock_codes), skipped,
    )

    for i, ts_code in enumerate(pending, 1):
        try:
            df = fetch_fina_indicator(ts_code)

            if df is not None and not df.empty:
                out_path = STAGING_DIR / f"{ts_code}.parquet"
                df.to_parquet(out_path, index=False)
            else:
                # Empty result is still a valid "done" — stock may have no filings yet
                logger.warning("[Phase 2] [%d/%d] %s — empty result, marking done", i, len(pending), ts_code)

            done_set.add(ts_code)
            progress["done"] = list(done_set)
            # Remove from failed if it previously failed and now succeeded
            failed_dict.pop(ts_code, None)

        except Exception as e:
            err_msg = str(e)
            failed_dict[ts_code] = err_msg
            progress["failed"] = failed_dict
            logger.error("[Phase 2] [%d/%d] FAILED %s: %s", i, len(pending), ts_code, err_msg)

        if i % CHECKPOINT_EVERY == 0:
            progress["failed"] = failed_dict
            save_progress(progress)
            logger.info(
                "[Phase 2] Checkpoint %d/%d — done: %d, failed: %d",
                i, len(pending), len(done_set), len(failed_dict),
            )

        time.sleep(SLEEP_BETWEEN_STOCKS)

    progress["failed"] = failed_dict
    save_progress(progress)


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

    logger.info("=" * 60)
    logger.info("Pixiu — Tushare fina_indicator Batch Downloader")
    logger.info("Output: %s", STAGING_DIR)
    logger.info("Progress: %s", PROGRESS_FILE)
    logger.info("=" * 60)

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
