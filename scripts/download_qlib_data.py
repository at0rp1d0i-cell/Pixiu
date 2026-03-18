#!/usr/bin/env python3
"""
scripts/download_qlib_data.py

Robust A-share OHLCV downloader: baostock → qlib binary format.

Phases:
  1. expand_calendar  — fetch all trading days from baostock (2010-01-01 to today),
                        merge with existing calendar, re-align existing stocks' start_idx
  2. download_stocks  — download all A-share OHLCV to CSV staging (checkpoint-based)
  3. build_bin        — convert staged CSVs to qlib binary, update instruments/all.txt

Resilience:
  - Progress checkpointed to data/qlib_download_progress.json every 50 stocks
  - On restart, already-downloaded stocks are skipped automatically
  - Stocks that fail all retries are logged to "failed" and skipped on retry
  - Each phase is idempotent; safe to re-run after any interruption

Usage:
  # Full run (background):
  nohup uv run python scripts/download_qlib_data.py > logs/qlib_download.log 2>&1 &

  # Check progress:
  tail -f logs/qlib_download.log

  # Resume after interruption (just re-run):
  uv run python scripts/download_qlib_data.py

使用说明：
  全量下载约 5000 只股票 × 15 年数据，耗时 2-4 小时（受 baostock 限速约束）。
  中断后直接重新运行即可续传，无需额外参数。
"""

import json
import logging
import os
import struct
import time
from datetime import datetime, date
from pathlib import Path

import baostock as bs
import numpy as np
import pandas as pd

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "qlib_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("qlib_downloader")

# ── Config ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data"
QLIB_DIR     = DATA_DIR / "qlib_bin"
STAGING_DIR  = DATA_DIR / "parquet_staging" / "baostock_raw"
PROGRESS_FILE = DATA_DIR / "qlib_download_progress.json"

START_DATE = "2010-01-01"
END_DATE   = datetime.today().strftime("%Y-%m-%d")

# baostock fields for daily K-line (후복권 = post-adjustment)
BS_FIELDS    = "date,code,open,high,low,close,volume,amount,adjustflag"
ADJUST_FLAG  = "2"   # 后复权

RETRY_LIMIT           = 3
SLEEP_BETWEEN_STOCKS  = 0.12   # seconds — stay within baostock rate limit
CHECKPOINT_EVERY      = 50     # save progress every N stocks


# ── Progress helpers ───────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "calendar_expanded": False,
        "done": [],
        "failed": {},
        "bin_built": [],
        "started_at": datetime.now().isoformat(),
    }


def save_progress(progress: dict) -> None:
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


# ── Code conversion ────────────────────────────────────────────────────────────

def bs_to_qlib(code: str) -> str:
    """sh.600000  →  sh600000"""
    return code.replace(".", "").lower()


def qlib_to_bs(code: str) -> str:
    """sh600000  →  sh.600000"""
    return code[:2] + "." + code[2:]


# ── Phase 1: Calendar expansion ────────────────────────────────────────────────

def expand_calendar() -> list[str]:
    """
    Fetch all A-share trading days from baostock (2010-01-01 to today),
    merge with existing calendar, write back, and re-align existing stocks.

    从 baostock 获取 2010 年至今的全部交易日，与现有 calendar 合并后写回，
    并重新对齐现有股票二进制文件的 start_idx。
    """
    logger.info("[Phase 1] Expanding calendar from %s to %s ...", START_DATE, END_DATE)

    rs = bs.query_trade_dates(start_date=START_DATE, end_date=END_DATE)
    trading_days = []
    while rs.error_code == "0" and rs.next():
        row = rs.get_row_data()
        if row[1] == "1":   # is_trading_day
            trading_days.append(row[0])

    if not trading_days:
        raise RuntimeError("baostock returned no trading days — check connection")

    calendar_path = QLIB_DIR / "calendars" / "day.txt"
    existing_days: list[str] = []
    if calendar_path.exists():
        existing_days = [d.strip() for d in calendar_path.read_text().splitlines() if d.strip()]

    merged = sorted(set(trading_days) | set(existing_days))
    logger.info("[Phase 1] Calendar: %d days (%s ~ %s)", len(merged), merged[0], merged[-1])

    # Map old calendar index → new calendar index for existing stocks
    old_index = {d: i for i, d in enumerate(existing_days)}
    new_index = {d: i for i, d in enumerate(merged)}
    # Offset = new_index[first_day] - old_index[first_day]
    if existing_days:
        offset = new_index[existing_days[0]] - old_index[existing_days[0]]
        logger.info("[Phase 1] start_idx offset for existing stocks: +%d", offset)
        if offset > 0:
            _realign_existing_stocks(offset)

    # Write new calendar
    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    calendar_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
    logger.info("[Phase 1] Calendar written: %s", calendar_path)

    return merged


def _realign_existing_stocks(offset: int) -> None:
    """
    Add `offset` to start_idx of every existing .day.bin file.
    必须在扩展 calendar 前调用，确保现有股票数据在新 calendar 中的偏移正确。
    """
    features_dir = QLIB_DIR / "features"
    if not features_dir.exists():
        return
    stock_dirs = [d for d in features_dir.iterdir() if d.is_dir()]
    logger.info("[Phase 1] Re-aligning %d existing stocks (offset +%d)...", len(stock_dirs), offset)
    for stock_dir in stock_dirs:
        for bin_file in stock_dir.glob("*.day.bin"):
            try:
                with open(bin_file, "r+b") as f:
                    old_start = struct.unpack("<I", f.read(4))[0]
                    new_start = old_start + offset
                    f.seek(0)
                    f.write(struct.pack("<I", new_start))
            except Exception as e:
                logger.warning("[Phase 1] Failed to realign %s: %s", bin_file, e)
    logger.info("[Phase 1] Re-alignment done.")


# ── Phase 2: Download stocks ───────────────────────────────────────────────────

def fetch_all_stock_codes() -> list[str]:
    """Return all baostock A-share codes (sh.xxxxxx / sz.xxxxxx)."""
    rs = bs.query_stock_basic()
    codes = []
    while rs.error_code == "0" and rs.next():
        row = rs.get_row_data()
        if row[4] == "1":  # type=1: A股，过滤掉指数/基金等
            codes.append(row[0])
    logger.info("[Phase 2] Total A-share stocks: %d", len(codes))
    return codes


def fetch_single_stock(code: str) -> pd.DataFrame | None:
    """
    Download daily OHLCV for one stock; returns None on permanent failure.
    单只股票日线下载，返回 None 表示全部重试失败。
    """
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            rs = bs.query_history_k_data_plus(
                code, BS_FIELDS,
                start_date=START_DATE,
                end_date=END_DATE,
                frequency="d",
                adjustflag=ADJUST_FLAG,
            )
            if rs.error_code != "0":
                logger.warning("[%s] baostock error %s (attempt %d)", code, rs.error_msg, attempt)
                time.sleep(1.5)
                continue
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return pd.DataFrame(columns=rs.fields)   # valid empty (new/suspended stock)
            return pd.DataFrame(rows, columns=rs.fields)
        except Exception as e:
            logger.warning("[%s] exception (attempt %d): %s", code, attempt, e)
            time.sleep(2.0)
    return None


def download_stocks(progress: dict) -> None:
    """
    Download all A-share stocks to CSV staging; checkpoint-based resumption.
    全量下载，每 50 只存一次进度，中断后可续传。
    """
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    done_set      = set(progress["done"])
    failed_counts = progress.get("failed", {})

    all_codes = fetch_all_stock_codes()
    pending = [
        c for c in all_codes
        if bs_to_qlib(c) not in done_set
        and failed_counts.get(bs_to_qlib(c), 0) < RETRY_LIMIT
    ]
    logger.info("[Phase 2] Pending: %d / %d stocks", len(pending), len(all_codes))

    for i, code in enumerate(pending, 1):
        qlib_code = bs_to_qlib(code)
        logger.info("[Phase 2] [%d/%d] %s ...", i, len(pending), code)

        df = fetch_single_stock(code)

        if df is None:
            failed_counts[qlib_code] = failed_counts.get(qlib_code, 0) + 1
            progress["failed"] = failed_counts
            logger.error("[Phase 2] SKIP %s — exhausted retries", code)
        else:
            if not df.empty:
                csv_path = STAGING_DIR / f"{qlib_code}.csv"
                df.to_csv(csv_path, index=False)
            done_set.add(qlib_code)
            progress["done"] = list(done_set)

        if i % CHECKPOINT_EVERY == 0:
            save_progress(progress)
            logger.info("[Phase 2] Checkpoint: %d done, %d failed", len(done_set), len(failed_counts))

        time.sleep(SLEEP_BETWEEN_STOCKS)

    save_progress(progress)
    logger.info(
        "[Phase 2] Download complete. Done: %d, Failed: %d",
        len(done_set), len(failed_counts),
    )


# ── Phase 3: Build qlib binary ─────────────────────────────────────────────────

def _read_calendar() -> list[str]:
    path = QLIB_DIR / "calendars" / "day.txt"
    return [d.strip() for d in path.read_text().splitlines() if d.strip()]


def _write_bin(path: Path, start_idx: int, values: np.ndarray) -> None:
    """Write a single qlib .day.bin file (uint32 start_idx + float32[])."""
    with open(path, "wb") as f:
        f.write(struct.pack("<I", start_idx))
        values.astype(np.float32).tofile(f)


def build_bin(progress: dict) -> None:
    """
    Convert all staged CSVs to qlib binary; update instruments/all.txt.
    将 CSV 转换为 qlib 二进制格式，更新 instruments 列表。
    """
    calendar = _read_calendar()
    cal_index = {d: i for i, d in enumerate(calendar)}
    logger.info("[Phase 3] Calendar has %d days (%s ~ %s)", len(calendar), calendar[0], calendar[-1])

    csv_files = sorted(STAGING_DIR.glob("*.csv"))
    already_built = set(progress.get("bin_built", []))
    pending = [f for f in csv_files if f.stem not in already_built]
    logger.info("[Phase 3] CSVs to convert: %d (already built: %d)", len(pending), len(already_built))

    instruments: dict[str, tuple[str, str]] = _load_instruments()

    for i, csv_path in enumerate(pending, 1):
        qlib_code = csv_path.stem        # e.g. sh600000
        logger.info("[Phase 3] [%d/%d] Converting %s ...", i, len(pending), qlib_code)

        try:
            df = pd.read_csv(csv_path)
            if df.empty or "date" not in df.columns:
                logger.warning("[Phase 3] Empty or malformed CSV: %s", csv_path.name)
                already_built.add(qlib_code)
                continue

            df = df[df["date"].notna()].copy()
            df["date"] = df["date"].astype(str)
            df = df.sort_values("date").reset_index(drop=True)

            # Filter to only dates in our calendar
            df = df[df["date"].isin(cal_index)].copy()
            if df.empty:
                logger.warning("[Phase 3] No calendar-matching dates for %s", qlib_code)
                already_built.add(qlib_code)
                continue

            first_date = df["date"].iloc[0]
            last_date  = df["date"].iloc[-1]
            start_idx  = cal_index[first_date]

            # Build a full float32 array aligned to calendar
            n_days = cal_index[last_date] - start_idx + 1
            stock_dir = QLIB_DIR / "features" / qlib_code
            stock_dir.mkdir(parents=True, exist_ok=True)

            date_to_row = dict(zip(df["date"], df.index))

            for col in ["open", "high", "low", "close", "volume", "amount"]:
                if col not in df.columns:
                    continue
                arr = np.full(n_days, np.nan, dtype=np.float32)
                for day_idx in range(n_days):
                    day = calendar[start_idx + day_idx]
                    if day in date_to_row:
                        val = df[col].iloc[date_to_row[day]]
                        try:
                            arr[day_idx] = float(val)
                        except (ValueError, TypeError):
                            pass
                _write_bin(stock_dir / f"{col}.day.bin", start_idx, arr)

            # factor (复权因子) — set to 1.0 placeholder if not present
            factor_path = stock_dir / "factor.day.bin"
            if not factor_path.exists():
                _write_bin(factor_path, start_idx, np.ones(n_days, dtype=np.float32))

            # Update instruments
            upper = qlib_code.upper()
            instruments[upper] = (first_date, last_date)

            already_built.add(qlib_code)

            if i % CHECKPOINT_EVERY == 0:
                progress["bin_built"] = list(already_built)
                _write_instruments(instruments)
                save_progress(progress)
                logger.info("[Phase 3] Checkpoint at %d built", len(already_built))

        except Exception as e:
            logger.error("[Phase 3] Failed to convert %s: %s", qlib_code, e)

    progress["bin_built"] = list(already_built)
    _write_instruments(instruments)
    save_progress(progress)
    logger.info("[Phase 3] Build complete. %d stocks converted.", len(already_built))


def _load_instruments() -> dict[str, tuple[str, str]]:
    path = QLIB_DIR / "instruments" / "all.txt"
    result: dict[str, tuple[str, str]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                result[parts[0]] = (parts[1], parts[2])
    return result


def _write_instruments(instruments: dict[str, tuple[str, str]]) -> None:
    path = QLIB_DIR / "instruments" / "all.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{code}\t{start}\t{end}" for code, (start, end) in sorted(instruments.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("[Instruments] Written: %d stocks → %s", len(instruments), path)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 60)
    logger.info("Qlib A-Share Data Downloader")
    logger.info("Range: %s ~ %s", START_DATE, END_DATE)
    logger.info("=" * 60)

    progress = load_progress()

    # Connect baostock
    lg = bs.login()
    if lg.error_code != "0":
        logger.error("baostock login failed: %s", lg.error_msg)
        return
    logger.info("baostock login OK (version: %s)", lg.version)

    try:
        # Phase 1: Calendar
        if not progress.get("calendar_expanded"):
            expand_calendar()
            progress["calendar_expanded"] = True
            save_progress(progress)
        else:
            logger.info("[Phase 1] Calendar already expanded, skipping.")

        # Phase 2: Download
        download_stocks(progress)

        # Phase 3: Build binary
        build_bin(progress)

    except KeyboardInterrupt:
        logger.info("Interrupted by user — progress saved, safe to resume.")
        save_progress(progress)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        save_progress(progress)
    finally:
        bs.logout()
        logger.info("baostock logout. Done.")


if __name__ == "__main__":
    main()
