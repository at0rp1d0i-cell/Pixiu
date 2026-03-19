from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormulaOperatorSpec:
    name: str
    qlib_syntax: str
    description: str
    category: str

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
