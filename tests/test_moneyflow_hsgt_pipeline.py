from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.moneyflow_hsgt import clean_moneyflow_hsgt_frame

pytestmark = pytest.mark.unit


def test_clean_moneyflow_hsgt_frame_normalizes_types_and_sorts():
    df = pd.DataFrame(
        {
            "trade_date": ["20240103", "20240102", "20240102"],
            "north_money": ["12.5", "10.0", "10.0"],
            "south_money": ["-5.0", "-3.0", "-3.0"],
        }
    )

    cleaned = clean_moneyflow_hsgt_frame(df)

    assert cleaned["trade_date"].tolist() == ["20240102", "20240103"]
    assert cleaned.loc[0, "north_money"] == pytest.approx(10.0)
    assert cleaned.loc[1, "south_money"] == pytest.approx(-5.0)
