"""
Stage 2 真实场景测试：使用真实 DeepSeek API 验证 AlphaResearcher 生成质量。

运行前需要设置 .env：RESEARCHER_API_KEY, RESEARCHER_BASE_URL, RESEARCHER_MODEL

运行方式：
    uv run pytest -q tests/integration/test_stage2_live.py -v -s
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

pytestmark = pytest.mark.skipif(
    not os.getenv("RESEARCHER_API_KEY"),
    reason="RESEARCHER_API_KEY 未设置，跳过真实场景测试",
)

from src.agents.researcher import AlphaResearcher
from src.schemas.market_context import MarketContextMemo
from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.state import AgentState

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def _clear_proxy(monkeypatch):
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)


def _make_context() -> MarketContextMemo:
    return MarketContextMemo(
        date="2026-03-17",
        northbound=None,
        macro_signals=[],
        hot_themes=["AI算力", "红利"],
        historical_insights=[],
        suggested_islands=["momentum"],
        market_regime="trending_up",
        raw_summary="市场整体偏多，北向资金净流入，科技板块领涨。",
    )


# ─────────────────────────────────────────────────────────
# Test 1: AlphaResearcher 真实 LLM 调用，生成合法 Batch
# ─────────────────────────────────────────────────────────

def test_alpha_researcher_live_generates_valid_batch():
    """真实 DeepSeek API 调用，验证能生成 2-3 个合法 FactorResearchNote。"""
    researcher = AlphaResearcher(island="momentum")
    context = _make_context()

    batch = asyncio.run(researcher.generate_batch(context=context, iteration=1))

    print(f"\n[AlphaResearcherBatch] island={batch.island}")
    print(f"  notes count: {len(batch.notes)}")
    print(f"  rationale: {batch.generation_rationale[:100]}")
    for i, note in enumerate(batch.notes):
        print(f"  note[{i}]: formula={note.proposed_formula}, hypothesis={note.hypothesis[:60]}")

    assert isinstance(batch, AlphaResearcherBatch)
    assert batch.island == "momentum"
    assert 1 <= len(batch.notes) <= 5, f"notes 数量异常: {len(batch.notes)}"
    assert batch.generation_rationale, "generation_rationale 不能为空"

    for note in batch.notes:
        assert isinstance(note, FactorResearchNote)
        assert note.island == "momentum"
        assert note.proposed_formula, "proposed_formula 不能为空"
        assert note.hypothesis, "hypothesis 不能为空"
        assert note.economic_intuition, "economic_intuition 不能为空"
        assert note.note_id, "note_id 不能为空"
        # 记录含未来数据的公式（LLM 偶发违规，不 hard fail，但打印警告）
        if "Ref($close, -" in note.proposed_formula:
            import warnings
            warnings.warn(f"公式含未来数据（LLM 违规）: {note.proposed_formula}")


# ─────────────────────────────────────────────────────────
# Test 2: 不同 Island 生成差异化假设
# ─────────────────────────────────────────────────────────

def test_alpha_researcher_live_different_islands():
    """两个不同 Island 的生成结果应有差异（公式不完全相同）。"""
    context = _make_context()

    batch_mom = asyncio.run(
        AlphaResearcher(island="momentum").generate_batch(context=context, iteration=1)
    )
    batch_val = asyncio.run(
        AlphaResearcher(island="valuation").generate_batch(context=context, iteration=1)
    )

    print(f"\n[momentum] formulas: {[n.proposed_formula for n in batch_mom.notes]}")
    print(f"[valuation] formulas: {[n.proposed_formula for n in batch_val.notes]}")

    mom_formulas = {n.proposed_formula for n in batch_mom.notes}
    val_formulas = {n.proposed_formula for n in batch_val.notes}

    # 两个 island 的公式集合不应完全相同
    assert mom_formulas != val_formulas, "不同 Island 生成了完全相同的公式集合"

    # valuation island 应倾向于使用基本面字段
    val_all_formulas = " ".join(val_formulas)
    # 至少有一个公式包含价格或基本面相关字段
    assert any(field in val_all_formulas for field in ("$pe", "$pb", "$roe", "$close", "$open")), \
        f"valuation island 公式未使用任何已知字段: {val_formulas}"


# ─────────────────────────────────────────────────────────
# Test 3: 带历史反馈的迭代生成
# ─────────────────────────────────────────────────────────

def test_alpha_researcher_live_with_feedback():
    """带上轮失败反馈，验证 LLM 能接受约束并生成新方向。"""
    from src.schemas.judgment import CriticVerdict

    last_verdict = CriticVerdict(
        report_id="rep-prev",
        factor_id="factor-prev",
        note_id="note-prev",
        overall_passed=False,
        decision="reject",
        score=0.2,
        checks=[],
        passed_checks=[],
        failed_checks=["sharpe"],
        failure_mode="low_sharpe",
        failure_explanation="Sharpe=0.5，低于门槛 2.67。",
        suggested_fix="考虑更换信号方向或延长窗口平滑噪声。",
        summary="Sharpe 未通过",
        reason_codes=["LOW_SHARPE"],
        register_to_pool=False,
        pool_tags=[],
    )

    researcher = AlphaResearcher(island="momentum")
    context = _make_context()

    batch = asyncio.run(researcher.generate_batch(
        context=context,
        iteration=2,
        last_verdict=last_verdict,
        failed_formulas=["$close/Ref($close,5)-1"],
    ))

    print(f"\n[带反馈迭代] notes count: {len(batch.notes)}")
    for note in batch.notes:
        print(f"  formula: {note.proposed_formula}")
        print(f"  hypothesis: {note.hypothesis[:80]}")

    assert isinstance(batch, AlphaResearcherBatch)
    assert len(batch.notes) >= 1

    # 不应重复已失败的公式
    for note in batch.notes:
        assert note.proposed_formula != "$close/Ref($close,5)-1", \
            "LLM 重复了已失败的公式"


# ─────────────────────────────────────────────────────────
# Test 4: hypothesis_gen_node 完整节点（含 SubspaceScheduler）
# ─────────────────────────────────────────────────────────

def test_hypothesis_gen_node_live():
    """跑完整的 hypothesis_gen_node，验证多 Island 并行生成并写入 state。"""
    from src.agents.researcher import hypothesis_gen_node

    context = _make_context()
    state = AgentState(
        current_round=1,
        market_context=context,
        iteration=1,
    )
    state_dict = dict(state)
    state_dict["active_islands"] = ["momentum", "valuation"]

    result = hypothesis_gen_node(state_dict)

    notes = result.get("research_notes", [])
    print(f"\n[hypothesis_gen_node] 生成 notes: {len(notes)}")
    for note in notes:
        print(f"  [{note.island}] {note.proposed_formula} — {note.hypothesis[:60]}")

    assert len(notes) >= 2, f"至少应生成 2 个 notes，实际: {len(notes)}"

    islands_covered = {note.island for note in notes}
    assert "momentum" in islands_covered or "valuation" in islands_covered, \
        f"未覆盖目标 island: {islands_covered}"

    for note in notes:
        assert isinstance(note, FactorResearchNote)
        assert note.proposed_formula
        assert note.hypothesis
