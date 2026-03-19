from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormulaFieldSpec:
    formula_name: str
    bin_stem: str
    source: str
    description: str
    category: str


@dataclass(frozen=True)
class FormulaOperatorSpec:
    name: str
    qlib_syntax: str
    description: str
    category: str


BASE_FIELD_SPECS = (
    FormulaFieldSpec("$open", "open", "qlib_price_volume", "开盘价", "price_volume"),
    FormulaFieldSpec("$high", "high", "qlib_price_volume", "最高价", "price_volume"),
    FormulaFieldSpec("$low", "low", "qlib_price_volume", "最低价", "price_volume"),
    FormulaFieldSpec("$close", "close", "qlib_price_volume", "收盘价", "price_volume"),
    FormulaFieldSpec("$volume", "volume", "qlib_price_volume", "成交量", "price_volume"),
    FormulaFieldSpec("$vwap", "vwap", "qlib_price_volume", "成交量加权均价", "price_volume"),
    FormulaFieldSpec("$amount", "amount", "qlib_price_volume", "成交额", "price_volume"),
    FormulaFieldSpec("$factor", "factor", "qlib_price_volume", "复权因子", "price_volume"),
)

EXPERIMENTAL_FIELD_SPECS = (
    FormulaFieldSpec("$roe", "roe", "fina_indicator", "净资产收益率", "fundamental"),
    FormulaFieldSpec("$pb", "pb", "daily_basic", "市净率", "fundamental"),
    FormulaFieldSpec("$pe_ttm", "pe_ttm", "daily_basic", "滚动市盈率", "fundamental"),
    FormulaFieldSpec("$turnover_rate", "turnover_rate", "daily_basic", "换手率", "fundamental"),
    FormulaFieldSpec("$float_mv", "float_mv", "daily_basic", "流通市值", "fundamental"),
)

ALL_FIELD_SPECS = BASE_FIELD_SPECS + EXPERIMENTAL_FIELD_SPECS
FIELD_SPECS_BY_NAME = {spec.formula_name: spec for spec in ALL_FIELD_SPECS}

APPROVED_OPERATORS = (
    "Mean", "Std", "Var", "Max", "Min", "Sum",
    "Ref", "Delta", "Slope", "Rsquare", "Resi",
    "Rank", "Abs", "Sign",
    "Log", "Power", "Sqrt",
    "Corr", "Cov",
    "If", "Gt", "Lt", "Ge", "Le", "Eq", "Ne",
    "And", "Or", "Not",
    "Add", "Sub", "Mul", "Div",
    "IdxMax", "IdxMin", "Comb", "Count", "Mad",
    "WMA", "EMA",
    "Ts_Mean", "Ts_Std", "Ts_Max", "Ts_Min", "Ts_Sum",
    "Ts_Rank", "Ts_Corr", "Ts_Cov", "Ts_WMA", "Ts_Slope",
    "SignedPower", "Greater", "Less",
)

FORMULA_OPERATOR_SPECS = (
    FormulaOperatorSpec("Ref", "Ref($field, N)", "N 日前的值（N 必须为正整数）", "temporal_transform"),
    FormulaOperatorSpec("Mean", "Mean($field, N)", "N 日均值", "temporal_transform"),
    FormulaOperatorSpec("Std", "Std($field, N)", "N 日标准差", "temporal_transform"),
    FormulaOperatorSpec("Corr", "Corr($x, $y, N)", "N 日相关系数", "temporal_transform"),
    FormulaOperatorSpec("Max", "Max($field, N)", "N 日最大值", "temporal_transform"),
    FormulaOperatorSpec("Min", "Min($field, N)", "N 日最小值", "temporal_transform"),
    FormulaOperatorSpec("Delta", "Delta($field, N)", "N 日变化量", "temporal_transform"),
    FormulaOperatorSpec("Rank", "Rank($field)", "截面排名", "cross_sectional"),
    FormulaOperatorSpec("Abs", "Abs($field)", "绝对值", "math"),
    FormulaOperatorSpec("Sign", "Sign($field)", "符号函数", "math"),
    FormulaOperatorSpec("Log", "Log($field)", "自然对数（输入必须 > 0）", "math"),
    FormulaOperatorSpec("If", "If(cond, t, f)", "条件表达式", "logic"),
)

OPERATOR_SPECS_BY_NAME = {spec.name: spec for spec in FORMULA_OPERATOR_SPECS}
