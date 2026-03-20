from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.stk_limit import normalize_stk_limit_frame

pytestmark = pytest.mark.unit


def test_normalize_stk_limit_frame_sorts_dedupes_and_coerces_numeric():
    df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "trade_date": ["20260318", "20260317", "20260318"],
            "up_limit": ["12.13", "12.01", "12.23"],
            "down_limit": ["9.93", "9.83", "10.03"],
        }
    )

    normalized = normalize_stk_limit_frame(df)

    assert normalized["trade_date"].tolist() == ["20260317", "20260318"]
    assert normalized["up_limit"].tolist() == [12.01, 12.23]
    assert normalized["down_limit"].tolist() == [9.83, 10.03]


def test_normalize_stk_limit_frame_rejects_missing_identity_columns():
    df = pd.DataFrame({"trade_date": ["20260318"]})

    try:
        normalize_stk_limit_frame(df)
    except ValueError as exc:
        assert "ts_code/trade_date" in str(exc)
    else:
        raise AssertionError("normalize_stk_limit_frame should reject missing ts_code")
