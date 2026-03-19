from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONEYFLOW_STAGING_DIR = PROJECT_ROOT / "data" / "fundamental_staging" / "moneyflow"

MONEYFLOW_SOURCE_FIELDS = (
    "ts_code",
    "trade_date",
    "buy_sm_vol",
    "buy_sm_amount",
    "sell_sm_vol",
    "sell_sm_amount",
    "buy_md_vol",
    "buy_md_amount",
    "sell_md_vol",
    "sell_md_amount",
    "buy_lg_vol",
    "buy_lg_amount",
    "sell_lg_vol",
    "sell_lg_amount",
    "buy_elg_vol",
    "buy_elg_amount",
    "sell_elg_vol",
    "sell_elg_amount",
    "net_mf_vol",
    "net_mf_amount",
)


def get_moneyflow_field_string() -> str:
    return ",".join(MONEYFLOW_SOURCE_FIELDS)


def normalize_moneyflow_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    normalized = df.copy()
    present = [column for column in MONEYFLOW_SOURCE_FIELDS if column in normalized.columns]
    normalized = normalized[present]

    if "trade_date" not in normalized.columns or "ts_code" not in normalized.columns:
        raise ValueError("moneyflow frame missing ts_code/trade_date columns")

    normalized["ts_code"] = normalized["ts_code"].astype(str).str.strip()
    normalized["trade_date"] = normalized["trade_date"].astype(str).str.strip()
    normalized = normalized[
        normalized["trade_date"].str.match(r"^\d{8}$") & normalized["ts_code"].str.contains(r"\.")
    ]

    numeric_columns = [column for column in MONEYFLOW_SOURCE_FIELDS if column not in {"ts_code", "trade_date"}]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    normalized = normalized.sort_values(["ts_code", "trade_date"], kind="stable").reset_index(drop=True)
    return normalized
