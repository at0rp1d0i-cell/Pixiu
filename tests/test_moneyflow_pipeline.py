from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.moneyflow import normalize_moneyflow_frame

pytestmark = pytest.mark.unit


def test_normalize_moneyflow_frame_sorts_dedupes_and_coerces_numeric():
    df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "trade_date": ["20260318", "20260317", "20260318"],
            "buy_sm_vol": ["10", "20", "30"],
            "buy_sm_amount": ["1.1", "2.2", "3.3"],
            "net_mf_amount": ["0.5", "-1.5", "2.5"],
        }
    )

    normalized = normalize_moneyflow_frame(df)

    assert normalized["trade_date"].tolist() == ["20260317", "20260318"]
    assert normalized["buy_sm_vol"].tolist() == [20, 30]
    assert normalized["buy_sm_amount"].tolist() == [2.2, 3.3]
    assert normalized["net_mf_amount"].tolist() == [-1.5, 2.5]


def test_normalize_moneyflow_frame_rejects_missing_identity_columns():
    df = pd.DataFrame({"trade_date": ["20260318"]})

    try:
        normalize_moneyflow_frame(df)
    except ValueError as exc:
        assert "ts_code/trade_date" in str(exc)
    else:
        raise AssertionError("normalize_moneyflow_frame should reject missing ts_code")
