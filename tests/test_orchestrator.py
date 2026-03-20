"""
Orchestrator tests: routing logic + Stage 4b execution path.

Sources:
  - tests/test_orchestrator_routing.py
  - tests/test_orchestrator_stage4b.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.orchestrator import (
    NODE_LOOP_CONTROL,
    NODE_REPORT,
    REPORT_EVERY_N_ROUNDS,
    build_graph,
    coder_node,
    human_gate_node,
    loop_control_node,
    route_after_portfolio,
)
import src.core.orchestrator as orchestrator
from src.control_plane.state_store import StateStore
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.failure_constraint import FailureMode
from src.schemas.judgment import CriticVerdict, ThresholdCheck
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────

def _make_state(
    current_round: int = 1,
    backtest_reports: list | None = None,
    critic_verdicts: list | None = None,
) -> AgentState:
    return AgentState(
        current_round=current_round,
        backtest_reports=backtest_reports or [],
        critic_verdicts=critic_verdicts or [],
    )


def _make_report(sharpe: float, passed: bool = True) -> BacktestReport:
    return BacktestReport(
        report_id="r1",
        note_id="n1",
        factor_id="f1",
        island="momentum",
        formula="$close",
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.1,
            max_drawdown=0.1,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.5,
            turnover_rate=0.2,
        ),
        passed=passed,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
    )


def _make_verdict(overall_passed: bool) -> CriticVerdict:
    return CriticVerdict(
        report_id="r1",
        factor_id="f1",
        note_id="n1",
        overall_passed=overall_passed,
        decision="promote" if overall_passed else "archive",
        score=0.9 if overall_passed else 0.3,
        checks=[],
        register_to_pool=True,
        pool_tags=[],
        reason_codes=[],
    )


def _make_note(note_id: str) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=note_id,
        island="momentum",
        iteration=1,
        hypothesis="h",
        economic_intuition="e",
        proposed_formula="$close",
        final_formula="$close",
        exploration_questions=[],
        risk_factors=[],
        market_context_date="2026-03-09",
        status="ready_for_backtest",
    )


def _make_coder_report(note: FactorResearchNote) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{note.note_id}",
        note_id=note.note_id,
        factor_id=note.note_id,
        island=note.island,
        formula=note.final_formula or note.proposed_formula,
        metrics=BacktestMetrics(
            sharpe=1.0,
            annualized_return=0.1,
            max_drawdown=0.2,
            ic_mean=0.01,
            ic_std=0.02,
            icir=0.5,
            turnover_rate=0.3,
        ),
        passed=True,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=None,
    )


# ─────────────────────────────────────────────────────────
# From test_orchestrator_routing.py
# ─────────────────────────────────────────────────────────

class TestRouteAfterPortfolio:
    def test_round_zero_returns_loop_control(self):
        """第 0 轮不应触发报告（即使 0 % N == 0）。"""
        state = _make_state(current_round=0)
        result = route_after_portfolio(state)
        assert result == NODE_LOOP_CONTROL

    def test_triggers_report_at_n_rounds(self):
        """current_round == REPORT_EVERY_N_ROUNDS 时应触发报告。"""
        state = _make_state(current_round=REPORT_EVERY_N_ROUNDS)
        result = route_after_portfolio(state)
        assert result == NODE_REPORT

    def test_triggers_report_at_multiple_of_n(self):
        """current_round == 2 * REPORT_EVERY_N_ROUNDS 时应触发报告。"""
        state = _make_state(current_round=REPORT_EVERY_N_ROUNDS * 2)
        result = route_after_portfolio(state)
        assert result == NODE_REPORT

    def test_no_report_between_n_rounds(self):
        """非 N 的整数倍且无 breakthrough 时返回 loop_control。"""
        state = _make_state(current_round=3)
        result = route_after_portfolio(state)
        assert result == NODE_LOOP_CONTROL

    def test_triggers_on_breakthrough(self):
        """有超越基线 10% 的因子时立即触发报告。"""
        from src.schemas.thresholds import THRESHOLDS
        high_sharpe = THRESHOLDS.min_sharpe * 1.2
        state = _make_state(
            current_round=3,
            backtest_reports=[_make_report(sharpe=high_sharpe, passed=True)],
        )
        result = route_after_portfolio(state)
        assert result == NODE_REPORT

    def test_no_trigger_for_failed_report(self):
        """passed=False 的高 Sharpe 报告不应触发 breakthrough。"""
        from src.schemas.thresholds import THRESHOLDS
        high_sharpe = THRESHOLDS.min_sharpe * 1.2
        state = _make_state(
            current_round=3,
            backtest_reports=[_make_report(sharpe=high_sharpe, passed=False)],
        )
        result = route_after_portfolio(state)
        assert result == NODE_LOOP_CONTROL


def test_graph_routes_report_to_human_gate():
    graph = build_graph()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert ("report", "human_gate") in edges


class TestLoopControlNode:
    def test_increments_round(self):
        """current_round 应递增。"""
        state = _make_state(current_round=3)
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_get_sched.return_value = MagicMock()
            result = loop_control_node(state)
        assert result["current_round"] == 4

    def test_clears_temporary_fields(self):
        """临时字段应被清空。"""
        note = FactorResearchNote(
            note_id="n1",
            island="momentum",
            iteration=1,
            hypothesis="h",
            economic_intuition="e",
            proposed_formula="$close",
            final_formula="$close",
            exploration_questions=[],
            risk_factors=[],
            market_context_date="2026-03-14",
        )
        state = _make_state(current_round=1)
        state = state.model_copy(update={
            "research_notes": [note],
            "approved_notes": [note],
            "prefilter_diagnostics": {"input_count": 1, "approved_count": 1},
            "backtest_reports": [_make_report(2.0)],
            "critic_verdicts": [_make_verdict(True)],
        })
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_get_sched.return_value = MagicMock()
            result = loop_control_node(state)

        assert result["research_notes"] == []
        assert result["approved_notes"] == []
        assert result["prefilter_diagnostics"] == {}
        assert result["backtest_reports"] == []
        assert result["critic_verdicts"] == []
        assert result["filtered_count"] == 0
        assert result["awaiting_human_approval"] is False
        assert result["human_decision"] is None
        assert result["last_error"] is None

    def test_calls_on_epoch_done_when_verdict_passes(self):
        """有通过因子时应调用 on_epoch_done。"""
        state = _make_state(
            current_round=2,
            backtest_reports=[_make_report(3.0, passed=True)],
            critic_verdicts=[_make_verdict(True)],
        )
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_sched = MagicMock()
            mock_get_sched.return_value = mock_sched
            loop_control_node(state)

        mock_sched.on_epoch_done.assert_called()

    def test_calls_on_epoch_done_even_when_no_verdict_passes(self):
        """即使没有通过因子，on_epoch_done 也应被调用（修复 Bug 3）。"""
        state = _make_state(
            current_round=2,
            backtest_reports=[_make_report(0.5, passed=False)],
            critic_verdicts=[_make_verdict(False)],
        )
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_sched = MagicMock()
            mock_get_sched.return_value = mock_sched
            loop_control_node(state)

        mock_sched.on_epoch_done.assert_called_once()


def test_human_gate_consumes_control_plane_decision(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="evolve")
    monkeypatch.setattr(orchestrator, "get_state_store", lambda: store)
    monkeypatch.setattr(orchestrator, "_current_run_id", run.run_id)

    from src.schemas.control_plane import HumanDecisionRecord

    store.append_human_decision(HumanDecisionRecord(run_id=run.run_id, action="approve"))

    result = human_gate_node(AgentState(current_round=3, awaiting_human_approval=True))

    assert result["human_decision"] == "approve"
    assert result["awaiting_human_approval"] is False
    assert (
        orchestrator.route_after_human(
            AgentState(
                current_round=3,
                human_decision=result["human_decision"],
            )
        )
        == orchestrator.NODE_LOOP_CONTROL
    )
    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.status == "running"
    assert latest_run.current_stage == orchestrator.NODE_HUMAN_GATE
    snapshot = store.get_snapshot(run.run_id)
    assert snapshot is not None
    assert snapshot.awaiting_human_approval is False
    assert store.pop_latest_human_decision(run.run_id) is None


# ─────────────────────────────────────────────────────────
# From test_orchestrator_stage4b.py
# ─────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────
# ExperimentLogger snapshot integration: loop_control_node writes JSON
# ─────────────────────────────────────────────────────────

class TestLoopControlSnapshotWritten:
    def test_snapshot_json_created_after_loop_control(self, tmp_path):
        """loop_control_node 正常运行后 data/experiment_runs/ 下应产生 JSON 快照。"""
        import src.core.experiment_logger as _exp_mod
        from src.core.experiment_logger import ExperimentLogger

        # 用 tmp_path 隔离实验目录，覆盖单例
        run_id = "test_run_snapshot"
        test_logger = ExperimentLogger(run_id=run_id, runs_dir=tmp_path)
        _exp_mod._logger_instance = test_logger

        try:
            failed_report = _make_report(sharpe=0.5, passed=False).model_copy(update={
                "factor_id": "failing_factor",
                "note_id": "note_fail",
                "status": "success",
            })
            failed_verdict = CriticVerdict(
                report_id=failed_report.report_id,
                factor_id=failed_report.factor_id,
                note_id=failed_report.note_id,
                overall_passed=False,
                decision="archive",
                score=0.2,
                checks=[
                    ThresholdCheck(metric="sharpe", value=0.5, threshold=2.67, passed=False),
                    ThresholdCheck(metric="ic_mean", value=0.01, threshold=0.02, passed=False),
                ],
                failed_checks=["sharpe", "ic_mean"],
                failure_mode=FailureMode.LOW_SHARPE,
                failure_explanation="Sharpe 过低",
                suggested_fix="延长窗口",
                register_to_pool=True,
                pool_tags=[],
                reason_codes=["LOW_SHARPE"],
            )
            state = _make_state(
                current_round=5,
                backtest_reports=[failed_report],
                critic_verdicts=[failed_verdict],
            ).model_copy(update={
                "prefilter_diagnostics": {
                    "input_count": 12,
                    "approved_count": 3,
                    "rejection_counts_by_filter": {"validator": 4, "novelty": 2, "regime_filter": 3},
                    "sample_rejections": [
                        {"note_id": "note_1", "filter": "validator", "reason": "future ref"},
                        {"note_id": "note_2", "filter": "novelty", "reason": "duplicate"},
                    ],
                }
            })
            with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
                mock_get_sched.return_value = MagicMock()
                with patch("src.factor_pool.pool.get_factor_pool") as mock_pool:
                    mock_pool.return_value = MagicMock(
                        get_passed_factors=MagicMock(return_value=[])
                    )
                    loop_control_node(state)

            # round_005.json should have been written
            snapshot_path = tmp_path / run_id / "round_005.json"
            assert snapshot_path.exists(), f"快照文件不存在: {snapshot_path}"

            import json as _json
            data = _json.loads(snapshot_path.read_text(encoding="utf-8"))
            assert data["round"] == 5
            assert "timestamp" in data
            assert "subspace_generated" in data
            assert "verdicts" in data
            assert data["prefilter"]["input_count"] == 12
            assert data["prefilter"]["rejection_counts_by_filter"]["validator"] == 4
            assert data["execution"]["backtest_reports_count"] == 1
            assert data["execution"]["execution_error_count"] == 0
            assert data["execution"]["executed_factor_ids_sample"] == ["failing_factor"]
            assert data["judgment"]["verdict_counts_by_decision"]["archive"] == 1
            assert data["judgment"]["failure_mode_counts"]["low_sharpe"] == 1
            assert data["judgment"]["failed_check_counts"]["sharpe"] == 1
            assert data["judgment"]["sample_failures"][0]["factor_id"] == "failing_factor"
            assert set(data["scheduler_weights"]) == {
                "factor_algebra",
                "symbolic_mutation",
                "cross_market",
                "narrative_mining",
            }
            assert sum(data["scheduler_weights"].values()) == pytest.approx(1.0)
        finally:
            # 恢复单例，避免污染其他测试
            _exp_mod._logger_instance = None

    def test_snapshot_excludes_execution_error_from_failed_check_histogram(self, tmp_path):
        """execution_error 不应同时污染指标型 failed_check 统计。"""
        import src.core.experiment_logger as _exp_mod
        from src.core.experiment_logger import ExperimentLogger

        run_id = "test_run_exec_error_snapshot"
        test_logger = ExperimentLogger(run_id=run_id, runs_dir=tmp_path)
        _exp_mod._logger_instance = test_logger

        try:
            failed_report = _make_report(sharpe=0.0, passed=False).model_copy(update={
                "factor_id": "exec_error_factor",
                "note_id": "note_exec_error",
                "status": "failed",
                "error_message": "SyntaxError in backtest script",
            })
            failed_verdict = CriticVerdict(
                report_id=failed_report.report_id,
                factor_id=failed_report.factor_id,
                note_id=failed_report.note_id,
                overall_passed=False,
                decision="retry",
                score=0.0,
                checks=[
                    ThresholdCheck(metric="sharpe", value=0.0, threshold=2.67, passed=False),
                    ThresholdCheck(metric="ic_mean", value=0.0, threshold=0.02, passed=False),
                ],
                failed_checks=["sharpe", "ic_mean"],
                failure_mode=FailureMode.EXECUTION_ERROR,
                failure_explanation="回测执行失败",
                suggested_fix="检查脚本",
                register_to_pool=True,
                pool_tags=[],
                reason_codes=["EXECUTION_FAILED"],
            )
            state = _make_state(
                current_round=6,
                backtest_reports=[failed_report],
                critic_verdicts=[failed_verdict],
            )

            with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
                mock_get_sched.return_value = MagicMock()
                with patch("src.factor_pool.pool.get_factor_pool") as mock_pool:
                    mock_pool.return_value = MagicMock(
                        get_passed_factors=MagicMock(return_value=[])
                    )
                    loop_control_node(state)

            snapshot_path = tmp_path / run_id / "round_006.json"
            import json as _json
            data = _json.loads(snapshot_path.read_text(encoding="utf-8"))
            assert data["judgment"]["failure_mode_counts"]["execution_error"] == 1
            assert data["judgment"]["failed_check_counts"] == {}
        finally:
            _exp_mod._logger_instance = None


def test_orchestrator_stage4b_uses_execution_coder_path():
    note = _make_note("momentum_20260309_01")
    state = AgentState(approved_notes=[note], backtest_reports=[])
    expected_report = _make_coder_report(note)

    with patch("src.execution.coder.Coder") as mock_coder_cls:
        mock_coder = mock_coder_cls.return_value
        mock_coder.run_backtest = AsyncMock(return_value=expected_report)

        result = coder_node(state)

    mock_coder_cls.assert_called_once()
    mock_coder.run_backtest.assert_awaited_once_with(note)
    assert result["backtest_reports"] == [expected_report]
    assert result["approved_notes"][0].status == "completed"
