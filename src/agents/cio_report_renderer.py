"""
Compatibility Markdown renderer for single-factor CIO views.

Canonical Stage 5 report generation lives in `src.agents.judgment.ReportWriter`.
This renderer remains for focused tests and standalone report export.
"""
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict

class CIOReportRenderer:
    """
    确定性 Markdown 报告渲染器
    不调用 LLM，使用固定模板
    """

    @staticmethod
    def render(
        report: BacktestReport,
        verdict: CriticVerdict,
        factor_pool_record_id: str,
    ) -> str:
        """
        渲染最小化 CIO 报告

        Returns:
            Markdown 格式的报告文本
        """
        lines = []

        # 标题
        lines.append(f"# CIO Review: {factor_pool_record_id}")
        lines.append("")

        # Factor Summary
        lines.append("## Factor Summary")
        lines.append(f"- Note ID: {report.note_id}")
        lines.append(f"- Island ID: {report.island_id}")
        lines.append(f"- Formula: `{report.factor_spec.formula}`")
        lines.append(f"- Hypothesis: {report.factor_spec.hypothesis}")
        lines.append(f"- Economic rationale: {report.factor_spec.economic_rationale}")
        lines.append("")

        # Backtest Context
        lines.append("## Backtest Context")
        lines.append(f"- Universe: {report.execution_meta.universe}")
        lines.append(f"- Benchmark: {report.execution_meta.benchmark}")
        lines.append(f"- Date range: {report.execution_meta.start_date} to {report.execution_meta.end_date}")
        lines.append(f"- Engine/template version: {report.execution_meta.engine} {report.execution_meta.template_version}")
        lines.append(f"- Runtime: {report.execution_meta.runtime_seconds:.2f}s")
        lines.append("")

        # Core Metrics
        lines.append("## Core Metrics")
        m = report.metrics
        lines.append(f"- Sharpe: {m.sharpe:.4f}" if m.sharpe is not None else "- Sharpe: N/A")
        lines.append(f"- Annual return: {m.annual_return:.4f}" if m.annual_return is not None else "- Annual return: N/A")
        lines.append(f"- Max drawdown: {m.max_drawdown:.4f}" if m.max_drawdown is not None else "- Max drawdown: N/A")
        lines.append(f"- IC mean: {m.ic_mean:.4f}" if m.ic_mean is not None else "- IC mean: N/A")
        lines.append(f"- ICIR: {m.icir:.4f}" if m.icir is not None else "- ICIR: N/A")
        lines.append(f"- Turnover: {m.turnover:.4f}" if m.turnover is not None else "- Turnover: N/A")
        lines.append(f"- Coverage: {m.coverage:.4f}" if m.coverage is not None else "- Coverage: N/A")
        lines.append("")

        # Verdict
        lines.append("## Verdict")
        lines.append(f"- Decision: **{verdict.decision.upper()}**")
        lines.append(f"- Score: {verdict.score:.3f}")
        lines.append(f"- Passed checks: {', '.join(verdict.passed_checks) if verdict.passed_checks else 'None'}")
        lines.append(f"- Failed checks: {', '.join(verdict.failed_checks) if verdict.failed_checks else 'None'}")
        lines.append(f"- Reason codes: {', '.join(verdict.reason_codes) if verdict.reason_codes else 'None'}")
        lines.append(f"- Summary: {verdict.summary}")
        lines.append("")

        # Artifact References
        lines.append("## Artifact References")
        lines.append(f"- stdout: `{report.artifacts.stdout_path}`")
        lines.append(f"- stderr: `{report.artifacts.stderr_path}`")
        lines.append(f"- script: `{report.artifacts.script_path}`")
        if report.artifacts.raw_result_path:
            lines.append(f"- raw result: `{report.artifacts.raw_result_path}`")
        if report.artifacts.equity_curve_path:
            lines.append(f"- equity curve: `{report.artifacts.equity_curve_path}`")
        lines.append("")

        return "\n".join(lines)
