"""
Pixiu v2: Deterministic judgment runtime for the Stage 4→5 golden path.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import (
    CIOReport,
    CorrelationFlag,
    CriticVerdict,
    FactorWeight,
    PortfolioAllocation,
    RiskAuditReport,
    ThresholdCheck,
)
from src.schemas.state import AgentState
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


def _diagnose_failure(report: BacktestReport, failed_checks: list[ThresholdCheck]) -> tuple[str | None, str, str | None]:
    if report.error_message:
        return (
            "execution_error",
            f"回测执行失败：{report.error_message}",
            "检查公式语法、模板渲染和执行环境。",
        )

    if not failed_checks:
        return (None, "所有关键指标通过。", None)

    primary = failed_checks[0]
    mode_map = {
        "sharpe": "low_sharpe",
        "ic_mean": "low_ic",
        "icir": "low_icir",
        "turnover": "high_turnover",
        "max_drawdown": "high_drawdown",
        "coverage": "low_coverage",
    }
    failure_mode = mode_map.get(primary.metric, "threshold_failure")

    explanations = {
        "low_sharpe": f"Sharpe={primary.value:.2f}，低于门槛 {primary.threshold:.2f}。",
        "low_ic": f"IC={primary.value:.4f}，低于门槛 {primary.threshold:.4f}。",
        "low_icir": f"ICIR={primary.value:.2f}，低于门槛 {primary.threshold:.2f}。",
        "high_turnover": f"换手率={primary.value:.2%}，高于门槛 {primary.threshold:.2%}。",
        "high_drawdown": f"最大回撤={primary.value:.2%}，高于门槛 {primary.threshold:.2%}。",
        "low_coverage": f"覆盖率={primary.value:.2%}，低于门槛 {primary.threshold:.2%}。",
    }
    suggestions = {
        "low_sharpe": "考虑更换信号方向或延长窗口平滑噪声。",
        "low_ic": "检查经济假设是否成立，或缩小适用股票池。",
        "low_icir": "检查不同市场状态下的稳定性。",
        "high_turnover": "增大平滑窗口，降低信号抖动。",
        "high_drawdown": "增加风险过滤或缩短暴露窗口。",
        "low_coverage": "检查公式是否过度依赖稀疏字段或存在数据缺失。",
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


def _build_reason_codes(report: BacktestReport, failure_mode: str | None, failed_checks: list[ThresholdCheck]) -> list[str]:
    if report.error_message:
        return ["EXECUTION_FAILED"]

    code_map = {
        "low_sharpe": "LOW_SHARPE",
        "low_ic": "LOW_IC",
        "low_icir": "LOW_ICIR",
        "high_turnover": "HIGH_TURNOVER",
        "high_drawdown": "HIGH_DRAWDOWN",
        "low_coverage": "LOW_COVERAGE",
        "threshold_failure": "THRESHOLD_FAILURE",
    }
    codes = [code_map[failure_mode]] if failure_mode in code_map else []

    if report.status != "success":
        codes.append("PARSE_INCOMPLETE" if report.failure_stage == "parse" else "RUN_FAILED")

    return codes or [f"FAILED_{check.metric.upper()}" for check in failed_checks]


def _decide(report: BacktestReport, overall_passed: bool, score: float, failed_checks: list[ThresholdCheck]) -> str:
    if report.status != "success" or report.error_message:
        return "retry"
    if overall_passed:
        return "promote" if score >= 0.8 else "archive"
    if failed_checks and any(check.metric == "sharpe" and check.value <= 0 for check in failed_checks):
        return "reject"
    return "archive"


class Critic:
    """Deterministic Stage 5A critic."""

    async def evaluate(self, report: BacktestReport) -> CriticVerdict:
        checks = _build_threshold_checks(report)
        failed_checks = [check for check in checks if not check.passed]
        overall_passed = not report.error_message and not failed_checks
        failure_mode, failure_explanation, suggested_fix = _diagnose_failure(report, failed_checks)
        score = _score_report(report)
        decision = _decide(report, overall_passed, score, failed_checks)
        passed_checks = [check.metric for check in checks if check.passed]
        failed_check_names = [check.metric for check in failed_checks]
        reason_codes = _build_reason_codes(report, failure_mode, failed_checks)

        tags = [f"island:{report.island}"]
        tags.append("passed" if overall_passed else f"failed:{failure_mode or 'unknown'}")
        tags.append(f"decision:{decision}")

        if overall_passed:
            summary = f"{report.factor_id} passed deterministic checks with score {score:.2f}."
        else:
            summary = failure_explanation

        return CriticVerdict(
            report_id=report.report_id,
            factor_id=report.factor_id,
            note_id=report.note_id,
            overall_passed=overall_passed,
            decision=decision,
            score=score,
            checks=checks,
            passed_checks=passed_checks,
            failed_checks=failed_check_names,
            failure_mode=failure_mode,
            failure_explanation=failure_explanation,
            suggested_fix=suggested_fix,
            summary=summary,
            reason_codes=reason_codes,
            register_to_pool=True,
            pool_tags=tags,
        )


class RiskAuditor:
    """Minimal deterministic risk audit used to keep the current orchestrator runnable."""

    def __init__(self, factor_pool: FactorPool | None = None):
        self.factor_pool = factor_pool

    async def audit(self, report: BacktestReport) -> RiskAuditReport:
        correlation_flags: list[CorrelationFlag] = []

        if self.factor_pool is not None:
            for existing in self.factor_pool.get_passed_factors(island=report.island, limit=20):
                if existing.get("formula") == report.formula and existing.get("formula") != "":
                    correlation_flags.append(
                        CorrelationFlag(
                            existing_factor_id=existing.get("factor_id", existing.get("id", "unknown")),
                            correlation=1.0,
                            flag_reason="too_similar",
                        )
                    )
                    break

        overfitting_score = 0.0
        if report.error_message:
            overfitting_score = 0.5
        elif report.metrics.turnover_rate > THRESHOLDS.max_turnover_rate:
            overfitting_score = min(
                1.0,
                report.metrics.turnover_rate / max(THRESHOLDS.max_turnover_rate, 1e-9) - 1.0,
            )

        overfitting_flag = overfitting_score > THRESHOLDS.max_overfitting_score
        recommendation = "manual_review" if overfitting_flag or correlation_flags else "clear"
        audit_notes = "存在潜在过拟合或高相似风险。" if recommendation == "manual_review" else "未发现显著风险。"

        return RiskAuditReport(
            factor_id=report.factor_id,
            overfitting_score=overfitting_score,
            overfitting_flag=overfitting_flag,
            correlation_flags=correlation_flags,
            recommendation=recommendation,
            audit_notes=audit_notes,
        )


class PortfolioManager:
    """Minimal deterministic portfolio allocator."""

    def __init__(self, factor_pool: FactorPool | None = None):
        self.factor_pool = factor_pool

    async def rebalance(self, state: AgentState) -> PortfolioAllocation:
        passed_ids = {
            verdict.factor_id
            for verdict in state.critic_verdicts
            if verdict.overall_passed
        }
        selected_reports = [
            report for report in state.backtest_reports
            if report.factor_id in passed_ids
        ]

        if not selected_reports:
            return PortfolioAllocation(
                allocation_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                factor_weights=[],
                expected_portfolio_sharpe=0.0,
                expected_portfolio_ic=0.0,
                diversification_score=0.0,
                total_factors=0,
                notes="No approved factors available for allocation.",
            )

        weight = 1.0 / len(selected_reports)
        factor_weights = [
            FactorWeight(
                factor_id=report.factor_id,
                island=report.island,
                weight=weight,
                rationale="Equal-weight deterministic MVP allocation.",
            )
            for report in selected_reports
        ]
        unique_islands = {report.island for report in selected_reports}

        return PortfolioAllocation(
            allocation_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            factor_weights=factor_weights,
            expected_portfolio_sharpe=sum(report.metrics.sharpe for report in selected_reports) / len(selected_reports),
            expected_portfolio_ic=sum(report.metrics.ic_mean for report in selected_reports) / len(selected_reports),
            diversification_score=len(unique_islands) / len(selected_reports),
            total_factors=len(selected_reports),
            notes="Equal-weight deterministic MVP allocation.",
        )


class ReportWriter:
    """Template-based CIO report writer for the deterministic MVP."""

    async def generate_cio_report(self, state: AgentState) -> CIOReport:
        allocation = state.portfolio_allocation or PortfolioAllocation(
            allocation_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            factor_weights=[],
            expected_portfolio_sharpe=0.0,
            expected_portfolio_ic=0.0,
            diversification_score=0.0,
            total_factors=0,
            notes="No allocation available.",
        )

        best_report = max(
            state.backtest_reports,
            key=lambda report: report.metrics.sharpe,
            default=None,
        )
        passed_verdicts = [verdict for verdict in state.critic_verdicts if verdict.overall_passed]
        failed_verdicts = [verdict for verdict in state.critic_verdicts if not verdict.overall_passed]

        highlights = []
        if best_report is not None:
            highlights.append(
                f"Best factor {best_report.factor_id} achieved Sharpe {best_report.metrics.sharpe:.2f}."
            )
        if allocation.total_factors:
            highlights.append(f"Portfolio now tracks {allocation.total_factors} approved factor(s).")

        risks = []
        for verdict in failed_verdicts[:3]:
            if verdict.failure_mode:
                risks.append(f"{verdict.factor_id}: {verdict.failure_mode}")

        markdown = self._render_markdown(state, allocation, best_report, passed_verdicts, failed_verdicts)

        return CIOReport(
            report_id=str(uuid.uuid4()),
            period=f"round-{state.current_round}",
            total_factors_tested=len(state.backtest_reports),
            new_factors_approved=len(passed_verdicts),
            best_new_factor=best_report.factor_id if best_report is not None else None,
            best_new_sharpe=best_report.metrics.sharpe if best_report is not None else None,
            current_portfolio=allocation,
            portfolio_change_summary=f"Approved {len(passed_verdicts)} new factor(s) in round {state.current_round}.",
            highlights=highlights,
            risks=risks,
            full_report_markdown=markdown,
            suggested_actions=["approve", "redirect:<island>", "stop"],
            requires_human_decision=True,
        )

    def _render_markdown(
        self,
        state: AgentState,
        allocation: PortfolioAllocation,
        best_report: BacktestReport | None,
        passed_verdicts: list[CriticVerdict],
        failed_verdicts: list[CriticVerdict],
    ) -> str:
        best_factor_id = best_report.factor_id if best_report is not None else "N/A"
        best_sharpe = f"{best_report.metrics.sharpe:.2f}" if best_report is not None else "N/A"
        best_formula = best_report.factor_spec.formula if best_report and best_report.factor_spec else (best_report.formula if best_report else "N/A")
        best_hypothesis = best_report.factor_spec.hypothesis if best_report and best_report.factor_spec else "N/A"
        best_rationale = best_report.factor_spec.economic_rationale if best_report and best_report.factor_spec else "N/A"
        lines = [
            f"# CIO Review: round-{state.current_round}",
            "",
            "## Summary",
            f"- Tested factors: {len(state.backtest_reports)}",
            f"- Approved factors: {len(passed_verdicts)}",
            f"- Best factor: {best_factor_id}",
            f"- Best Sharpe: {best_sharpe}",
            "",
            "## Best Factor",
            f"- Formula: {best_formula}",
            f"- Hypothesis: {best_hypothesis}",
            f"- Economic rationale: {best_rationale}",
            "",
            "## Portfolio",
            f"- Total factors: {allocation.total_factors}",
            f"- Expected portfolio Sharpe: {allocation.expected_portfolio_sharpe:.2f}",
            f"- Expected portfolio IC: {allocation.expected_portfolio_ic:.4f}",
            "",
            "## Failures",
        ]

        if failed_verdicts:
            for verdict in failed_verdicts:
                lines.append(
                    f"- {verdict.factor_id}: {verdict.failure_mode or 'unknown'} "
                    f"(decision={verdict.decision or 'n/a'}, score={verdict.score:.2f})"
                )
        else:
            lines.append("- None")

        lines.extend(["", "## Decisions"])
        for verdict in passed_verdicts[:5]:
            lines.append(
                f"- {verdict.factor_id}: decision={verdict.decision or 'n/a'}, "
                f"score={verdict.score:.2f}, reason_codes={','.join(verdict.reason_codes)}"
            )

        return "\n".join(lines)
