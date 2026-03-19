from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STK_LIMIT_STAGING_DIR = PROJECT_ROOT / "data" / "fundamental_staging" / "stk_limit"

STK_LIMIT_SOURCE_FIELDS = (
    "ts_code",
    "trade_date",
    "up_limit",
    "down_limit",
)


def get_stk_limit_field_string() -> str:
    return ",".join(STK_LIMIT_SOURCE_FIELDS)


def normalize_stk_limit_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    normalized = df.copy()
    present = [column for column in STK_LIMIT_SOURCE_FIELDS if column in normalized.columns]
    normalized = normalized[present]

    if "trade_date" not in normalized.columns or "ts_code" not in normalized.columns:
        raise ValueError("stk_limit frame missing ts_code/trade_date columns")

    normalized["ts_code"] = normalized["ts_code"].astype(str).str.strip()
    normalized["trade_date"] = normalized["trade_date"].astype(str).str.strip()
    normalized = normalized[
        normalized["trade_date"].str.match(r"^\d{8}$") & normalized["ts_code"].str.contains(r"\.")
    ]

    for column in ("up_limit", "down_limit"):
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    normalized = normalized.sort_values(["ts_code", "trade_date"], kind="stable").reset_index(drop=True)
    return normalized
