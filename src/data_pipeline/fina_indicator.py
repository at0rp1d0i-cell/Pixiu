from __future__ import annotations

from src.data_pipeline.datasets import FINA_INDICATOR_DATASET

FINA_INDICATOR_STAGING_DIR = FINA_INDICATOR_DATASET.staging_path
FINA_INDICATOR_SOURCE_FIELDS = FINA_INDICATOR_DATASET.required_source_fields
QLIB_FINA_INDICATOR_FIELDS = tuple(
    field.bin_stem for field in FINA_INDICATOR_DATASET.formula_fields
)


def get_fina_indicator_field_string() -> str:
    return ",".join(FINA_INDICATOR_SOURCE_FIELDS)
