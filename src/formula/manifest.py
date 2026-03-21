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
    "Log", "Power",
    "Corr", "Cov",
    "If", "Gt", "Lt", "Ge", "Le", "Eq", "Ne",
    "And", "Or", "Not",
    "Add", "Sub", "Mul", "Div",
    "IdxMax", "IdxMin", "Count", "Mad",
    "WMA", "EMA",
    "Greater", "Less",
    "Kurt", "Skew", "Med", "Quantile",
)

FORMULA_OPERATOR_SPECS = (
    FormulaOperatorSpec("Ref", "Ref($field, N)", "N 日前的值（N 必须为正整数）", "temporal_transform"),
    FormulaOperatorSpec("Mean", "Mean($field, N)", "N 日均值", "temporal_transform"),
    FormulaOperatorSpec("Std", "Std($field, N)", "N 日标准差", "temporal_transform"),
    FormulaOperatorSpec("Corr", "Corr($x, $y, N)", "N 日相关系数", "temporal_transform"),
    FormulaOperatorSpec("Max", "Max($field, N)", "N 日最大值", "temporal_transform"),
    FormulaOperatorSpec("Min", "Min($field, N)", "N 日最小值", "temporal_transform"),
    FormulaOperatorSpec("Delta", "Delta($field, N)", "N 日变化量", "temporal_transform"),
    FormulaOperatorSpec("Rank", "Rank($field, N)", "N 日时序排名（归一化到 [0,1]）", "temporal_transform"),
    FormulaOperatorSpec("Abs", "Abs($field)", "绝对值", "math"),
    FormulaOperatorSpec("Sign", "Sign($field)", "符号函数", "math"),
    FormulaOperatorSpec("Log", "Log($field)", "自然对数（输入必须 > 0）", "math"),
    FormulaOperatorSpec("If", "If(cond, t, f)", "条件表达式", "logic"),
    FormulaOperatorSpec("Kurt", "Kurt($field, N)", "N 日峰度", "temporal_transform"),
    FormulaOperatorSpec("Skew", "Skew($field, N)", "N 日偏度", "temporal_transform"),
    FormulaOperatorSpec("Med", "Med($field, N)", "N 日中位数", "temporal_transform"),
    FormulaOperatorSpec("Quantile", "Quantile($field, N, q)", "N 日分位数（q 为 0~1）", "temporal_transform"),
)

OPERATOR_SPECS_BY_NAME = {spec.name: spec for spec in FORMULA_OPERATOR_SPECS}
