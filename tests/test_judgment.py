import asyncio

from src.agents.critic import Critic as CompatibilityCritic
from src.agents.judgment import Critic, PortfolioManager, ReportWriter, RiskAuditor
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.state import AgentState


def _make_report(
    factor_id: str = "momentum_20260309_01",
    sharpe: float = 3.0,
    ic_mean: float = 0.04,
    icir: float = 0.6,
    turnover_rate: float = 0.2,
    error_message: str | None = None,
) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{factor_id}",
        note_id=factor_id,
        factor_id=factor_id,
        island="momentum",
        formula="$close",
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.2,
            max_drawdown=0.1,
            ic_mean=ic_mean,
            ic_std=0.04,
            icir=icir,
            turnover_rate=turnover_rate,
        ),
        passed=error_message is None,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=error_message,
    )


def test_critic_passes_strong_report():
    report = _make_report()

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is True
    assert verdict.decision == "promote"
    assert verdict.note_id == report.note_id
    assert verdict.score > 0.8
    assert verdict.failure_mode is None
    assert "sharpe" in verdict.passed_checks
    assert verdict.reason_codes == []
    assert "passed" in verdict.pool_tags
    assert verdict.verdict_id


def test_critic_reports_execution_failure():
    report = _make_report(error_message="SyntaxError")

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is False
    assert verdict.decision == "retry"
    assert verdict.failure_mode == "execution_error"
    assert "EXECUTION_FAILED" in verdict.reason_codes
    assert verdict.register_to_pool is True


def test_critic_rejects_low_coverage():
    report = _make_report()
    report = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(update={"coverage": 0.2}),
            "passed": False,
        }
    )

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is False
    assert "coverage" in verdict.failed_checks
    assert "LOW_COVERAGE" in verdict.reason_codes


def test_legacy_critic_alias_matches_canonical_runtime():
    report = _make_report()

    canonical = asyncio.run(Critic().evaluate(report))
    compatibility = asyncio.run(CompatibilityCritic().evaluate(report))

    assert compatibility.decision == canonical.decision
    assert compatibility.score == canonical.score
    assert compatibility.reason_codes == canonical.reason_codes


class _StubPool:
    def __init__(self):
        self.registered: list[dict] = []

    def get_passed_factors(self, island: str | None = None, limit: int = 20):
        return []

    def register_factor(self, report, verdict, risk_report, hypothesis: str = ""):
        self.registered.append(
            {
                "report": report,
                "verdict": verdict,
                "risk_report": risk_report,
                "hypothesis": hypothesis,
            }
        )


def test_risk_auditor_and_writeback_contract():
    pool = _StubPool()
    report = _make_report()
    verdict = asyncio.run(Critic().evaluate(report))
    risk_report = asyncio.run(RiskAuditor(pool).audit(report))

    pool.register_factor(report=report, verdict=verdict, risk_report=risk_report, hypothesis="test")

    assert len(pool.registered) == 1
    assert pool.registered[0]["report"].factor_id == report.factor_id
    assert pool.registered[0]["verdict"].overall_passed is True
    assert pool.registered[0]["verdict"].decision == "promote"


def test_portfolio_manager_and_report_writer_generate_minimal_outputs():
    report = _make_report()
    verdict = asyncio.run(Critic().evaluate(report))
    state = AgentState(
        current_round=1,
        backtest_reports=[report],
        critic_verdicts=[verdict],
    )

    allocation = asyncio.run(PortfolioManager().rebalance(state))
    state = state.model_copy(update={"portfolio_allocation": allocation})
    cio_report = asyncio.run(ReportWriter().generate_cio_report(state))

    assert allocation.total_factors == 1
    assert cio_report.new_factors_approved == 1
    assert "CIO Review" in cio_report.full_report_markdown
    assert "decision=promote" in cio_report.full_report_markdown
    assert "## Best Factor" in cio_report.full_report_markdown
