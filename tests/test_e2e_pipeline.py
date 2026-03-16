"""
End-to-end pipeline test: verifies the full LangGraph graph
runs from Stage 1 through Stage 5 with mocked LLM and Docker.

Covers the happy path: Stage 1→2→3→4b→5→loop_control→END (1 round).
"""
import asyncio
import json
import os
import tempfile
import uuid
from datetime import date, UTC, datetime
from unittest.mock import patch, AsyncMock

import pytest

from src.schemas.market_context import MarketContextMemo, NorthboundFlow, MacroSignal
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.state import AgentState
from src.execution.docker_runner import ExecutionResult


# ─────────────────────────────────────────────
# Test data factories
# ─────────────────────────────────────────────

def _make_memo():
    return MarketContextMemo(
        date=date.today().strftime("%Y-%m-%d"),
        northbound=NorthboundFlow(
            net_buy_bn=15.0,
            top_sectors=["科技"],
            top_stocks=["600519"],
            sentiment="bullish",
        ),
        macro_signals=[
            MacroSignal(signal="PMI up", source="pmi", direction="positive", confidence=0.7),
        ],
        hot_themes=["AI"],
        historical_insights=[],
        suggested_islands=["momentum"],
        market_regime="trending_up",
        raw_summary="北向资金流入，市场偏暖。",
    )


def _make_notes(n=2):
    notes = []
    for i in range(n):
        notes.append(FactorResearchNote(
            note_id=f"momentum_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
            island="momentum",
            iteration=0,
            hypothesis=f"短期动量因子假设 {i}: 近期涨幅对未来收益有正向预测力。",
            economic_intuition="价格趋势具有短期自我强化特性",
            proposed_formula=f"Div($close, Ref($close, {5 + i}))",
            risk_factors=["流动性冲击", "市场反转"],
            market_context_date=date.today().strftime("%Y-%m-%d"),
            applicable_regimes=["trending_up"],
            invalid_regimes=["volatile"],
        ))
    return notes


def _make_passing_docker_result():
    """Docker output that Coder can parse into a passing BacktestReport."""
    metrics = {
        "sharpe": 3.5,
        "annualized_return": 0.25,
        "max_drawdown": 0.10,
        "ic_mean": 0.05,
        "ic_std": 0.03,
        "icir": 1.67,
        "turnover_rate": 0.15,
        "coverage": 0.95,
    }
    return ExecutionResult(
        success=True,
        stdout=json.dumps({"metrics": metrics}),
        stderr="",
        returncode=0,
        duration_seconds=5.0,
    )


def _make_backtest_report(note, passed=True):
    """Directly create a BacktestReport for tests that bypass Coder."""
    if passed:
        metrics = BacktestMetrics(
            sharpe=3.5, annualized_return=0.25, max_drawdown=0.10,
            ic_mean=0.05, ic_std=0.03, icir=1.67, turnover_rate=0.15,
            coverage=0.95,
        )
    else:
        metrics = BacktestMetrics(
            sharpe=0.5, annualized_return=0.02, max_drawdown=0.25,
            ic_mean=0.01, ic_std=0.05, icir=0.2, turnover_rate=0.60,
        )
    return BacktestReport(
        report_id=str(uuid.uuid4()),
        note_id=note.note_id,
        factor_id=note.note_id,
        island=note.island,
        formula=note.proposed_formula,
        metrics=metrics,
        passed=passed,
        status="success",
        execution_time_seconds=5.0,
        qlib_output_raw="mock output",
    )


# ─────────────────────────────────────────────
# Mock functions for each stage
# ─────────────────────────────────────────────

def _mock_market_context_node(state_dict):
    """Stage 1 mock: return a valid MarketContextMemo."""
    return {**state_dict, "market_context": _make_memo()}


def _mock_hypothesis_gen_node(state_dict):
    """Stage 2 mock: return valid FactorResearchNotes."""
    return {**state_dict, "research_notes": _make_notes(2)}


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.smoke
def test_e2e_pipeline_one_round_factors_fail():
    """
    Full pipeline: 1 round, factors fail judgment → loop_control → END.

    Flow: START → market_context → hypothesis_gen → synthesis → prefilter
          → coder → judgment → loop_control → END
    """
    import src.core.orchestrator as orch

    # Save and reset global state
    saved = (orch._graph, orch._scheduler, orch._current_run_id, orch.MAX_ROUNDS)
    orch._graph = None
    orch._scheduler = None
    orch._current_run_id = None
    orch.MAX_ROUNDS = 1

    # Use temp dirs for factor pool and state store
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_state.db")
        pool_path = os.path.join(tmpdir, "test_pool")

        async def mock_run_backtest(self, note):
            return _make_backtest_report(note, passed=False)

        async def mock_alignment_check(self, note):
            return True, "mock aligned"

        with patch("src.agents.market_analyst.market_context_node", _mock_market_context_node), \
             patch("src.agents.researcher.hypothesis_gen_node", _mock_hypothesis_gen_node), \
             patch("src.agents.prefilter.AlignmentChecker.check", mock_alignment_check), \
             patch("src.execution.coder.Coder.run_backtest", mock_run_backtest), \
             patch("src.execution.coder.Coder.__init__", lambda self: None), \
             patch.dict(os.environ, {"PIXIU_STATE_STORE_PATH": db_path}), \
             patch("src.factor_pool.pool._DEFAULT_DB_PATH", pool_path), \
             patch("src.factor_pool.pool._pool_instance", None), \
             patch("src.control_plane.state_store._state_store", None):

            try:
                graph = orch.build_graph()
                config = {"configurable": {"thread_id": "test_e2e_fail"}}
                initial = AgentState(current_round=0)

                result = asyncio.run(
                    graph.ainvoke(initial.model_dump(), config=config)
                )

                # Pipeline completed one round
                assert result["current_round"] == 1
                # All verdicts should be failures (no passed)
                # After loop_control, temp state is cleared
                assert result.get("research_notes") == []
                assert result.get("approved_notes") == []
            finally:
                orch._graph, orch._scheduler, orch._current_run_id, orch.MAX_ROUNDS = saved


@pytest.mark.smoke
def test_e2e_pipeline_one_round_factors_pass():
    """
    Full pipeline: 1 round, factors pass judgment → portfolio → loop_control → END.

    Flow: START → market_context → hypothesis_gen → synthesis → prefilter
          → coder → judgment → portfolio → loop_control → END
    """
    import src.core.orchestrator as orch

    saved = (orch._graph, orch._scheduler, orch._current_run_id,
             orch.MAX_ROUNDS, orch.REPORT_EVERY_N_ROUNDS)
    orch._graph = None
    orch._scheduler = None
    orch._current_run_id = None
    orch.MAX_ROUNDS = 1
    orch.REPORT_EVERY_N_ROUNDS = 999  # Avoid triggering report → human gate

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_state.db")
        pool_path = os.path.join(tmpdir, "test_pool")

        async def mock_run_backtest(self, note):
            return _make_backtest_report(note, passed=True)

        async def mock_alignment_check(self, note):
            return True, "mock aligned"

        with patch("src.agents.market_analyst.market_context_node", _mock_market_context_node), \
             patch("src.agents.researcher.hypothesis_gen_node", _mock_hypothesis_gen_node), \
             patch("src.agents.prefilter.AlignmentChecker.check", mock_alignment_check), \
             patch("src.execution.coder.Coder.run_backtest", mock_run_backtest), \
             patch("src.execution.coder.Coder.__init__", lambda self: None), \
             patch.dict(os.environ, {"PIXIU_STATE_STORE_PATH": db_path}), \
             patch("src.factor_pool.pool._DEFAULT_DB_PATH", pool_path), \
             patch("src.factor_pool.pool._pool_instance", None), \
             patch("src.control_plane.state_store._state_store", None):

            try:
                graph = orch.build_graph()
                config = {"configurable": {"thread_id": "test_e2e_pass"}}
                initial = AgentState(current_round=0)

                result = asyncio.run(
                    graph.ainvoke(initial.model_dump(), config=config)
                )

                # Pipeline completed one round and looped
                assert result["current_round"] == 1
                # After loop_control, temp state is cleared
                assert result.get("backtest_reports") == []
                assert result.get("critic_verdicts") == []
            finally:
                (orch._graph, orch._scheduler, orch._current_run_id,
                 orch.MAX_ROUNDS, orch.REPORT_EVERY_N_ROUNDS) = saved


@pytest.mark.smoke
def test_e2e_prefilter_rejects_all():
    """
    Pipeline with all notes rejected by prefilter → skip Stage 4/5.

    Flow: START → market_context → hypothesis_gen → synthesis → prefilter
          → loop_control → END (no approved notes)
    """
    import src.core.orchestrator as orch

    saved = (orch._graph, orch._scheduler, orch._current_run_id, orch.MAX_ROUNDS)
    orch._graph = None
    orch._scheduler = None
    orch._current_run_id = None
    orch.MAX_ROUNDS = 1

    def mock_hypothesis_gen_bad(state_dict):
        """Generate notes with invalid formulas that Validator will reject."""
        notes = [
            FactorResearchNote(
                note_id=f"bad_{uuid.uuid4().hex[:8]}",
                island="momentum",
                iteration=0,
                hypothesis="Bad formula test",
                economic_intuition="Testing rejection",
                proposed_formula="INVALID()",  # Unknown operator
                risk_factors=["test"],
                market_context_date=date.today().strftime("%Y-%m-%d"),
            ),
        ]
        return {**state_dict, "research_notes": notes}

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_state.db")
        pool_path = os.path.join(tmpdir, "test_pool")

        async def mock_alignment_check(self, note):
            return True, "mock aligned"

        with patch("src.agents.market_analyst.market_context_node", _mock_market_context_node), \
             patch("src.agents.researcher.hypothesis_gen_node", mock_hypothesis_gen_bad), \
             patch("src.agents.prefilter.AlignmentChecker.check", mock_alignment_check), \
             patch.dict(os.environ, {"PIXIU_STATE_STORE_PATH": db_path}), \
             patch("src.factor_pool.pool._DEFAULT_DB_PATH", pool_path), \
             patch("src.factor_pool.pool._pool_instance", None), \
             patch("src.control_plane.state_store._state_store", None):

            try:
                graph = orch.build_graph()
                config = {"configurable": {"thread_id": "test_e2e_reject"}}
                initial = AgentState(current_round=0)

                result = asyncio.run(
                    graph.ainvoke(initial.model_dump(), config=config)
                )

                # Completed one round
                assert result["current_round"] == 1
                # No backtests ran (prefilter rejected all)
                assert result.get("backtest_reports") == []
            finally:
                orch._graph, orch._scheduler, orch._current_run_id, orch.MAX_ROUNDS = saved
