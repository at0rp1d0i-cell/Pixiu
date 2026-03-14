"""
judgment_node → FactorPool 写回测试

验证：
- verdict.register_to_pool=True 时 pool.register_factor 被调用
- hypothesis 参数被正确从 approved_notes 传入
- verdict.register_to_pool=False 时不调用 pool
"""
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.orchestrator import judgment_node
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _make_note(note_id: str, hypothesis: str = "测试假设") -> FactorResearchNote:
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


def _make_report(note_id: str, sharpe: float = 3.0, passed: bool = True) -> BacktestReport:
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


class _StubPool:
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


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

def test_judgment_node_passes_hypothesis_to_pool():
    """
    judgment_node 在写入 pool 时应传入 hypothesis（来自 approved_notes）。
    修复 Bug 4：之前 hypothesis 参数为空字符串。
    """
    note = _make_note("factor_001", hypothesis="资金流持续推动短期趋势延续")
    report = _make_report("factor_001", sharpe=3.0, passed=True)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPool()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1, "应有一次 register_factor 调用"
    call = pool.calls[0]
    assert call["hypothesis"] == "资金流持续推动短期趋势延续", (
        f"hypothesis 应从 note 中传入，实际: {call['hypothesis']!r}"
    )


def test_judgment_node_calls_pool_when_register_to_pool_true():
    """verdict.register_to_pool=True 时应调用 pool.register_factor。"""
    note = _make_note("factor_002")
    report = _make_report("factor_002", sharpe=3.0)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPool()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        judgment_node(state)

    assert len(pool.calls) == 1, "register_to_pool=True 时应调用 pool.register_factor"


def test_judgment_node_returns_verdicts_and_risk_reports():
    """judgment_node 应返回 critic_verdicts 和 risk_audit_reports。"""
    note = _make_note("factor_003")
    report = _make_report("factor_003", sharpe=3.0)
    state = AgentState(
        current_round=1,
        approved_notes=[note],
        backtest_reports=[report],
        critic_verdicts=[],
    )
    pool = _StubPool()

    with patch("src.core.orchestrator.get_factor_pool", return_value=pool), \
         patch("src.core.orchestrator._write_snapshot"):
        result = judgment_node(state)

    assert "critic_verdicts" in result
    assert "risk_audit_reports" in result
    assert len(result["critic_verdicts"]) == 1
    assert len(result["risk_audit_reports"]) == 1


def test_judgment_node_empty_reports_returns_empty():
    """无回测报告时应返回空列表。"""
    state = AgentState(
        current_round=1,
        approved_notes=[],
        backtest_reports=[],
        critic_verdicts=[],
    )

    with patch("src.core.orchestrator.get_factor_pool", return_value=_StubPool()):
        result = judgment_node(state)

    assert result["critic_verdicts"] == []
    assert result["risk_audit_reports"] == []
