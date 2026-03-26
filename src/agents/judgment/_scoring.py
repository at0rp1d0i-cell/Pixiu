"""Private scoring helpers for the judgment runtime."""
from __future__ import annotations

from typing import Optional

from src.schemas.backtest import BacktestReport
from src.schemas.failure_constraint import FailureMode
from src.schemas.judgment import ThresholdCheck
from src.schemas.thresholds import THRESHOLDS


def _build_threshold_checks(report: BacktestReport) -> list[ThresholdCheck]:
    metrics = report.metrics
    turnover = metrics.turnover_rate
    coverage = metrics.coverage if metrics.coverage is not None else 1.0
    return [
        ThresholdCheck(
            metric="sharpe",
            value=metrics.sharpe,
            threshold=THRESHOLDS.min_sharpe,
            passed=metrics.sharpe >= THRESHOLDS.min_sharpe,
        ),
        ThresholdCheck(
            metric="ic_mean",
            value=metrics.ic_mean,
            threshold=THRESHOLDS.min_ic_mean,
            passed=metrics.ic_mean >= THRESHOLDS.min_ic_mean,
        ),
        ThresholdCheck(
            metric="icir",
            value=metrics.icir,
            threshold=THRESHOLDS.min_icir,
            passed=metrics.icir >= THRESHOLDS.min_icir,
        ),
        ThresholdCheck(
            metric="turnover",
            value=turnover,
            threshold=THRESHOLDS.max_turnover_rate,
            passed=turnover <= THRESHOLDS.max_turnover_rate,
        ),
        ThresholdCheck(
            metric="max_drawdown",
            value=metrics.max_drawdown,
            threshold=THRESHOLDS.max_drawdown,
            passed=metrics.max_drawdown <= THRESHOLDS.max_drawdown,
        ),
        ThresholdCheck(
            metric="coverage",
            value=coverage,
            threshold=THRESHOLDS.min_coverage,
            passed=coverage >= THRESHOLDS.min_coverage,
        ),
    ]


def _diagnose_failure(
    report: BacktestReport, failed_checks: list[ThresholdCheck]
) -> tuple[Optional[FailureMode], str, Optional[str]]:
    if report.error_message:
        return (
            FailureMode.EXECUTION_ERROR,
            f"回测执行失败：{report.error_message}",
            "检查公式语法、模板渲染和执行环境。",
        )

    if not failed_checks:
        return (None, "所有关键指标通过。", None)

    primary = failed_checks[0]
    mode_map: dict[str, FailureMode] = {
        "sharpe": FailureMode.LOW_SHARPE,
        "ic_mean": FailureMode.NO_IC,
        "icir": FailureMode.NO_IC,
        "turnover": FailureMode.HIGH_TURNOVER,
        "max_drawdown": FailureMode.HIGH_DRAWDOWN,
        "coverage": FailureMode.LOW_COVERAGE,
    }
    failure_mode: FailureMode = mode_map.get(primary.metric, FailureMode.LOW_SHARPE)

    # Refine IC failure: distinguish negative IC from near-zero IC
    if failure_mode == FailureMode.NO_IC and primary.metric == "ic_mean":
        if primary.value < -0.01:
            failure_mode = FailureMode.NEGATIVE_IC

    explanations: dict[FailureMode, str] = {
        FailureMode.LOW_SHARPE: f"Sharpe={primary.value:.2f}，低于门槛 {primary.threshold:.2f}。",
        FailureMode.NO_IC: f"IC={primary.value:.4f}，低于门槛 {primary.threshold:.4f}（近零信号）。",
        FailureMode.NEGATIVE_IC: f"IC={primary.value:.4f}，为明显负值，信号方向可能反转。",
        FailureMode.HIGH_TURNOVER: f"换手率={primary.value:.2%}，高于门槛 {primary.threshold:.2%}。",
        FailureMode.HIGH_DRAWDOWN: f"最大回撤={primary.value:.2%}，高于门槛 {primary.threshold:.2%}。",
        FailureMode.LOW_COVERAGE: f"覆盖率={primary.value:.2%}，低于门槛 {primary.threshold:.2%}。",
    }
    suggestions: dict[FailureMode, str] = {
        FailureMode.LOW_SHARPE: "考虑更换信号方向或延长窗口平滑噪声。",
        FailureMode.NO_IC: "检查经济假设是否成立，或缩小适用股票池。",
        FailureMode.NEGATIVE_IC: "信号方向与收益负相关，尝试对信号取反或重审经济逻辑。",
        FailureMode.HIGH_TURNOVER: "增大平滑窗口，降低信号抖动。",
        FailureMode.HIGH_DRAWDOWN: "增加风险过滤或缩短暴露窗口。",
        FailureMode.LOW_COVERAGE: "检查公式是否过度依赖稀疏字段或存在数据缺失。",
    }

    return (
        failure_mode,
        explanations.get(failure_mode, "未通过关键阈值检查。"),
        suggestions.get(failure_mode),
    )


def _normalize_positive(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 1.0 if value > 0 else 0.0
    return max(0.0, min(1.0, value / threshold))


def _normalize_negative(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 1.0
    return max(0.0, min(1.0, threshold / max(value, threshold)))


def _score_report(report: BacktestReport) -> float:
    metrics = report.metrics
    turnover = metrics.turnover_rate
    coverage = metrics.coverage if metrics.coverage is not None else 1.0
    raw_score = (
        0.35 * _normalize_positive(metrics.sharpe, THRESHOLDS.min_sharpe)
        + 0.20 * _normalize_positive(metrics.ic_mean, THRESHOLDS.min_ic_mean)
        + 0.20 * _normalize_positive(metrics.icir, THRESHOLDS.min_icir)
        + 0.10 * _normalize_negative(turnover, THRESHOLDS.max_turnover_rate)
        + 0.10 * _normalize_negative(max(metrics.max_drawdown, 0.0), THRESHOLDS.max_drawdown)
        + 0.05 * _normalize_positive(coverage, THRESHOLDS.min_coverage)
    )
    return round(raw_score, 4)


def _build_reason_codes(
    report: BacktestReport,
    failure_mode: Optional[FailureMode],
    failed_checks: list[ThresholdCheck],
) -> list[str]:
    if report.error_message:
        return ["EXECUTION_FAILED"]

    code_map: dict[FailureMode, str] = {
        FailureMode.LOW_SHARPE: "LOW_SHARPE",
        FailureMode.NO_IC: "LOW_IC",
        FailureMode.NEGATIVE_IC: "NEGATIVE_IC",
        FailureMode.HIGH_TURNOVER: "HIGH_TURNOVER",
        FailureMode.HIGH_DRAWDOWN: "HIGH_DRAWDOWN",
        FailureMode.LOW_COVERAGE: "LOW_COVERAGE",
        FailureMode.EXECUTION_ERROR: "EXECUTION_FAILED",
        FailureMode.OVERFITTING: "OVERFITTING",
        FailureMode.DUPLICATE: "DUPLICATE",
    }
    codes = [code_map[failure_mode]] if failure_mode is not None and failure_mode in code_map else []

    if report.status != "success":
        codes.append("PARSE_INCOMPLETE" if report.failure_stage == "parse" else "RUN_FAILED")

    if not report.error_message and not failed_checks:
        if report.oos_passed is True:
            codes.append("OOS_PASSED")
        elif report.oos_passed is False:
            codes.append("OOS_FAILED")
        elif report.oos_window is not None or report.metrics_scope == "discovery":
            codes.append("PENDING_OOS")

    return codes or [f"FAILED_{check.metric.upper()}" for check in failed_checks]


def _decide(
    report: BacktestReport,
    overall_passed: bool,
    score: float,
    failed_checks: list[ThresholdCheck],
) -> str:
    if report.status != "success" or report.error_message:
        return "retry"
    if overall_passed:
        if report.oos_passed is True:
            return "promote" if score >= THRESHOLDS.min_promote_score else "archive"
        if report.oos_passed is False:
            return "archive"
        return "candidate"
    if failed_checks and any(check.metric == "sharpe" and check.value <= 0 for check in failed_checks):
        return "reject"
    return "archive"
