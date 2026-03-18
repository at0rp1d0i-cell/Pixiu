"""
Orchestrator 路由逻辑测试

验证：
- route_after_portfolio 的两条分支（N 轮触发 / breakthrough 触发 / 第0轮不触发）
- loop_control_node 每轮无条件调用 scheduler.on_epoch_done
- loop_control_node 正确递增 round 并清空临时字段
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from src.core.orchestrator import (
    NODE_LOOP_CONTROL,
    NODE_REPORT,
    REPORT_EVERY_N_ROUNDS,
    loop_control_node,
    route_after_portfolio,
)
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.judgment import CriticVerdict
from src.schemas.state import AgentState


# ─────────────────────────────────────────────────────────
# Helpers
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


# ─────────────────────────────────────────────────────────
# route_after_portfolio 测试
# ─────────────────────────────────────────────────────────

class TestRouteAfterPortfolio:
    def test_round_zero_returns_loop_control(self):
        """第 0 轮不应触发报告（即使 0 % N == 0）。"""
        state = _make_state(current_round=0)
        result = route_after_portfolio(state)
        assert result == NODE_LOOP_CONTROL, (
            f"第 0 轮应返回 NODE_LOOP_CONTROL，实际返回: {result}"
        )

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
        high_sharpe = THRESHOLDS.min_sharpe * 1.2  # 超越 20%
        state = _make_state(
            current_round=3,  # 非 N 的整数倍
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


# ─────────────────────────────────────────────────────────
# loop_control_node 测试
# ─────────────────────────────────────────────────────────

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
        from src.schemas.research_note import FactorResearchNote
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
            "backtest_reports": [_make_report(2.0)],
            "critic_verdicts": [_make_verdict(True)],
        })
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_get_sched.return_value = MagicMock()
            result = loop_control_node(state)

        assert result["research_notes"] == []
        assert result["approved_notes"] == []
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
        """
        即使没有通过因子，on_epoch_done 也应被调用（修复 Bug 3）。
        确保温度每轮都能退火。
        """
        state = _make_state(
            current_round=2,
            backtest_reports=[_make_report(0.5, passed=False)],
            critic_verdicts=[_make_verdict(False)],
        )
        with patch("src.core.orchestrator.get_scheduler") as mock_get_sched:
            mock_sched = MagicMock()
            mock_get_sched.return_value = mock_sched
            loop_control_node(state)

        mock_sched.on_epoch_done.assert_called_once(), (
            "即使没有通过因子，on_epoch_done 也应被调用一次"
        )
