from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.core.env import load_dotenv_if_available
from src.data_pipeline.datasets import DatasetFieldSpec, DatasetSpec

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QLIB_DIR = PROJECT_ROOT / "data" / "qlib_bin"
DEFAULT_MIN_COVERAGE_RATIO = 0.90


@dataclass(frozen=True)
class FieldCoverageStatus:
    spec: DatasetFieldSpec
    instrument_count: int
    total_instruments: int
    coverage_ratio: float
    runtime_available: bool


@dataclass(frozen=True)
class DatasetReadinessStatus:
    spec: DatasetSpec
    staged: bool
    materialized: bool
    runtime_available: bool
    field_status: dict[str, FieldCoverageStatus]


def resolve_qlib_dir(provider_uri: str | Path | None = None) -> Path:
    load_dotenv_if_available()

    if provider_uri is not None:
        return Path(provider_uri)

    qlib_env = os.getenv("QLIB_DATA_DIR")
    if qlib_env:
        return Path(qlib_env) if os.path.isabs(qlib_env) else PROJECT_ROOT / qlib_env

    return DEFAULT_QLIB_DIR


def resolve_features_dir(provider_uri: str | Path | None = None) -> Path:
    return resolve_qlib_dir(provider_uri) / "features"


def read_min_coverage_ratio() -> float:
    raw = os.getenv("PIXIU_FIELD_MIN_COVERAGE_RATIO")
    if not raw:
        return DEFAULT_MIN_COVERAGE_RATIO
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_COVERAGE_RATIO
    return min(max(value, 0.0), 1.0)


def canonical_universe_dirs(instrument_dirs: list[Path]) -> list[Path]:
    universe = [path for path in instrument_dirs if (path / "close.day.bin").exists()]
    return universe or instrument_dirs


def _read_day_bin_values(bin_path: Path) -> np.ndarray:
    try:
        with bin_path.open("rb") as handle:
            header = handle.read(4)
            if len(header) != 4:
                return np.array([], dtype=np.float32)
            return np.fromfile(handle, dtype=np.float32)
    except OSError:
        return np.array([], dtype=np.float32)


def _bin_has_valid_values(bin_path: Path) -> bool:
    values = _read_day_bin_values(bin_path)
    return bool(values.size and np.isfinite(values).any())


def count_feature_bins(features_dir: Path) -> tuple[int, Counter[str]]:
    if not features_dir.exists():
        return 0, Counter()

    instrument_dirs = [path for path in features_dir.iterdir() if path.is_dir()]
    universe_dirs = canonical_universe_dirs(instrument_dirs)
    counter: Counter[str] = Counter()
    for instrument_dir in universe_dirs:
        for bin_path in instrument_dir.glob("*.day.bin"):
            if _bin_has_valid_values(bin_path):
                counter[bin_path.name] += 1
    return len(universe_dirs), counter


def _dataset_has_staged_artifacts(dataset: DatasetSpec) -> bool:
    if dataset.staging_path is None or not dataset.staging_path.exists():
        return False
    return any(dataset.staging_path.glob("*.parquet"))


def get_dataset_readiness(
    dataset_specs: tuple[DatasetSpec, ...],
    provider_uri: str | Path | None = None,
    min_coverage_ratio: float | None = None,
) -> dict[str, DatasetReadinessStatus]:
    min_ratio = read_min_coverage_ratio() if min_coverage_ratio is None else min_coverage_ratio
    features_dir = resolve_features_dir(provider_uri)
    total_instruments, counter = count_feature_bins(features_dir)

    readiness: dict[str, DatasetReadinessStatus] = {}
    for dataset in dataset_specs:
        field_status: dict[str, FieldCoverageStatus] = {}
        for field in dataset.formula_fields:
            instrument_count = counter.get(f"{field.bin_stem}.day.bin", 0)
            coverage_ratio = (instrument_count / total_instruments) if total_instruments else 0.0
            runtime_available = instrument_count > 0 and coverage_ratio >= min_ratio
            field_status[field.formula_name] = FieldCoverageStatus(
                spec=field,
                instrument_count=instrument_count,
                total_instruments=total_instruments,
                coverage_ratio=coverage_ratio,
                runtime_available=runtime_available,
            )

        staged = _dataset_has_staged_artifacts(dataset) if dataset.staging_path is not None else bool(total_instruments)
        materialized = any(status.instrument_count > 0 for status in field_status.values())
        runtime_available = bool(field_status) and all(
            status.runtime_available for status in field_status.values()
        )
        readiness[dataset.name] = DatasetReadinessStatus(
            spec=dataset,
            staged=staged,
            materialized=materialized,
            runtime_available=runtime_available,
            field_status=field_status,
        )

    return readiness
