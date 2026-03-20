"""
Stage 1 → 2 → 3 → 5 端到端真实场景测试

Stage 4 (Docker/qlib) 不可用，用预构造的 BacktestReport 直接注入 Stage 5。

运行前需要设置 .env：RESEARCHER_API_KEY, RESEARCHER_BASE_URL, RESEARCHER_MODEL

运行方式：
    uv run pytest -q tests/integration/test_e2e_live.py -v -s

Tier: e2e
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.schemas.backtest import (
    BacktestMetrics,
    BacktestReport,
    ArtifactRefs,
    ExecutionMeta,
    FactorSpecSnapshot,
)
from src.schemas.market_context import MarketContextMemo
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState

pytestmark = pytest.mark.e2e


def _make_backtest_report(note: FactorResearchNote, sharpe: float = 3.1) -> BacktestReport:
    """为 approved note 构造一个合法的 BacktestReport（绕过 Stage 4）。"""
    formula = note.final_formula or note.proposed_formula
    return BacktestReport(
        report_id=f"report-{note.note_id}",
        note_id=note.note_id,
        factor_id=note.note_id,
        island=note.island,
        formula=formula,
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.22,
            max_drawdown=0.12,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.65,
            turnover_rate=0.18,
            coverage=1.0,
        ),
        passed=sharpe >= 2.67,
        execution_time_seconds=1.0,
        qlib_output_raw="{}",
        execution_meta=ExecutionMeta(
            universe="csi300",
            benchmark="csi300",
            start_date="2021-01-01",
            end_date="2025-01-01",
            runtime_seconds=1.0,
            timestamp_utc=datetime.now(UTC),
        ),
        factor_spec=FactorSpecSnapshot(
            formula=formula,
            hypothesis=note.hypothesis,
            economic_rationale=note.economic_intuition,
        ),
        artifacts=ArtifactRefs(),
    )


def _make_mock_pool():
    pool = MagicMock()
    pool.get_island_factors.return_value = []
    pool.get_island_best_factors.return_value = []
    pool.get_passed_factors.return_value = []
    pool.register_factor.return_value = None
    return pool


# ─────────────────────────────────────────────────────────
# E2E Test: Stage 1 → 2 → 3 → 5
# ─────────────────────────────────────────────────────────

def test_e2e_stage1_to_stage5(tmp_path, orchestrator_state_guard, monkeypatch):
    """
    完整 e2e 流程（Stage 4 用预构造 BacktestReport 绕过）：

    1. Stage 1: market_context_node → MarketContextMemo（真实 DeepSeek + AKShare MCP）
    2. Stage 2: hypothesis_gen_node → FactorResearchNote[]（真实 DeepSeek）
    3. Stage 3: prefilter_node → approved_notes[]（纯逻辑 + mock LLM）
    4. Stage 4: 跳过，直接注入 BacktestReport
    5. Stage 5: judgment_node + portfolio_node + report_node（纯确定性）
    """
    from src.core.orchestrator import (
        judgment_node,
        market_context_node,
        portfolio_node,
        prefilter_node,
        report_node,
    )

    mock_pool = _make_mock_pool()

    # ── Stage 1: 真实 LLM + 真实 MCP ──
    print("\n[E2E] Stage 1: 生成市场上下文...")
    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=mock_pool):
        s1_result = market_context_node(AgentState(current_round=1))

    memo: MarketContextMemo = s1_result.get("market_context")
    assert memo is not None, "Stage 1 未产出 market_context"
    assert isinstance(memo, MarketContextMemo)
    print(f"  regime={memo.market_regime}, islands={memo.suggested_islands}")
    print(f"  raw_summary={memo.raw_summary[:100]}")

    state = AgentState(current_round=1, market_context=memo)

    # ── Stage 2: 真实 LLM ──
    print("\n[E2E] Stage 2: 生成假设...")
    state_dict = dict(state)
    state_dict["active_islands"] = ["momentum", "valuation"]
    state_dict["iteration"] = 1

    from src.agents.researcher import hypothesis_gen_node as _inner_gen
    s2_result = _inner_gen(state_dict)

    notes = s2_result.get("research_notes", [])
    assert len(notes) >= 1, f"Stage 2 未产出任何 notes，实际: {len(notes)}"
    print(f"  生成 {len(notes)} 个 notes")
    for n in notes:
        print(f"    [{n.island}] {n.proposed_formula} — {n.hypothesis[:50]}")

    state = state.model_copy(update={
        "research_notes": notes,
        "hypotheses": s2_result.get("hypotheses", []),
        "strategy_specs": s2_result.get("strategy_specs", []),
    })

    # ── Stage 3: 纯逻辑过滤（AlignmentChecker mock）──
    print("\n[E2E] Stage 3: 过滤候选...")
    mock_llm = MagicMock()
    from unittest.mock import AsyncMock
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM not available"))
    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=mock_pool), \
         patch("src.agents.prefilter.build_researcher_llm", return_value=mock_llm):
        s3_result = prefilter_node(state)

    approved = s3_result.get("approved_notes", [])
    filtered = s3_result.get("filtered_count", 0)
    print(f"  放行 {len(approved)} 个，淘汰 {filtered} 个")

    if len(approved) == 0:
        pytest.skip("Stage 3 过滤后无 approved notes（所有公式被拒绝），跳过后续阶段")

    state = state.model_copy(update=s3_result)

    # ── Stage 4: 跳过，注入预构造 BacktestReport ──
    print("\n[E2E] Stage 4: 跳过（注入预构造 BacktestReport）...")
    reports = [_make_backtest_report(n, sharpe=3.1) for n in approved]
    print(f"  注入 {len(reports)} 个 BacktestReport")
    state = state.model_copy(update={"backtest_reports": reports})

    # ── Stage 5a: judgment_node（纯确定性）──
    print("\n[E2E] Stage 5a: judgment...")
    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=mock_pool), \
         patch("src.core.orchestrator.control_plane._write_snapshot"):
        s5a_result = judgment_node(state)

    verdicts = s5a_result.get("critic_verdicts", [])
    assert len(verdicts) > 0, "Stage 5a 未产出 critic_verdicts"
    print(f"  verdicts={len(verdicts)}, passed={sum(1 for v in verdicts if v.overall_passed)}")

    state = state.model_copy(update=s5a_result)

    # ── Stage 5b: portfolio_node ──
    print("\n[E2E] Stage 5b: portfolio...")
    with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=mock_pool):
        s5b_result = portfolio_node(state)

    alloc = s5b_result.get("portfolio_allocation")
    assert alloc is not None, "Stage 5b 未产出 portfolio_allocation"
    print(f"  total_factors={alloc.total_factors}")

    state = state.model_copy(update=s5b_result)

    # ── Stage 5c: report_node ──
    print("\n[E2E] Stage 5c: report...")
    from src.control_plane.state_store import StateStore
    from src.core.orchestrator import control_plane as orchestrator_control_plane
    from src.core.orchestrator import runtime as orchestrator_runtime

    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="e2e_test")

    with orchestrator_state_guard(reports_dir=tmp_path / "reports"):
        monkeypatch.setattr(orchestrator_control_plane, "get_state_store", lambda: store)
        orchestrator_runtime.set_current_run_id(run.run_id)

        with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=mock_pool):
            s5c_result = report_node(state)

    cio = s5c_result.get("cio_report")
    assert cio is not None, "Stage 5c 未产出 cio_report"
    assert "CIO Review" in cio.full_report_markdown
    print(f"  CIO report 生成，长度={len(cio.full_report_markdown)} 字符")
    print(f"  report 前200字:\n{cio.full_report_markdown[:200]}")

    final_state = state.model_copy(update=s5c_result)
    assert final_state.awaiting_human_approval is True

    print("\n[E2E] 全流程通过: Stage 1→2→3→(4 bypassed)→5 ✓")
