#!/usr/bin/env python3
"""
scripts/convert_fundamental_to_qlib.py

Convert Tushare fina_indicator parquet files to qlib binary format with
Point-in-Time (PIT) forward-fill to avoid look-ahead bias.

PIT logic:
  Each fina_indicator record has ann_date (announcement date) and end_date
  (report period end). For each trading day t, we take the value from the
  most recent record whose ann_date <= t.  This means a quarterly report
  becomes "visible" only on its announcement date, not its period-end date.

Input:
  data/fundamental_staging/fina_indicator/{ts_code}.parquet

Output:
  data/qlib_bin/features/{ts_code_lower}/{field}.day.bin
  (same directory as price-volume bins)

Usage:
  uv run python scripts/convert_fundamental_to_qlib.py
"""

import struct
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ──────────────────────────────────────────────────────────────────

PROJECT_ROOT   = Path(__file__).resolve().parents[1]
DATA_DIR       = PROJECT_ROOT / "data"
STAGING_DIR    = DATA_DIR / "fundamental_staging" / "fina_indicator"
_qlib_env = os.getenv("QLIB_DATA_DIR")
if _qlib_env:
    QLIB_DIR = Path(_qlib_env) if os.path.isabs(_qlib_env) else PROJECT_ROOT / _qlib_env
else:
    QLIB_DIR = PROJECT_ROOT / "data" / "qlib_bin"
CALENDAR_FILE  = QLIB_DIR / "calendars" / "day.txt"
FEATURES_DIR   = QLIB_DIR / "features"

# Fields to write (parquet column name → bin file stem)
FIELDS = [
    "eps",
    "dt_eps",
    "roe",
    "roe_waa",
    "roe_dt",
    "roa",
    "netprofit_margin",
    "gross_margin",
    "current_ratio",
    "quick_ratio",
    "debt_to_assets",
    "assets_turn",
]

PROGRESS_EVERY = 200  # print progress every N stocks


# ── Code conversion ─────────────────────────────────────────────────────────

def ts_code_to_qlib(ts_code: str) -> str:
    """
    Convert Tushare ts_code to qlib directory name.
    000001.SZ  →  sz000001
    600000.SH  →  sh600000
    """
    if "." not in ts_code:
        return ts_code.lower()
    number, exchange = ts_code.split(".", 1)
    return exchange.lower() + number


# ── Bin writer ───────────────────────────────────────────────────────────────

def _write_bin(path: Path, start_idx: int, values: np.ndarray) -> None:
    """Write a single qlib .day.bin file.

    Format: uint32 start_idx (little-endian) + float32[] values.
    start_idx is the calendar index of the first element in values.
    """
    with open(path, "wb") as f:
        f.write(struct.pack("<I", start_idx))
        values.astype(np.float32).tofile(f)


# ── Calendar ─────────────────────────────────────────────────────────────────

def read_calendar() -> list[str]:
    """Return sorted list of trading days as YYYY-MM-DD strings."""
    return [d.strip() for d in CALENDAR_FILE.read_text().splitlines() if d.strip()]


# ── PIT forward-fill ─────────────────────────────────────────────────────────

def pit_fill(df: pd.DataFrame, calendar: list[str]) -> pd.DataFrame:
    """
    Forward-fill fina_indicator records onto the full trading calendar
    using Point-in-Time semantics.

    Algorithm:
      1. Parse ann_date to YYYY-MM-DD and sort records by ann_date ascending.
      2. For each trading day t in the calendar, find the latest record
         with ann_date <= t (merge_asof on sorted ann_date).
      3. Days before the first announcement get NaN for all fields.

    Returns a DataFrame indexed by calendar date with one row per trading day.
    """
    # Normalise ann_date: YYYYMMDD → YYYY-MM-DD
    df = df.copy()
    df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["ann_date"])
    df["ann_date"] = df["ann_date"].dt.strftime("%Y-%m-%d")

    # Keep only fields we care about (plus ann_date key)
    keep_cols = ["ann_date"] + [c for c in FIELDS if c in df.columns]
    df = df[keep_cols].copy()

    # When multiple records share the same ann_date, keep the most recent
    # end_date (already sorted, or just keep last occurrence per ann_date)
    df = df.sort_values("ann_date", kind="stable")
    df = df.drop_duplicates(subset=["ann_date"], keep="last")
    df = df.reset_index(drop=True)

    # Build a calendar DataFrame to merge into
    cal_df = pd.DataFrame({"date": calendar})

    # merge_asof: for each row in cal_df, find the last row in df
    # where ann_date <= date  (both must be sorted ascending)
    merged = pd.merge_asof(
        cal_df,
        df,
        left_on="date",
        right_on="ann_date",
        direction="backward",
    )
    # merged has one row per calendar day; fields are NaN before first announcement
    merged = merged.set_index("date")
    return merged


# ── Per-stock conversion ──────────────────────────────────────────────────────

def convert_stock(
    parquet_path: Path,
    calendar: list[str],
    cal_index: dict[str, int],
) -> bool:
    """
    Convert one stock's fina_indicator parquet to qlib bins.

    Returns True if any bin was written, False if skipped.
    """
    ts_code  = parquet_path.stem          # e.g. 000001.SZ
    qlib_dir = FEATURES_DIR / ts_code_to_qlib(ts_code)

    # Skip if all target bins already exist
    existing = {b.stem.split(".")[0] for b in qlib_dir.glob("*.day.bin")} if qlib_dir.exists() else set()
    target_fields = [f for f in FIELDS]
    if existing.issuperset(target_fields):
        return False  # all bins present, skip

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"  [WARN] Cannot read {parquet_path.name}: {e}", flush=True)
        return False

    if df.empty or "ann_date" not in df.columns:
        return False

    # PIT forward-fill onto full calendar
    filled = pit_fill(df, calendar)

    # Determine the calendar slice covered by this stock's data
    # We write from the first calendar day to the last calendar day
    # (qlib will handle the NaN prefix naturally via start_idx = 0)
    # But to be consistent with price bins, use the full calendar span.
    start_idx = 0
    n_days    = len(calendar)

    qlib_dir.mkdir(parents=True, exist_ok=True)

    wrote_any = False
    for field in FIELDS:
        bin_path = qlib_dir / f"{field}.day.bin"
        if bin_path.exists():
            continue  # already present, skip individual field

        if field not in filled.columns:
            # Field not in parquet — write full-NaN array so qlib sees it
            arr = np.full(n_days, np.nan, dtype=np.float32)
        else:
            arr = filled[field].to_numpy(dtype=np.float32, na_value=np.nan)
            # Ensure length matches calendar
            if len(arr) != n_days:
                arr2 = np.full(n_days, np.nan, dtype=np.float32)
                arr2[: len(arr)] = arr[: n_days]
                arr = arr2

        _write_bin(bin_path, start_idx, arr)
        wrote_any = True

    return wrote_any


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Guard: staging directory must exist
    if not STAGING_DIR.exists():
        print(
            f"Staging directory not found: {STAGING_DIR}\n"
            "Run the fina_indicator downloader first. Exiting.",
            flush=True,
        )
        sys.exit(0)

    # Guard: calendar must exist
    if not CALENDAR_FILE.exists():
        print(
            f"Calendar file not found: {CALENDAR_FILE}\n"
            "Run scripts/download_qlib_data.py (Phase 1) first. Exiting.",
            flush=True,
        )
        sys.exit(0)

    print(f"Reading calendar from {CALENDAR_FILE} ...", flush=True)
    calendar = read_calendar()
    cal_index = {d: i for i, d in enumerate(calendar)}
    print(f"Calendar: {len(calendar)} days ({calendar[0]} ~ {calendar[-1]})", flush=True)

    parquet_files = sorted(STAGING_DIR.glob("*.parquet"))
    if not parquet_files:
        print(f"No parquet files found in {STAGING_DIR}. Exiting.", flush=True)
        sys.exit(0)

    print(f"Found {len(parquet_files)} parquet files. Starting conversion ...", flush=True)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped   = 0

    for i, path in enumerate(parquet_files, 1):
        wrote = convert_stock(path, calendar, cal_index)
        if wrote:
            converted += 1
        else:
            skipped += 1

        if i % PROGRESS_EVERY == 0:
            print(
                f"  [{i}/{len(parquet_files)}] converted={converted}, skipped={skipped}",
                flush=True,
            )

    print(
        f"\nDone. converted={converted}, skipped={skipped}",
        flush=True,
    )


if __name__ == "__main__":
    main()
