from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONEYFLOW_HSGT_DIR = PROJECT_ROOT / "data" / "fundamental_staging" / "moneyflow_hsgt"
MONEYFLOW_HSGT_FILE = MONEYFLOW_HSGT_DIR / "moneyflow_hsgt.parquet"
MONEYFLOW_HSGT_START_DATE = "20141117"

MONEYFLOW_HSGT_COLUMNS = [
    "trade_date",
    "ggt_ss",
    "ggt_sz",
    "hgt",
    "sgt",
    "north_money",
    "south_money",
]


def clean_moneyflow_hsgt_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    cleaned = df.copy()
    present = [column for column in MONEYFLOW_HSGT_COLUMNS if column in cleaned.columns]
    cleaned = cleaned[present]
    cleaned["trade_date"] = cleaned["trade_date"].astype(str).str.strip()
    cleaned = cleaned[cleaned["trade_date"].str.match(r"^\d{8}$")]

    for column in MONEYFLOW_HSGT_COLUMNS[1:]:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned = cleaned.drop_duplicates(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return cleaned
