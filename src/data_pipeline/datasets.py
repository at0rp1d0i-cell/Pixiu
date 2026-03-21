from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FUNDAMENTAL_STAGING_DIR = DATA_DIR / "fundamental_staging"


@dataclass(frozen=True)
class DatasetFieldSpec:
    formula_name: str
    bin_stem: str
    source: str
    source_field: str
    description: str
    category: str
    runtime_group: str


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    source_type: str
    staging_path: Path | None
    required_source_fields: tuple[str, ...]
    formula_fields: tuple[DatasetFieldSpec, ...]
    runtime_group: str


QLIB_PRICE_VOLUME_DATASET = DatasetSpec(
    name="qlib_price_volume",
    source_type="qlib_builtin",
    staging_path=None,
    required_source_fields=(),
    formula_fields=(
        DatasetFieldSpec("$open", "open", "qlib_price_volume", "open", "开盘价", "price_volume", "base"),
        DatasetFieldSpec("$high", "high", "qlib_price_volume", "high", "最高价", "price_volume", "base"),
        DatasetFieldSpec("$low", "low", "qlib_price_volume", "low", "最低价", "price_volume", "base"),
        DatasetFieldSpec("$close", "close", "qlib_price_volume", "close", "收盘价", "price_volume", "base"),
        DatasetFieldSpec("$volume", "volume", "qlib_price_volume", "volume", "成交量", "price_volume", "base"),
        DatasetFieldSpec("$vwap", "vwap", "qlib_price_volume", "vwap", "成交量加权均价", "price_volume", "base"),
        DatasetFieldSpec("$amount", "amount", "qlib_price_volume", "amount", "成交额", "price_volume", "base"),
        DatasetFieldSpec("$factor", "factor", "qlib_price_volume", "factor", "复权因子", "price_volume", "base"),
    ),
    runtime_group="base",
)

FINA_INDICATOR_DATASET = DatasetSpec(
    name="fina_indicator",
    source_type="tushare_fina_indicator",
    staging_path=FUNDAMENTAL_STAGING_DIR / "fina_indicator",
    required_source_fields=(
        "ts_code",
        "ann_date",
        "end_date",
        "eps",
        "dt_eps",
        "roe",
        "roe_waa",
        "roe_dt",
        "roa",
        "netprofit_margin",
        "gross_margin",
        "current_ratio",
        "quick_ratio",
        "debt_to_assets",
        "assets_turn",
    ),
    formula_fields=(
        DatasetFieldSpec("$roe", "roe", "fina_indicator", "roe", "净资产收益率", "fundamental", "experimental"),
        DatasetFieldSpec("$roe_waa", "roe_waa", "fina_indicator", "roe_waa", "加权平均净资产收益率", "fundamental", "experimental"),
        DatasetFieldSpec("$roe_dt", "roe_dt", "fina_indicator", "roe_dt", "扣非净资产收益率", "fundamental", "experimental"),
        DatasetFieldSpec("$roa", "roa", "fina_indicator", "roa", "总资产报酬率", "fundamental", "experimental"),
        DatasetFieldSpec("$eps", "eps", "fina_indicator", "eps", "每股收益", "fundamental", "experimental"),
        DatasetFieldSpec("$dt_eps", "dt_eps", "fina_indicator", "dt_eps", "扣非每股收益", "fundamental", "experimental"),
        DatasetFieldSpec("$netprofit_margin", "netprofit_margin", "fina_indicator", "netprofit_margin", "净利润率", "fundamental", "experimental"),
        DatasetFieldSpec("$gross_margin", "gross_margin", "fina_indicator", "gross_margin", "毛利率", "fundamental", "experimental"),
        DatasetFieldSpec("$current_ratio", "current_ratio", "fina_indicator", "current_ratio", "流动比率", "fundamental", "experimental"),
        DatasetFieldSpec("$quick_ratio", "quick_ratio", "fina_indicator", "quick_ratio", "速动比率", "fundamental", "experimental"),
        DatasetFieldSpec("$debt_to_assets", "debt_to_assets", "fina_indicator", "debt_to_assets", "资产负债率", "fundamental", "experimental"),
        DatasetFieldSpec("$assets_turn", "assets_turn", "fina_indicator", "assets_turn", "总资产周转率", "fundamental", "experimental"),
    ),
    runtime_group="experimental",
)

DAILY_BASIC_DATASET = DatasetSpec(
    name="daily_basic",
    source_type="tushare_daily_basic",
    staging_path=FUNDAMENTAL_STAGING_DIR / "daily_basic",
    required_source_fields=(
        "ts_code",
        "trade_date",
        "turnover_rate",
        "pe_ttm",
        "pb",
        "circ_mv",
    ),
    formula_fields=(
        DatasetFieldSpec("$pb", "pb", "daily_basic", "pb", "市净率", "fundamental", "experimental"),
        DatasetFieldSpec("$pe_ttm", "pe_ttm", "daily_basic", "pe_ttm", "滚动市盈率", "fundamental", "experimental"),
        DatasetFieldSpec("$turnover_rate", "turnover_rate", "daily_basic", "turnover_rate", "换手率", "fundamental", "experimental"),
        DatasetFieldSpec("$float_mv", "float_mv", "daily_basic", "circ_mv", "流通市值", "fundamental", "experimental"),
    ),
    runtime_group="experimental",
)

FORMULA_DATASET_SPECS = (
    QLIB_PRICE_VOLUME_DATASET,
    FINA_INDICATOR_DATASET,
    DAILY_BASIC_DATASET,
)

ALL_FIELD_SPECS = tuple(
    field
    for dataset in FORMULA_DATASET_SPECS
    for field in dataset.formula_fields
)
BASE_FIELD_SPECS = tuple(
    field for field in ALL_FIELD_SPECS if field.runtime_group == "base"
)
EXPERIMENTAL_FIELD_SPECS = tuple(
    field for field in ALL_FIELD_SPECS if field.runtime_group == "experimental"
)
FIELD_SPECS_BY_NAME = {spec.formula_name: spec for spec in ALL_FIELD_SPECS}
DATASET_SPECS_BY_NAME = {spec.name: spec for spec in FORMULA_DATASET_SPECS}


def get_formula_dataset_specs() -> tuple[DatasetSpec, ...]:
    return FORMULA_DATASET_SPECS


def get_formula_field_specs() -> tuple[DatasetFieldSpec, ...]:
    return ALL_FIELD_SPECS
