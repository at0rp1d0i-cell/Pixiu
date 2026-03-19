from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAILY_BASIC_STAGING_DIR = PROJECT_ROOT / "data" / "fundamental_staging" / "daily_basic"

DAILY_BASIC_SOURCE_FIELDS = (
    "ts_code",
    "trade_date",
    "turnover_rate",
    "pe_ttm",
    "pb",
    "circ_mv",
)

DAILY_BASIC_FIELD_MAP = {
    "turnover_rate": "turnover_rate",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "circ_mv": "float_mv",
}

QLIB_DAILY_BASIC_FIELDS = tuple(DAILY_BASIC_FIELD_MAP.values())


def get_daily_basic_field_string() -> str:
    return ",".join(DAILY_BASIC_SOURCE_FIELDS)


def ts_code_to_qlib(ts_code: str) -> str:
    if "." not in ts_code:
        return ts_code.lower()
    number, exchange = ts_code.split(".", 1)
    return exchange.lower() + number


def normalize_daily_basic_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "trade_date" not in normalized.columns:
        raise ValueError("daily_basic frame missing trade_date column")

    normalized["trade_date"] = pd.to_datetime(
        normalized["trade_date"],
        format="%Y%m%d",
        errors="coerce",
    )
    normalized = normalized.dropna(subset=["trade_date"]).copy()
    normalized["date"] = normalized["trade_date"].dt.strftime("%Y-%m-%d")
    normalized = normalized.rename(columns=DAILY_BASIC_FIELD_MAP)
    keep_cols = ["date"] + [field for field in QLIB_DAILY_BASIC_FIELDS if field in normalized.columns]
    normalized = normalized[keep_cols].copy()
    normalized = normalized.sort_values("date", kind="stable")
    normalized = normalized.drop_duplicates(subset=["date"], keep="last")
    normalized = normalized.reset_index(drop=True)
    return normalized


def align_daily_basic_to_calendar(
    df: pd.DataFrame,
    calendar: list[str],
) -> pd.DataFrame:
    normalized = normalize_daily_basic_frame(df)
    cal_df = pd.DataFrame({"date": calendar})
    merged = cal_df.merge(normalized, on="date", how="left")
    return merged.set_index("date")


def build_daily_basic_feature_arrays(
    df: pd.DataFrame,
    calendar: list[str],
) -> dict[str, np.ndarray]:
    aligned = align_daily_basic_to_calendar(df, calendar)
    arrays: dict[str, np.ndarray] = {}
    n_days = len(calendar)
    for field in QLIB_DAILY_BASIC_FIELDS:
        if field not in aligned.columns:
            arrays[field] = np.full(n_days, np.nan, dtype=np.float32)
            continue
        arrays[field] = aligned[field].to_numpy(dtype=np.float32, na_value=np.nan)
    return arrays
