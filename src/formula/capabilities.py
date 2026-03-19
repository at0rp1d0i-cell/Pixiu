from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.data_pipeline.datasets import (
    ALL_FIELD_SPECS,
    BASE_FIELD_SPECS,
    EXPERIMENTAL_FIELD_SPECS,
    FIELD_SPECS_BY_NAME as _FIELD_SPECS_BY_NAME,
    DatasetFieldSpec,
    get_formula_dataset_specs,
)
from src.data_pipeline.readiness import (
    FieldCoverageStatus,
    get_dataset_readiness,
    read_min_coverage_ratio,
)
from src.formula.manifest import (
    APPROVED_OPERATORS,
    FORMULA_OPERATOR_SPECS,
    FormulaOperatorSpec as _FormulaOperatorSpec,
    OPERATOR_SPECS_BY_NAME as _OPERATOR_SPECS_BY_NAME,
)

FIELD_SPECS_BY_NAME = _FIELD_SPECS_BY_NAME
FormulaFieldSpec = DatasetFieldSpec
FormulaOperatorSpec = _FormulaOperatorSpec
OPERATOR_SPECS_BY_NAME = _OPERATOR_SPECS_BY_NAME


@dataclass(frozen=True)
class RuntimeFieldStatus:
    spec: DatasetFieldSpec
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


def get_runtime_formula_capabilities(
    provider_uri=None,
    min_coverage_ratio: float | None = None,
) -> FormulaCapabilities:
    min_ratio = read_min_coverage_ratio() if min_coverage_ratio is None else min_coverage_ratio
    dataset_readiness = get_dataset_readiness(
        get_formula_dataset_specs(),
        provider_uri=provider_uri,
        min_coverage_ratio=min_ratio,
    )
    field_status: dict[str, RuntimeFieldStatus] = {}
    total_instruments = 0
    for dataset in get_formula_dataset_specs():
        readiness = dataset_readiness[dataset.name]
        for spec in dataset.formula_fields:
            status: FieldCoverageStatus = readiness.field_status[spec.formula_name]
            total_instruments = max(total_instruments, status.total_instruments)
            field_status[spec.formula_name] = RuntimeFieldStatus(
                spec=spec,
                instrument_count=status.instrument_count,
                total_instruments=status.total_instruments,
                coverage_ratio=status.coverage_ratio,
                available=status.runtime_available,
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
