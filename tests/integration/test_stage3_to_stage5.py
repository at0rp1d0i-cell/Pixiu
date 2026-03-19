"""
Stage 3 → Stage 4 → Stage 5 全流程集成测试

从 prefilter_node 开始，经过 coder_node、judgment_node、portfolio_node、
最终到 report_node，验证整条节点链在真实数据契约下能正确运行。

Tier: integration（需要真实 ChromaDB + SQLite，但 mock DockerRunner 和 LLM）
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.orchestrator import (
    coder_node,
    judgment_node,
    portfolio_node,
    prefilter_node,
    report_node,
)
from src.execution.docker_runner import ExecutionResult
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _make_note(
    note_id: str,
    formula: str = "Ref($close, 5) / $close - 1",
    island: str = "momentum",
) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=note_id,
        island=island,
        iteration=1,
        hypothesis=f"假设：{note_id}",
        economic_intuition="资金流推动趋势延续",
        proposed_formula=formula,
        final_formula=formula,
        exploration_questions=[],
        risk_factors=["市场风格切换"],
        market_context_date="2026-03-14",
        universe="csi300",
        backtest_start="2021-06-01",
        backtest_end="2023-12-31",
        status="ready_for_backtest",
    )


def _make_exec_result(sharpe: float = 3.1) -> ExecutionResult:
    stdout = "BACKTEST_RESULT_JSON:" + json.dumps({
        "sharpe": sharpe,
        "annualized_return": 0.22,
        "max_drawdown": 0.12,
        "ic_mean": 0.04,
        "ic_std": 0.03,
        "icir": 0.65,
        "turnover_rate": 0.18,
        "error": None,
    })
    return ExecutionResult(
        success=True,
        stdout=stdout,
        stderr="",
        returncode=0,
        duration_seconds=1.2,
    )


class _StubPool:
    def __init__(self):
        self.calls: list[dict] = []

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


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

def test_prefilter_to_report_node_full_pipeline(tmp_path, monkeypatch):
    """
    完整节点链：prefilter → coder → judgment → portfolio → report。

    验证：
    - prefilter_node 过滤无效公式
    - coder_node 生成 BacktestReport
    - judgment_node 生成 CriticVerdict + RiskAuditReport，并写入 pool
    - portfolio_node 生成 PortfolioAllocation
    - report_node 生成 CIOReport，设置 awaiting_human_approval=True
    """
    from src.control_plane.state_store import StateStore
    import src.core.orchestrator as orchestrator

    # 准备 3 个 notes，其中 1 个使用无效公式（负偏移，Validator 应拒绝）
    valid_note_1 = _make_note("momentum_001", formula="Ref($close, 5) / $close - 1")
    valid_note_2 = _make_note("momentum_002", formula="Mean($volume, 10) / Mean($volume, 30) - 1")
    invalid_note = _make_note("momentum_003", formula="Ref($close, -5)")  # 未来数据，无效

    initial_state = AgentState(
        current_round=1,
        research_notes=[valid_note_1, valid_note_2, invalid_note],
        approved_notes=[],
        backtest_reports=[],
        critic_verdicts=[],
    )

    # === Stage 3: prefilter_node ===
    capabilities = SimpleNamespace(
        available_fields=("$close", "$volume"),
        approved_operators=("Ref", "Mean"),
    )

    with patch("src.factor_pool.pool.get_factor_pool") as mock_pool_factory:
        mock_pool = MagicMock()
        mock_pool.get_island_factors.return_value = []
        mock_pool.query_constraints.return_value = []
        mock_pool_factory.return_value = mock_pool

        # AlignmentChecker 的 LLM 调用 mock
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM not available"))
        with patch("src.agents.prefilter.build_researcher_llm", return_value=mock_llm), \
             patch("src.agents.prefilter.get_runtime_formula_capabilities", return_value=capabilities):
            stage3_result = prefilter_node(initial_state)

    state_after_prefilter = initial_state.model_copy(update=stage3_result)

    # 无效公式应被过滤掉，至少保留 1 个有效 note
    assert len(state_after_prefilter.approved_notes) >= 1, (
        f"应至少有 1 个 approved note，实际: {len(state_after_prefilter.approved_notes)}"
    )
    assert all(n.note_id != "momentum_003" for n in state_after_prefilter.approved_notes), (
        "无效公式的 note 不应通过 prefilter"
    )

    # === Stage 4: coder_node（mock DockerRunner）===
    exec_result = _make_exec_result(sharpe=3.1)
    stub_pool = _StubPool()

    with patch("src.execution.coder.DockerRunner.run_python", new=AsyncMock(return_value=exec_result)), \
         patch("src.core.orchestrator.get_factor_pool", return_value=stub_pool), \
         patch("src.core.orchestrator._write_snapshot"):
        stage4_result = coder_node(state_after_prefilter)

    state_after_coder = state_after_prefilter.model_copy(update=stage4_result)
    assert len(state_after_coder.backtest_reports) > 0
    assert all(r.factor_id for r in state_after_coder.backtest_reports)

    # === Stage 5a: judgment_node ===
    with patch("src.core.orchestrator.get_factor_pool", return_value=stub_pool), \
         patch("src.core.orchestrator._write_snapshot"):
        stage5a_result = judgment_node(state_after_coder)

    state_after_judgment = state_after_coder.model_copy(update=stage5a_result)
    assert len(state_after_judgment.critic_verdicts) > 0
    assert len(state_after_judgment.risk_audit_reports) > 0

    # 强指标的因子应通过 Critic
    passed_verdicts = [v for v in state_after_judgment.critic_verdicts if v.overall_passed]
    assert len(passed_verdicts) > 0, "高 Sharpe 因子应通过 Critic"

    # pool.register_factor 应被调用，且 hypothesis 非空
    assert len(stub_pool.calls) > 0, "应有因子被写入 pool"
    for call in stub_pool.calls:
        assert call["hypothesis"], f"hypothesis 不应为空，实际: {call['hypothesis']!r}"

    # === Stage 5b: portfolio_node ===
    with patch("src.core.orchestrator.get_factor_pool", return_value=stub_pool):
        stage5b_result = portfolio_node(state_after_judgment)

    state_after_portfolio = state_after_judgment.model_copy(update=stage5b_result)
    assert state_after_portfolio.portfolio_allocation is not None
    assert state_after_portfolio.portfolio_allocation.total_factors >= 1

    # === Stage 5c: report_node（mock StateStore）===
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="integration_test")

    monkeypatch.setattr(orchestrator, "get_state_store", lambda: store)
    monkeypatch.setattr(orchestrator, "_current_run_id", run.run_id)
    monkeypatch.setattr(orchestrator, "REPORTS_DIR", tmp_path / "reports")

    with patch("src.core.orchestrator.get_factor_pool", return_value=stub_pool):
        stage5c_result = report_node(state_after_portfolio)

    final_state = state_after_portfolio.model_copy(update=stage5c_result)

    # 验证 CIOReport
    assert final_state.cio_report is not None
    assert "CIO Review" in final_state.cio_report.full_report_markdown
    assert final_state.awaiting_human_approval is True

    # 验证 StateStore 写入
    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.status == "awaiting_human_approval"

    snapshot = store.get_snapshot(run.run_id)
    assert snapshot is not None
    assert snapshot.awaiting_human_approval is True

    reports = store.list_reports(limit=10)
    assert len(reports) == 1
    assert reports[0].kind == "cio_report"


def test_coder_node_handles_multiple_notes_independently(tmp_path):
    """
    coder_node 对每个 note 独立执行回测，结果应互不影响。
    """
    notes = [
        _make_note("m_001", formula="Ref($close, 5) / $close - 1"),
        _make_note("m_002", formula="Mean($volume, 10) / Mean($volume, 30) - 1"),
    ]
    state = AgentState(
        current_round=1,
        approved_notes=notes,
        backtest_reports=[],
    )
    exec_result = _make_exec_result(sharpe=2.5)

    with patch("src.execution.coder.DockerRunner.run_python", new=AsyncMock(return_value=exec_result)), \
         patch("src.core.orchestrator.get_factor_pool", return_value=_StubPool()), \
         patch("src.core.orchestrator._write_snapshot"):
        result = coder_node(state)

    assert len(result["backtest_reports"]) == 2
    factor_ids = {r.factor_id for r in result["backtest_reports"]}
    assert "m_001" in factor_ids
    assert "m_002" in factor_ids
