from __future__ import annotations

import pytest

from src.data_pipeline.datasets import (
    DAILY_BASIC_DATASET,
    DATASET_SPECS_BY_NAME,
    FIELD_SPECS_BY_NAME,
    FINA_INDICATOR_DATASET,
    FORMULA_DATASET_SPECS,
    QLIB_PRICE_VOLUME_DATASET,
)

pytestmark = pytest.mark.unit


def test_formula_dataset_registry_contains_three_formula_datasets():
    names = [dataset.name for dataset in FORMULA_DATASET_SPECS]
    assert names == ["qlib_price_volume", "fina_indicator", "daily_basic"]
    assert DATASET_SPECS_BY_NAME["qlib_price_volume"] == QLIB_PRICE_VOLUME_DATASET
    assert DATASET_SPECS_BY_NAME["fina_indicator"] == FINA_INDICATOR_DATASET
    assert DATASET_SPECS_BY_NAME["daily_basic"] == DAILY_BASIC_DATASET


def test_formula_dataset_registry_owns_expected_fields():
    assert FIELD_SPECS_BY_NAME["$roe"].source == "fina_indicator"
    assert FIELD_SPECS_BY_NAME["$pb"].source == "daily_basic"
    assert FIELD_SPECS_BY_NAME["$pe_ttm"].source == "daily_basic"
    assert FIELD_SPECS_BY_NAME["$turnover_rate"].source == "daily_basic"
    assert FIELD_SPECS_BY_NAME["$float_mv"].source == "daily_basic"


def test_daily_basic_registry_preserves_source_to_bin_mapping():
    float_mv = FIELD_SPECS_BY_NAME["$float_mv"]
    assert float_mv.source_field == "circ_mv"
    assert float_mv.bin_stem == "float_mv"
