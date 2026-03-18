"""
Stage 5 merged tests: judgment + judgment_pool_writeback + stage45_golden_path.

Sources:
  - tests/test_judgment.py
  - tests/test_judgment_pool_writeback.py
  - tests/test_stage45_golden_path.py
"""
import asyncio
import json
import pytest

pytestmark = pytest.mark.unit

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.judgment import Critic, PortfolioManager, ReportWriter, RiskAuditor
from src.execution.coder import Coder
from src.execution.docker_runner import ExecutionResult
from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


# ─────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────
# From test_judgment.py
# ─────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────
# From test_judgment_pool_writeback.py
# ─────────────────────────────────────────────────────────

def _make_note_for_writeback(note_id: str, hypothesis: str = "测试假设") -> FactorResearchNote:
    return FactorResearchNote(
        note_id=note_id,
        island="momentum",
        iteration=1,
        hypothesis=hypothesis,
        economic_intuition="经济直觉",
        proposed_formula="$close",
        final_formula="$close",
        exploration_questions=[],
        risk_factors=[],
        market_context_date="2026-03-14",
        status="ready_for_backtest",
    )


def _make_report_for_writeback(note_id: str, sharpe: float = 3.0, passed: bool = True) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{note_id}",
        note_id=note_id,
        factor_id=note_id,
        island="momentum",
        formula="$close",
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.2,
            max_drawdown=0.1,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.6,
            turnover_rate=0.2,
        ),
        passed=passed,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=None,
    )


class _StubPoolWriteback:
    """记录所有 register_factor 调用。"""
    def __init__(self):
        self.calls: list[dict] = []

    def get_passed_factors(self, island=None, limit=20):
        return []

    def register_factor(self, report, verdict, risk_report, hypothesis: str = ""):
        self.calls.append({
            "report": report,
            "verdict": verdict,
            "risk_report": risk_report,
            "hypothesis": hypothesis,
        })


def test_judgment_node_passes_hypothesis_to_pool():
    from src.core.orchestrator import judgment_node

    note = _make_note_for_writeback("factor_001", hypothesis="资金流持续推动短期趋势延续")
    report = _make_report_for_writeback("factor_001", sharpe=3.0, passed=True)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPoolWriteback()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1, "应有一次 register_factor 调用"
    call = pool.calls[0]
    assert call["hypothesis"] == "资金流持续推动短期趋势延续", (
        f"hypothesis 应从 note 中传入，实际: {call['hypothesis']!r}"
    )


def test_judgment_node_calls_pool_when_register_to_pool_true():
    from src.core.orchestrator import judgment_node

    note = _make_note_for_writeback("factor_002")
    report = _make_report_for_writeback("factor_002", sharpe=3.0)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPoolWriteback()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1


def test_judgment_node_returns_verdicts_and_risk_reports():
    from src.core.orchestrator import judgment_node

    note = _make_note_for_writeback("factor_003")
    report = _make_report_for_writeback("factor_003", sharpe=3.0)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPoolWriteback()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        result = judgment_node(state)

    assert "critic_verdicts" in result
    assert "risk_audit_reports" in result
    assert len(result["critic_verdicts"]) == 1
    assert len(result["risk_audit_reports"]) == 1


def test_judgment_node_empty_reports_returns_empty():
    from src.core.orchestrator import judgment_node

    state = AgentState(
        current_round=1,
        approved_notes=[],
        backtest_reports=[],
        critic_verdicts=[],
    )

    with patch("src.core.orchestrator.get_factor_pool", return_value=_StubPoolWriteback()):
        result = judgment_node(state)

    assert result["critic_verdicts"] == []
    assert result["risk_audit_reports"] == []


# ─────────────────────────────────────────────────────────
# From test_stage45_golden_path.py
# ─────────────────────────────────────────────────────────

def _make_note_golden() -> FactorResearchNote:
    return FactorResearchNote(
        note_id="momentum_20260312_01",
        island="momentum",
        iteration=1,
        hypothesis="近20日价格动量在高流动性股票池中延续。",
        economic_intuition="资金持续流入会强化短期趋势。",
        proposed_formula="Ref($close, 20) / $close - 1",
        final_formula="Ref($close, 20) / $close - 1",
        exploration_questions=[],
        risk_factors=["市场风格切换"],
        market_context_date="2026-03-12",
        universe="csi300",
        backtest_start="2021-06-01",
        backtest_end="2023-12-31",
    )


def _make_exec_result_golden() -> ExecutionResult:
    stdout = "BACKTEST_RESULT_JSON:" + json.dumps(
        {
            "sharpe": 3.1,
            "annualized_return": 0.22,
            "max_drawdown": 0.12,
            "ic_mean": 0.04,
            "ic_std": 0.03,
            "icir": 0.65,
            "turnover_rate": 0.18,
            "error": None,
        }
    )
    return ExecutionResult(
        success=True,
        stdout=stdout,
        stderr="",
        returncode=0,
        duration_seconds=1.2,
    )


def test_stage45_golden_path_runs_end_to_end(tmp_path):
    note = _make_note_golden()
    pool = FactorPool(db_path=str(tmp_path / "pool"))
    exec_result = _make_exec_result_golden()

    with patch("src.execution.coder.DockerRunner.run_python", new=AsyncMock(return_value=exec_result)):
        report = asyncio.run(Coder().run_backtest(note))

    assert report.run_id is not None
    assert report.factor_id == note.note_id
    assert report.passed is True
    assert report.status == "success"
    assert report.execution_meta is not None
    assert report.factor_spec is not None
    assert report.artifacts is not None
    assert Path(report.artifacts.stdout_path).exists()
    assert Path(report.artifacts.stderr_path).exists()
    assert Path(report.artifacts.script_path).exists()

    verdict = asyncio.run(Critic().evaluate(report))
    assert verdict.overall_passed is True
    assert verdict.decision == "promote"
    assert verdict.factor_id == report.factor_id

    risk_report = asyncio.run(RiskAuditor(pool).audit(report))
    assert risk_report.factor_id == report.factor_id

    pool.register_factor(report=report, verdict=verdict, risk_report=risk_report, hypothesis=note.hypothesis)
    passed_factors = pool.get_passed_factors(island=note.island, limit=10)
    assert len(passed_factors) == 1
    assert passed_factors[0]["formula"] == report.formula

    allocation = asyncio.run(
        PortfolioManager(factor_pool=pool).rebalance(
            AgentState(
                current_round=1,
                backtest_reports=[report],
                critic_verdicts=[verdict],
                risk_audit_reports=[risk_report],
            )
        )
    )
    assert allocation.total_factors == 1

    state = AgentState(
        current_round=1,
        backtest_reports=[report],
        critic_verdicts=[verdict],
        risk_audit_reports=[risk_report],
        portfolio_allocation=allocation,
    )
    cio_report = asyncio.run(ReportWriter().generate_cio_report(state))
    assert "CIO Review" in cio_report.full_report_markdown
    assert report.factor_id in cio_report.full_report_markdown
    assert "decision=promote" in cio_report.full_report_markdown
