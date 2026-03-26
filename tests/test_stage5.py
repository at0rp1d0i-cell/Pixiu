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

from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.agents.judgment import Critic, PortfolioManager, ReportWriter, RiskAuditor
from src.execution.coder import Coder
from src.execution.docker_runner import ExecutionResult
from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport, ThresholdCheck
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState

pytestmark = pytest.mark.unit


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
    oos_passed: bool | None = None,
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
        execution_succeeded=error_message is None,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=error_message,
        oos_passed=oos_passed,
    )


# ─────────────────────────────────────────────────────────
# From test_judgment.py
# ─────────────────────────────────────────────────────────

def test_critic_passes_strong_report():
    report = _make_report()

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is True
    assert verdict.decision == "candidate"
    assert verdict.note_id == report.note_id
    assert verdict.score > 0.8
    assert verdict.failure_mode is None
    assert "sharpe" in verdict.passed_checks
    assert verdict.reason_codes == []
    assert "passed" in verdict.pool_tags
    assert verdict.verdict_id


def test_critic_promotes_oos_passed_report():
    report = _make_report(oos_passed=True)

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is True
    assert verdict.decision == "promote"
    assert "decision:promote" in verdict.pool_tags


def test_critic_archives_oos_failed_report():
    report = _make_report(oos_passed=False)

    verdict = asyncio.run(Critic().evaluate(report))

    assert verdict.overall_passed is True
    assert verdict.decision == "archive"
    assert "decision:archive" in verdict.pool_tags
    assert "OOS_FAILED" in verdict.reason_codes
    assert "out-of-sample" in verdict.summary.lower()


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
    assert pool.registered[0]["verdict"].decision == "candidate"


def test_portfolio_manager_and_report_writer_generate_minimal_outputs():
    report = _make_report(oos_passed=True)
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


def test_report_writer_surfaces_candidate_without_approval():
    report = _make_report()
    verdict = asyncio.run(Critic().evaluate(report))
    state = AgentState(
        current_round=1,
        backtest_reports=[report],
        critic_verdicts=[verdict],
    )

    allocation = asyncio.run(PortfolioManager().rebalance(state))
    cio_report = asyncio.run(
        ReportWriter().generate_cio_report(
            state.model_copy(update={"portfolio_allocation": allocation})
        )
    )

    assert verdict.decision == "candidate"
    assert allocation.total_factors == 0
    assert cio_report.new_factors_approved == 0
    assert "Candidate factors: 1" in cio_report.full_report_markdown
    assert "pending OOS validation" in cio_report.full_report_markdown


def test_report_writer_surfaces_oos_archived_factor_details():
    report = _make_report(factor_id="momentum_oos_failed", sharpe=2.8, oos_passed=False)
    report = report.model_copy(
        update={
            "metrics_scope": "discovery",
            "oos_degradation": 1.1,
        }
    )
    verdict = asyncio.run(Critic().evaluate(report))
    state = AgentState(
        current_round=3,
        backtest_reports=[report],
        critic_verdicts=[verdict],
    )

    allocation = asyncio.run(PortfolioManager().rebalance(state))
    cio_report = asyncio.run(
        ReportWriter().generate_cio_report(
            state.model_copy(update={"portfolio_allocation": allocation})
        )
    )

    assert verdict.decision == "archive"
    assert cio_report.new_factors_approved == 0
    assert "failed OOS validation" in cio_report.full_report_markdown
    assert "oos_passed=False" in cio_report.full_report_markdown
    assert "oos_degradation=1.1" in cio_report.full_report_markdown


def test_report_writer_ignores_failed_verdicts_when_picking_best_factor():
    passed_report = _make_report(factor_id="momentum_passed", sharpe=2.8, oos_passed=True)
    failed_report = _make_report(factor_id="momentum_failed", sharpe=6.0)

    passed_verdict = asyncio.run(Critic().evaluate(passed_report))
    failed_verdict = passed_verdict.model_copy(
        update={
            "report_id": failed_report.report_id,
            "factor_id": failed_report.factor_id,
            "note_id": failed_report.note_id,
            "overall_passed": False,
            "decision": "reject",
            "score": 0.1,
            "failure_mode": passed_verdict.failure_mode,
            "failure_explanation": "synthetic failure",
            "reason_codes": ["LOW_SHARPE"],
        }
    )

    state = AgentState(
        current_round=1,
        backtest_reports=[passed_report, failed_report],
        critic_verdicts=[passed_verdict, failed_verdict],
    )

    cio_report = asyncio.run(ReportWriter().generate_cio_report(state))

    assert cio_report.best_new_factor == passed_report.factor_id
    assert cio_report.best_new_sharpe == passed_report.metrics.sharpe


def test_report_writer_only_counts_promoted_factors_as_approved():
    report = _make_report(factor_id="momentum_archived", sharpe=2.9, oos_passed=True)
    verdict = asyncio.run(Critic().evaluate(report)).model_copy(
        update={
            "decision": "archive",
            "score": 0.6,
        }
    )
    state = AgentState(
        current_round=2,
        backtest_reports=[report],
        critic_verdicts=[verdict],
    )

    allocation = asyncio.run(PortfolioManager().rebalance(state))
    cio_report = asyncio.run(ReportWriter().generate_cio_report(state.model_copy(update={
        "portfolio_allocation": allocation,
    })))

    assert allocation.total_factors == 0
    assert cio_report.new_factors_approved == 0
    assert "Deterministic passes: 1" in cio_report.full_report_markdown


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


def _make_report_for_writeback(
    note_id: str,
    sharpe: float = 3.0,
    passed: bool = True,
    error_message: str | None = None,
) -> BacktestReport:
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
        execution_succeeded=error_message is None,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=error_message,
    )


class _StubPoolWriteback:
    """记录所有 register_factor 调用。"""
    def __init__(self):
        self.calls: list[dict] = []
        self.constraints: list[object] = []

    def get_passed_factors(self, island=None, limit=20):
        return []

    def register_factor(self, report, verdict, risk_report, hypothesis: str = "", note=None):
        self.calls.append({
            "report": report,
            "verdict": verdict,
            "risk_report": risk_report,
            "hypothesis": hypothesis,
            "note": note,
        })

    def register_constraint(self, constraint):
        self.constraints.append(constraint)


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

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1, "应有一次 register_factor 调用"
    call = pool.calls[0]
    assert call["hypothesis"] == "资金流持续推动短期趋势延续", (
        f"hypothesis 应从 note 中传入，实际: {call['hypothesis']!r}"
    )
    assert call["note"] is note


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

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
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

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
        result = judgment_node(state)

    assert "critic_verdicts" in result
    assert "risk_audit_reports" in result
    assert len(result["critic_verdicts"]) == 1
    assert len(result["risk_audit_reports"]) == 1


def test_judgment_node_parallel_exception_does_not_drop_other_results():
    from src.core.orchestrator import judgment_node

    ok_note = _make_note_for_writeback("factor_ok")
    boom_note = _make_note_for_writeback("factor_boom")
    ok_report = _make_report_for_writeback("factor_ok", sharpe=3.0)
    boom_report = _make_report_for_writeback("factor_boom", sharpe=2.5)
    state = AgentState(
        current_round=1,
        approved_notes=[ok_note, boom_note],
        backtest_reports=[ok_report, boom_report],
        critic_verdicts=[],
    )
    pool = _StubPoolWriteback()

    async def _critic_side_effect(report, regime=None):
        if report.factor_id == "factor_boom":
            raise RuntimeError("critic boom")
        return CriticVerdict(
            report_id=report.report_id,
            factor_id=report.factor_id,
            note_id=report.note_id,
            overall_passed=True,
            decision="promote",
            score=0.95,
            checks=[],
            passed_checks=["sharpe"],
            failed_checks=[],
            failure_mode=None,
            failure_explanation=None,
            suggested_fix=None,
            summary="ok",
            reason_codes=[],
            regime_at_judgment=regime,
            register_to_pool=True,
            pool_tags=["passed"],
        )

    async def _audit_side_effect(report):
        return RiskAuditReport(
            factor_id=report.factor_id,
            overfitting_score=0.0,
            overfitting_flag=False,
            recommendation="keep",
            audit_notes="ok",
        )

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"), \
         patch("src.agents.judgment.Critic.evaluate", new=AsyncMock(side_effect=_critic_side_effect)), \
         patch("src.agents.judgment.RiskAuditor.audit", new=AsyncMock(side_effect=_audit_side_effect)):
        result = judgment_node(state)

    assert [verdict.factor_id for verdict in result["critic_verdicts"]] == ["factor_ok"]
    assert [risk.factor_id for risk in result["risk_audit_reports"]] == ["factor_ok"]
    assert len(pool.calls) == 1
    assert pool.calls[0]["report"].factor_id == "factor_ok"
    assert pool.calls[0]["note"] is ok_note


def test_judgment_node_records_execution_error_constraint_as_warning():
    from src.core.orchestrator import judgment_node
    from src.schemas.failure_constraint import FailureMode

    note = _make_note_for_writeback("factor_003", hypothesis="执行错误不应升级成硬约束")
    report = _make_report_for_writeback(
        "factor_003",
        sharpe=0.0,
        passed=False,
        error_message="SyntaxError: bad formula",
    )
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPoolWriteback()

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1
    assert len(pool.constraints) == 1
    constraint = pool.constraints[0]
    assert constraint.failure_mode == FailureMode.EXECUTION_ERROR
    assert constraint.severity == "warning"
    assert "execution error" in constraint.constraint_rule.lower()


def test_judgment_node_empty_reports_returns_empty():
    from src.core.orchestrator import judgment_node

    state = AgentState(
        current_round=1,
        approved_notes=[],
        backtest_reports=[],
        critic_verdicts=[],
    )

    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=_StubPoolWriteback()):
        result = judgment_node(state)

    assert result["critic_verdicts"] == []
    assert result["risk_audit_reports"] == []


def test_report_node_failure_does_not_request_human_approval():
    from src.core.orchestrator import report_node

    state = AgentState(current_round=1)

    with patch("src.agents.judgment.ReportWriter.generate_cio_report", new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("src.core.orchestrator.control_plane._update_run_record"), \
         patch("src.core.orchestrator.control_plane._persist_cio_report"), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
        result = report_node(state)

    assert result["error_stage"] == "report"
    assert result["awaiting_human_approval"] is False


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
            "coverage": 0.95,
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

    report = report.model_copy(update={"oos_passed": True})
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


# ─────────────────────────────────────────────────────────
# TestRiskAuditor
# ─────────────────────────────────────────────────────────

class TestRiskAuditor:
    def test_audit_passed_report_returns_no_flags(self):
        report = _make_report()
        result = asyncio.run(RiskAuditor().audit(report))

        assert result.factor_id == report.factor_id
        assert result.correlation_flags == []
        assert result.recommendation == "clear"
        assert result.overfitting_flag is False

    def test_audit_low_ic_report_flags_overfitting(self):
        # High turnover triggers overfitting score > threshold (0.40)
        # turnover_rate=2.0 → overfitting_score = 2.0/0.5 - 1 = 3.0, clamped to 1.0
        report = _make_report(turnover_rate=2.0)
        result = asyncio.run(RiskAuditor().audit(report))

        assert result.overfitting_flag is True
        assert result.overfitting_score > 0.40
        assert result.recommendation == "manual_review"

    def test_audit_execution_error_sets_penalty_score(self):
        report = _make_report(error_message="RuntimeError: division by zero")
        result = asyncio.run(RiskAuditor().audit(report))

        assert result.overfitting_score == 0.5
        assert result.factor_id == report.factor_id


# ─────────────────────────────────────────────────────────
# TestConstraintExtractor
# ─────────────────────────────────────────────────────────

class TestConstraintExtractor:
    def _make_failed_verdict(self) -> CriticVerdict:
        from src.schemas.failure_constraint import FailureMode

        return CriticVerdict(
            report_id="report-001",
            factor_id="momentum_20260309_01",
            note_id="momentum_20260309_01",
            overall_passed=False,
            decision="reject",
            score=0.1,
            failure_mode=FailureMode.LOW_SHARPE,
            failure_explanation="Sharpe too low",
            suggested_fix="Try longer window",
            checks=[
                ThresholdCheck(metric="sharpe", value=0.5, threshold=2.67, passed=False)
            ],
            failed_checks=["sharpe"],
            register_to_pool=True,
        )

    def _make_passed_verdict(self) -> CriticVerdict:
        return CriticVerdict(
            report_id="report-002",
            factor_id="momentum_20260309_02",
            note_id="momentum_20260309_02",
            overall_passed=True,
            decision="promote",
            score=0.9,
            checks=[
                ThresholdCheck(metric="sharpe", value=3.5, threshold=2.67, passed=True)
            ],
            passed_checks=["sharpe"],
            register_to_pool=True,
        )

    def _make_note(self, note_id: str = "momentum_20260309_01") -> FactorResearchNote:
        return FactorResearchNote(
            note_id=note_id,
            island="momentum",
            iteration=1,
            hypothesis="动量假设",
            economic_intuition="资金流",
            proposed_formula="Ref($close, 20) / $close - 1",
            final_formula="Ref($close, 20) / $close - 1",
            exploration_questions=[],
            risk_factors=[],
            market_context_date="2026-03-09",
        )

    def test_extract_returns_constraint_on_failed_verdict(self):
        from src.agents.judgment.constraint_extractor import ConstraintExtractor

        verdict = self._make_failed_verdict()
        note = self._make_note()
        result = ConstraintExtractor().extract(verdict, note)

        assert result is not None
        assert result.source_note_id == note.note_id
        assert result.source_verdict_id == verdict.verdict_id

    def test_extract_returns_none_on_passed_verdict(self):
        from src.agents.judgment.constraint_extractor import ConstraintExtractor

        verdict = self._make_passed_verdict()
        note = self._make_note(note_id="momentum_20260309_02")
        result = ConstraintExtractor().extract(verdict, note)

        assert result is None

    def test_extract_sets_correct_island_and_failure_mode(self):
        from src.agents.judgment.constraint_extractor import ConstraintExtractor
        from src.schemas.failure_constraint import FailureMode

        verdict = self._make_failed_verdict()
        note = self._make_note()
        result = ConstraintExtractor().extract(verdict, note)

        assert result is not None
        assert result.island == "momentum"
        assert result.failure_mode == FailureMode.LOW_SHARPE


# ─────────────────────────────────────────────────────────
# TestScoring
# ─────────────────────────────────────────────────────────

class TestScoring:
    def test_decide_candidates_without_oos(self):
        from src.agents.judgment._scoring import _decide

        report = _make_report(sharpe=3.0)
        result = _decide(report, overall_passed=True, score=0.9, failed_checks=[])

        assert result == "candidate"

    def test_decide_promotes_high_score_with_oos(self):
        from src.agents.judgment._scoring import _decide

        report = _make_report(sharpe=3.0, oos_passed=True)
        result = _decide(report, overall_passed=True, score=0.9, failed_checks=[])

        assert result == "promote"

    def test_decide_rejects_low_score(self):
        from src.agents.judgment._scoring import _decide

        report = _make_report(sharpe=-0.5)
        failed = [ThresholdCheck(metric="sharpe", value=-0.5, threshold=2.67, passed=False)]
        result = _decide(report, overall_passed=False, score=0.1, failed_checks=failed)

        assert result == "reject"

    def test_normalize_sharpe_clamps_to_zero_one(self):
        from src.agents.judgment._scoring import _normalize_positive

        # Value well above threshold → clamped to 1.0
        assert _normalize_positive(10.0, 2.67) == 1.0
        # Zero value → 0.0
        assert _normalize_positive(0.0, 2.67) == 0.0
        # Exactly at threshold → 1.0
        assert _normalize_positive(2.67, 2.67) == 1.0
        # Half of threshold → 0.5
        assert abs(_normalize_positive(1.335, 2.67) - 0.5) < 1e-9
