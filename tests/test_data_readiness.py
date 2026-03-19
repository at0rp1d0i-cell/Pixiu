from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.data_pipeline.datasets import DAILY_BASIC_DATASET
from src.data_pipeline.readiness import get_dataset_readiness

pytestmark = pytest.mark.unit


def _touch_bin(features_dir: Path, instrument: str, bin_name: str) -> None:
    instrument_dir = features_dir / instrument
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / bin_name).write_bytes(b"")


def test_dataset_readiness_marks_staged_and_materialized_before_runtime_ready(tmp_path: Path):
    staging_dir = tmp_path / "fundamental_staging" / "daily_basic"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "000001.SZ.parquet").write_bytes(b"x")

    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _touch_bin(features_dir, instrument, "close.day.bin")
        if i < 18:
            _touch_bin(features_dir, instrument, "pb.day.bin")
            _touch_bin(features_dir, instrument, "pe_ttm.day.bin")
            _touch_bin(features_dir, instrument, "turnover_rate.day.bin")
            _touch_bin(features_dir, instrument, "float_mv.day.bin")

    dataset = replace(DAILY_BASIC_DATASET, staging_path=staging_dir)
    readiness = get_dataset_readiness((dataset,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["daily_basic"]

    assert status.staged is True
    assert status.materialized is True
    assert status.runtime_available is False
    assert status.field_status["$pb"].coverage_ratio == pytest.approx(0.9)


def test_dataset_readiness_marks_runtime_available_at_threshold(tmp_path: Path):
    staging_dir = tmp_path / "fundamental_staging" / "daily_basic"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "000001.SZ.parquet").write_bytes(b"x")

    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _touch_bin(features_dir, instrument, "close.day.bin")
        if i < 19:
            _touch_bin(features_dir, instrument, "pb.day.bin")
            _touch_bin(features_dir, instrument, "pe_ttm.day.bin")
            _touch_bin(features_dir, instrument, "turnover_rate.day.bin")
            _touch_bin(features_dir, instrument, "float_mv.day.bin")

    dataset = replace(DAILY_BASIC_DATASET, staging_path=staging_dir)
    readiness = get_dataset_readiness((dataset,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["daily_basic"]

    assert status.staged is True
    assert status.materialized is True
    assert status.runtime_available is True
    assert status.field_status["$float_mv"].coverage_ratio == pytest.approx(0.95)
