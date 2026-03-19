from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.core.env import load_dotenv_if_available
from src.formula.manifest import (
    ALL_FIELD_SPECS,
    APPROVED_OPERATORS,
    BASE_FIELD_SPECS,
    EXPERIMENTAL_FIELD_SPECS,
    FIELD_SPECS_BY_NAME as _FIELD_SPECS_BY_NAME,
    FORMULA_OPERATOR_SPECS,
    FormulaFieldSpec,
    FormulaOperatorSpec as _FormulaOperatorSpec,
    OPERATOR_SPECS_BY_NAME as _OPERATOR_SPECS_BY_NAME,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QLIB_DIR = PROJECT_ROOT / "data" / "qlib_bin"
DEFAULT_MIN_COVERAGE_RATIO = 0.95

FIELD_SPECS_BY_NAME = _FIELD_SPECS_BY_NAME
FormulaOperatorSpec = _FormulaOperatorSpec
OPERATOR_SPECS_BY_NAME = _OPERATOR_SPECS_BY_NAME


@dataclass(frozen=True)
class RuntimeFieldStatus:
    spec: FormulaFieldSpec
    instrument_count: int
    total_instruments: int
    coverage_ratio: float
    available: bool


@dataclass(frozen=True)
class FormulaCapabilities:
    field_status: dict[str, RuntimeFieldStatus]
    approved_operators: tuple[str, ...]
    total_instruments: int
    min_coverage_ratio: float

    @property
    def available_fields(self) -> tuple[str, ...]:
        return tuple(
            spec.formula_name
            for spec in ALL_FIELD_SPECS
            if self.field_status[spec.formula_name].available
        )

    @property
    def base_fields(self) -> tuple[str, ...]:
        return tuple(spec.formula_name for spec in BASE_FIELD_SPECS)

    @property
    def experimental_fields(self) -> tuple[str, ...]:
        return tuple(spec.formula_name for spec in EXPERIMENTAL_FIELD_SPECS)

    @property
    def available_experimental_fields(self) -> tuple[str, ...]:
        return tuple(
            spec.formula_name
            for spec in EXPERIMENTAL_FIELD_SPECS
            if self.field_status[spec.formula_name].available
        )


def _resolve_qlib_dir(provider_uri: str | Path | None = None) -> Path:
    load_dotenv_if_available()

    if provider_uri is not None:
        return Path(provider_uri)

    qlib_env = os.getenv("QLIB_DATA_DIR")
    if qlib_env:
        return Path(qlib_env) if os.path.isabs(qlib_env) else PROJECT_ROOT / qlib_env

    return DEFAULT_QLIB_DIR


def _resolve_features_dir(provider_uri: str | Path | None = None) -> Path:
    return _resolve_qlib_dir(provider_uri) / "features"


def _read_min_coverage_ratio() -> float:
    raw = os.getenv("PIXIU_FIELD_MIN_COVERAGE_RATIO")
    if not raw:
        return DEFAULT_MIN_COVERAGE_RATIO
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_COVERAGE_RATIO
    return min(max(value, 0.0), 1.0)


def _canonical_universe_dirs(instrument_dirs: list[Path]) -> list[Path]:
    universe = [path for path in instrument_dirs if (path / "close.day.bin").exists()]
    return universe or instrument_dirs


def _count_feature_bins(features_dir: Path) -> tuple[int, Counter[str]]:
    if not features_dir.exists():
        return 0, Counter()

    instrument_dirs = [path for path in features_dir.iterdir() if path.is_dir()]
    universe_dirs = _canonical_universe_dirs(instrument_dirs)
    counter: Counter[str] = Counter()
    for instrument_dir in universe_dirs:
        for bin_path in instrument_dir.glob("*.day.bin"):
            counter[bin_path.name] += 1
    return len(universe_dirs), counter


def get_runtime_formula_capabilities(
    provider_uri: str | Path | None = None,
    min_coverage_ratio: float | None = None,
) -> FormulaCapabilities:
    min_ratio = _read_min_coverage_ratio() if min_coverage_ratio is None else min_coverage_ratio
    features_dir = _resolve_features_dir(provider_uri)
    total_instruments, counter = _count_feature_bins(features_dir)

    field_status: dict[str, RuntimeFieldStatus] = {}
    for spec in ALL_FIELD_SPECS:
        bin_name = f"{spec.bin_stem}.day.bin"
        instrument_count = counter.get(bin_name, 0)
        coverage_ratio = (instrument_count / total_instruments) if total_instruments else 0.0
        available = instrument_count > 0 and coverage_ratio >= min_ratio
        field_status[spec.formula_name] = RuntimeFieldStatus(
            spec=spec,
            instrument_count=instrument_count,
            total_instruments=total_instruments,
            coverage_ratio=coverage_ratio,
            available=available,
        )

    return FormulaCapabilities(
        field_status=field_status,
        approved_operators=APPROVED_OPERATORS,
        total_instruments=total_instruments,
        min_coverage_ratio=min_ratio,
    )


def get_allowed_formula_fields(
    provider_uri: str | Path | None = None,
    min_coverage_ratio: float | None = None,
) -> tuple[str, ...]:
    return get_runtime_formula_capabilities(
        provider_uri=provider_uri,
        min_coverage_ratio=min_coverage_ratio,
    ).available_fields


def get_approved_formula_operators() -> tuple[str, ...]:
    return APPROVED_OPERATORS


def format_available_fields_for_prompt(capabilities: FormulaCapabilities) -> str:
    base_fields = [field for field in capabilities.base_fields if field in capabilities.available_fields]
    experimental_fields = [
        field for field in capabilities.experimental_fields if field in capabilities.available_fields
    ]
    unavailable_experimental = [
        field for field in capabilities.experimental_fields if field not in capabilities.available_fields
    ]

    lines: list[str] = []
    if base_fields:
        lines.append(f"  基础价量字段：{', '.join(base_fields)}")
    if experimental_fields:
        lines.append(f"  扩展实验字段：{', '.join(experimental_fields)}")
    if unavailable_experimental:
        lines.append(f"  当前未就绪字段（禁止使用）：{', '.join(unavailable_experimental)}")
    if not lines:
        lines.append("  （当前未检测到本地 Qlib 可用字段，禁止猜测未列出的字段）")
    return "\n".join(lines)


def format_available_operators_for_prompt(capabilities: FormulaCapabilities) -> str:
    approved = set(capabilities.approved_operators)
    common_specs = [spec for spec in FORMULA_OPERATOR_SPECS if spec.name in approved]
    described_names = {spec.name for spec in common_specs}
    remaining = [name for name in capabilities.approved_operators if name not in described_names]

    lines: list[str] = []
    if common_specs:
        lines.append("  常用稳定算子：")
        for spec in common_specs:
            lines.append(f"    - `{spec.qlib_syntax}` — {spec.description}")
    if remaining:
        lines.append(f"  其余运行时 allowlist：{', '.join(remaining)}")
    if not lines:
        lines.append("  （当前未配置运行时算子 allowlist）")
    return "\n".join(lines)
