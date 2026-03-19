"""Template-based CIO report writer for the deterministic MVP."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CIOReport, CriticVerdict, PortfolioAllocation
from src.schemas.state import AgentState


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

        passed_verdicts = [verdict for verdict in state.critic_verdicts if verdict.overall_passed]
        failed_verdicts = [verdict for verdict in state.critic_verdicts if not verdict.overall_passed]
        passed_factor_ids = {verdict.factor_id for verdict in passed_verdicts}
        best_report = max(
            (report for report in state.backtest_reports if report.factor_id in passed_factor_ids),
            key=lambda report: report.metrics.sharpe,
            default=None,
        )

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
