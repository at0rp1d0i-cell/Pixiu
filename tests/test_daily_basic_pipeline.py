from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data_pipeline.daily_basic import (
    DAILY_BASIC_FIELD_MAP,
    QLIB_DAILY_BASIC_FIELDS,
    build_daily_basic_feature_arrays,
    get_daily_basic_field_string,
    normalize_daily_basic_frame,
)

pytestmark = pytest.mark.unit


def test_daily_basic_field_string_and_mapping():
    field_string = get_daily_basic_field_string()
    assert "trade_date" in field_string
    assert "pe_ttm" in field_string
    assert "pb" in field_string
    assert "turnover_rate" in field_string
    assert "circ_mv" in field_string
    assert DAILY_BASIC_FIELD_MAP["circ_mv"] == "float_mv"


def test_normalize_daily_basic_frame_maps_circ_mv_to_float_mv():
    df = pd.DataFrame(
        {
            "trade_date": ["20250317"],
            "pe_ttm": [12.5],
            "pb": [1.8],
            "turnover_rate": [3.2],
            "circ_mv": [123456.0],
        }
    )

    normalized = normalize_daily_basic_frame(df)

    assert "date" in normalized.columns
    assert "float_mv" in normalized.columns
    assert normalized.loc[0, "date"] == "2025-03-17"
    assert normalized.loc[0, "float_mv"] == pytest.approx(123456.0)


def test_build_daily_basic_feature_arrays_aligns_to_calendar():
    calendar = ["2025-03-17", "2025-03-18", "2025-03-19"]
    df = pd.DataFrame(
        {
            "trade_date": ["20250317", "20250319"],
            "pe_ttm": [10.0, 12.0],
            "pb": [1.5, 1.7],
            "turnover_rate": [2.0, 2.5],
            "circ_mv": [100.0, 120.0],
        }
    )

    arrays = build_daily_basic_feature_arrays(df, calendar)

    assert set(arrays) == set(QLIB_DAILY_BASIC_FIELDS)
    np.testing.assert_allclose(arrays["pe_ttm"][[0, 2]], np.array([10.0, 12.0], dtype=np.float32))
    assert np.isnan(arrays["pe_ttm"][1])
    np.testing.assert_allclose(arrays["float_mv"][[0, 2]], np.array([100.0, 120.0], dtype=np.float32))
