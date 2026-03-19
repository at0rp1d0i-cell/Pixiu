from __future__ import annotations

from pathlib import Path

import pytest

from src.formula.capabilities import (
    APPROVED_OPERATORS,
    FIELD_SPECS_BY_NAME,
    get_runtime_formula_capabilities,
)

pytestmark = pytest.mark.unit


def _touch_bin(features_dir: Path, instrument: str, bin_name: str) -> None:
    instrument_dir = features_dir / instrument
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / bin_name).write_bytes(b"")


def test_runtime_formula_capabilities_expose_fields_by_coverage(tmp_path: Path):
    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _touch_bin(features_dir, instrument, "close.day.bin")
        _touch_bin(features_dir, instrument, "open.day.bin")
        if i < 19:
            _touch_bin(features_dir, instrument, "roe.day.bin")
        if i < 18:
            _touch_bin(features_dir, instrument, "pb.day.bin")

    capabilities = get_runtime_formula_capabilities(
        provider_uri=tmp_path,
        min_coverage_ratio=0.95,
    )

    assert "$close" in capabilities.available_fields
    assert "$open" in capabilities.available_fields
    assert "$roe" in capabilities.available_fields
    assert "$pb" not in capabilities.available_fields
    assert capabilities.total_instruments == 20


def test_runtime_formula_capabilities_use_canonical_operator_manifest(tmp_path: Path):
    capabilities = get_runtime_formula_capabilities(
        provider_uri=tmp_path,
        min_coverage_ratio=0.95,
    )

    assert capabilities.approved_operators == APPROVED_OPERATORS
    assert "Mean" in capabilities.approved_operators
    assert "CSRank" not in capabilities.approved_operators
    assert FIELD_SPECS_BY_NAME["$float_mv"].bin_stem == "float_mv"
