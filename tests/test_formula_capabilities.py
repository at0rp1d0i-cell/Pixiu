from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from src.formula.capabilities import (
    APPROVED_OPERATORS,
    FIELD_SPECS_BY_NAME,
    OPERATOR_SPECS_BY_NAME,
    format_available_operators_for_prompt,
    get_runtime_formula_capabilities,
)

pytestmark = pytest.mark.unit


def _touch_bin(features_dir: Path, instrument: str, bin_name: str) -> None:
    instrument_dir = features_dir / instrument
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / bin_name).write_bytes(b"")


def _write_day_bin(features_dir: Path, instrument: str, bin_name: str, values: list[float]) -> None:
    instrument_dir = features_dir / instrument
    instrument_dir.mkdir(parents=True, exist_ok=True)
    with (instrument_dir / bin_name).open("wb") as handle:
        handle.write(struct.pack("<I", 0))
        handle.write(np.asarray(values, dtype=np.float32).astype("<f4").tobytes())


def test_runtime_formula_capabilities_expose_fields_by_coverage(tmp_path: Path):
    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "open.day.bin", [1.0])
        if i < 19:
            _write_day_bin(features_dir, instrument, "roe.day.bin", [1.0])
        if i < 18:
            _write_day_bin(features_dir, instrument, "pb.day.bin", [1.0])

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


def test_runtime_formula_capabilities_anchor_coverage_to_price_universe(tmp_path: Path):
    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "open.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "roe.day.bin", [1.0])

    # Extra directories with only experimental fields should not dilute
    # coverage for the canonical trading universe.
    for i in range(5):
        instrument = f"sz9{i:05d}"
        _write_day_bin(features_dir, instrument, "roe.day.bin", [1.0])

    capabilities = get_runtime_formula_capabilities(
        provider_uri=tmp_path,
        min_coverage_ratio=0.95,
    )

    assert capabilities.total_instruments == 20
    assert "$close" in capabilities.available_fields
    assert "$open" in capabilities.available_fields
    assert "$roe" in capabilities.available_fields


def test_runtime_formula_capabilities_resolve_qlib_data_dir_from_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    qlib_dir = tmp_path / "custom_qlib"
    features_dir = qlib_dir / "features"
    _write_day_bin(features_dir, "sh000001", "close.day.bin", [1.0])
    _write_day_bin(features_dir, "sh000001", "open.day.bin", [1.0])

    monkeypatch.delenv("QLIB_DATA_DIR", raising=False)

    def fake_load_dotenv() -> None:
        monkeypatch.setenv("QLIB_DATA_DIR", str(qlib_dir))

    with patch("src.data_pipeline.readiness.load_dotenv_if_available", side_effect=fake_load_dotenv):
        capabilities = get_runtime_formula_capabilities()

    assert capabilities.total_instruments == 1
    assert "$close" in capabilities.available_fields
    assert "$open" in capabilities.available_fields


def test_formula_operator_specs_use_canonical_non_future_examples(tmp_path: Path):
    capabilities = get_runtime_formula_capabilities(
        provider_uri=tmp_path,
        min_coverage_ratio=0.95,
    )

    operator_block = format_available_operators_for_prompt(capabilities)

    assert OPERATOR_SPECS_BY_NAME["Ref"].qlib_syntax == "Ref($field, N)"
    assert OPERATOR_SPECS_BY_NAME["Rank"].qlib_syntax == "Rank($field)"
    assert "Ref($field, -N)" not in operator_block
    assert "Ref($field, N)" in operator_block


def test_runtime_formula_capabilities_ignore_all_nan_bins(tmp_path: Path):
    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "pb.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "pe_ttm.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "turnover_rate.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "float_mv.day.bin", [np.nan])

    capabilities = get_runtime_formula_capabilities(
        provider_uri=tmp_path,
        min_coverage_ratio=0.95,
    )

    assert "$close" in capabilities.available_fields
    assert "$pb" not in capabilities.available_fields
    assert "$pe_ttm" not in capabilities.available_fields
    assert "$turnover_rate" not in capabilities.available_fields
    assert "$float_mv" not in capabilities.available_fields
