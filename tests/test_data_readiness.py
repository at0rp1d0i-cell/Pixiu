from __future__ import annotations

import struct
from dataclasses import replace
from pathlib import Path

import pytest
import numpy as np

from src.data_pipeline.datasets import DAILY_BASIC_DATASET
from src.data_pipeline.datasets import QLIB_PRICE_VOLUME_DATASET
from src.data_pipeline.readiness import (
    canonical_universe_dirs,
    get_dataset_readiness,
    read_min_coverage_ratio,
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


def test_dataset_readiness_marks_staged_and_materialized_before_runtime_ready(tmp_path: Path):
    staging_dir = tmp_path / "fundamental_staging" / "daily_basic"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "000001.SZ.parquet").write_bytes(b"x")

    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        if i < 18:
            _write_day_bin(features_dir, instrument, "pb.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "pe_ttm.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "turnover_rate.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "float_mv.day.bin", [1.0])

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
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        if i < 19:
            _write_day_bin(features_dir, instrument, "pb.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "pe_ttm.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "turnover_rate.day.bin", [1.0])
            _write_day_bin(features_dir, instrument, "float_mv.day.bin", [1.0])

    dataset = replace(DAILY_BASIC_DATASET, staging_path=staging_dir)
    readiness = get_dataset_readiness((dataset,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["daily_basic"]

    assert status.staged is True
    assert status.materialized is True
    assert status.runtime_available is True
    assert status.field_status["$float_mv"].coverage_ratio == pytest.approx(0.95)


def test_dataset_readiness_ignores_all_nan_bins(tmp_path: Path):
    staging_dir = tmp_path / "fundamental_staging" / "daily_basic"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "000001.SZ.parquet").write_bytes(b"x")

    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "pb.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "pe_ttm.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "turnover_rate.day.bin", [np.nan])
        _write_day_bin(features_dir, instrument, "float_mv.day.bin", [np.nan])

    dataset = replace(DAILY_BASIC_DATASET, staging_path=staging_dir)
    readiness = get_dataset_readiness((dataset,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["daily_basic"]

    assert status.staged is True
    assert status.materialized is False
    assert status.runtime_available is False
    assert status.field_status["$pb"].instrument_count == 0


def test_dataset_readiness_marks_price_volume_unstaged_and_unmaterialized_without_features_dir(
    tmp_path: Path,
):
    readiness = get_dataset_readiness((QLIB_PRICE_VOLUME_DATASET,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["qlib_price_volume"]

    assert status.staged is False
    assert status.materialized is False
    assert status.runtime_available is False
    assert status.field_status["$close"].instrument_count == 0


def test_dataset_readiness_keeps_materialized_and_runtime_ready_even_when_stage_is_empty(
    tmp_path: Path,
):
    staging_dir = tmp_path / "fundamental_staging" / "daily_basic"
    staging_dir.mkdir(parents=True, exist_ok=True)

    features_dir = tmp_path / "features"
    for i in range(20):
        instrument = f"sh{i:06d}"
        _write_day_bin(features_dir, instrument, "close.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "pb.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "pe_ttm.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "turnover_rate.day.bin", [1.0])
        _write_day_bin(features_dir, instrument, "float_mv.day.bin", [1.0])

    dataset = replace(DAILY_BASIC_DATASET, staging_path=staging_dir)
    readiness = get_dataset_readiness((dataset,), provider_uri=tmp_path, min_coverage_ratio=0.95)
    status = readiness["daily_basic"]

    assert status.staged is False
    assert status.materialized is True
    assert status.runtime_available is True
    assert status.field_status["$pb"].coverage_ratio == pytest.approx(1.0)


def test_read_min_coverage_ratio_clamps_and_falls_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PIXIU_FIELD_MIN_COVERAGE_RATIO", raising=False)
    assert read_min_coverage_ratio() == pytest.approx(0.90)

    monkeypatch.setenv("PIXIU_FIELD_MIN_COVERAGE_RATIO", "not-a-number")
    assert read_min_coverage_ratio() == pytest.approx(0.90)

    monkeypatch.setenv("PIXIU_FIELD_MIN_COVERAGE_RATIO", "-0.25")
    assert read_min_coverage_ratio() == pytest.approx(0.0)

    monkeypatch.setenv("PIXIU_FIELD_MIN_COVERAGE_RATIO", "1.25")
    assert read_min_coverage_ratio() == pytest.approx(1.0)


def test_canonical_universe_dirs_falls_back_when_close_bins_are_missing(tmp_path: Path):
    features_dir = tmp_path / "features"
    first = features_dir / "sh000001"
    second = features_dir / "sh000002"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)
    (first / "pb.day.bin").write_bytes(b"")
    (second / "roe.day.bin").write_bytes(b"")

    universe_dirs = canonical_universe_dirs([first, second])

    assert universe_dirs == [first, second]


def test_canonical_universe_dirs_prefers_close_bins_when_present(tmp_path: Path):
    features_dir = tmp_path / "features"
    canonical = features_dir / "sh000001"
    ignored = features_dir / "sh000002"
    canonical.mkdir(parents=True, exist_ok=True)
    ignored.mkdir(parents=True, exist_ok=True)
    (canonical / "close.day.bin").write_bytes(b"")
    (ignored / "roe.day.bin").write_bytes(b"")

    universe_dirs = canonical_universe_dirs([canonical, ignored])

    assert universe_dirs == [canonical]


def test_canonical_universe_dirs_returns_empty_for_empty_input():
    assert canonical_universe_dirs([]) == []
