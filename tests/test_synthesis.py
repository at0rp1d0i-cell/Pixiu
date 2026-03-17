"""
Unit tests for SynthesisAgent (Stage 2b).

Covers:
- test_dedup_identical_hypotheses   : 两个相同假设 → 保留一个
- test_dedup_different_hypotheses   : 两个不同假设 → 保留两个
- test_family_clustering            : 3 个相关假设 → 识别为 1 个 family
- test_cross_island_merge           : 不同 island 的互补假设 → 产出 merge 建议
- test_empty_input                  : 0 个输入 → 空输出直通
- test_single_input                 : 1 个输入 → 直通
- test_graceful_degrade             : 内部异常 → 降级不抛出
- test_synthesis_node_not_passthrough: synthesis_node 实际调用 SynthesisAgent（不是 pass-through）
"""
import asyncio
import uuid
from datetime import date
from unittest.mock import patch

import pytest

from src.schemas.research_note import FactorResearchNote, SynthesisInsight
from src.agents.synthesis import SynthesisAgent, SynthesisResult


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _note(
    island: str = "momentum",
    hypothesis: str = "短期动量因子",
    economic_intuition: str = "价格趋势具有短期自我强化特性",
    proposed_formula: str = "Div($close, Ref($close, 5))",
    note_id: str | None = None,
) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=note_id or f"{island}_{uuid.uuid4().hex[:8]}",
        island=island,
        iteration=0,
        hypothesis=hypothesis,
        economic_intuition=economic_intuition,
        proposed_formula=proposed_formula,
        risk_factors=["流动性冲击"],
        market_context_date=date.today().strftime("%Y-%m-%d"),
    )


def _run(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.unit
def test_empty_input():
    """0 个输入 → 直通，所有列表为空。"""
    agent = SynthesisAgent()
    result = _run(agent.synthesize([]))
    assert isinstance(result, SynthesisResult)
    assert result.filtered_notes == []
    assert result.removed_notes == []
    assert result.insights == []
    assert result.families == {}
    assert result.merge_candidates == []


@pytest.mark.unit
def test_single_input():
    """1 个输入 → 直通，note 原样返回。"""
    agent = SynthesisAgent()
    note = _note()
    result = _run(agent.synthesize([note]))
    assert len(result.filtered_notes) == 1
    assert result.filtered_notes[0].note_id == note.note_id
    assert result.removed_notes == []


@pytest.mark.unit
def test_dedup_identical_hypotheses():
    """两个文本完全相同的假设 → 去重后只保留 1 个，且产出 duplicate insight。"""
    agent = SynthesisAgent()

    # 完全相同的文本内容，但不同 note_id
    text = "短期动量因子：近期涨幅对未来收益有正向预测力，价格趋势具有短期自我强化特性。"
    note_a = _note(
        island="momentum",
        hypothesis=text,
        economic_intuition=text,
        proposed_formula="Div($close, Ref($close, 5))",
        note_id="note_a",
    )
    note_b = _note(
        island="momentum",
        hypothesis=text,
        economic_intuition=text,
        proposed_formula="Div($close, Ref($close, 5))",
        note_id="note_b",
    )

    result = _run(agent.synthesize([note_a, note_b]))

    # 只保留 1 个
    assert len(result.filtered_notes) == 1
    assert len(result.removed_notes) == 1

    # 有 duplicate insight
    duplicate_insights = [i for i in result.insights if i.relationship == "duplicate"]
    assert len(duplicate_insights) >= 1


@pytest.mark.unit
def test_dedup_different_hypotheses():
    """两个语义完全不同的假设 → 两个都保留。"""
    agent = SynthesisAgent()

    note_a = _note(
        island="momentum",
        hypothesis="短期动量因子：近期涨幅对未来收益有正向预测力",
        economic_intuition="价格趋势自我强化",
        proposed_formula="Div($close, Ref($close, 5))",
        note_id="note_a",
    )
    note_b = _note(
        island="valuation",
        hypothesis="市盈率逆向因子：低PE股票未来收益更高，均值回归效应显著",
        economic_intuition="价值回归均值",
        proposed_formula="Div(1.0, Div($pe_ttm, $close))",
        note_id="note_b",
    )

    result = _run(agent.synthesize([note_a, note_b]))

    assert len(result.filtered_notes) == 2
    assert result.removed_notes == []


@pytest.mark.unit
def test_family_clustering():
    """3 个相关假设 → 层次聚类识别为同一 family。

    直接调用 _cluster_families 并传入预计算的单位向量矩阵，使得
    cosine_similarity 返回精确控制的相似度值：

      sim(a,b) = 0.75  > FAMILY_THRESHOLD(0.60), < DEDUP_THRESHOLD(0.85)
      sim(a,c) = 0.72  同上
      sim(b,c) = 0.70  同上

    这样 3 个 notes 全部通过去重，且距离矩阵（1-sim）全部 < 0.40，
    层次聚类（average linkage, t=0.40）应将 3 个合并为 1 个 family。
    """
    import numpy as np

    agent = SynthesisAgent()

    note_a = _note(island="momentum", note_id="fam_a")
    note_b = _note(island="momentum", note_id="fam_b")
    note_c = _note(island="momentum", note_id="fam_c")
    notes = [note_a, note_b, note_c]

    # 构造 3 个单位行向量，使其 dot product（= cosine similarity）恰好为目标值。
    # v_a = [1, 0, 0]
    # v_b 满足: v_a · v_b = 0.75  → v_b = [0.75, sqrt(1-0.75^2), 0]
    # v_c 满足: v_a · v_c = 0.72, v_b · v_c = 0.70
    #   v_c = [0.72, y, z] where:
    #     0.75*0.72 + sqrt(1-0.75^2)*y = 0.70  → y = (0.70 - 0.54) / 0.6614 ≈ 0.2419
    #     z = sqrt(1 - 0.72^2 - y^2)
    vb_x = 0.75
    vb_y = (1 - vb_x ** 2) ** 0.5          # ≈ 0.6614
    vc_x = 0.72
    vc_y = (0.70 - vb_x * vc_x) / vb_y    # ≈ 0.2419
    vc_z = max(0.0, 1 - vc_x**2 - vc_y**2) ** 0.5

    vectors = np.array([
        [1.0,   0.0,   0.0  ],
        [vb_x,  vb_y,  0.0  ],
        [vc_x,  vc_y,  vc_z ],
    ])

    # 验证构造的相似度（调试辅助，不影响断言）
    from sklearn.metrics.pairwise import cosine_similarity
    sim = cosine_similarity(vectors)
    assert sim[0][1] > 0.60 and sim[0][1] < 0.85
    assert sim[0][2] > 0.60 and sim[0][2] < 0.85
    assert sim[1][2] > 0.60 and sim[1][2] < 0.85

    # 验证去重不触发（所有相似度 < DEDUP_THRESHOLD）
    filtered, removed_ids, _ = agent._deduplicate(notes, vectors)
    assert removed_ids == [], f"相似度 < 0.85 时不应触发去重，但移除了: {removed_ids}"
    assert len(filtered) == 3

    # 验证聚类产出 family
    families, family_insights = agent._cluster_families(filtered, vectors)
    assert len(families) >= 1, (
        f"距离全部 < 0.40 的 3 个 notes 应聚为至少 1 个 family，实际 families={families}"
    )
    assert len(family_insights) >= 1


@pytest.mark.unit
def test_cross_island_merge():
    """来自不同 island 的语义相近（但未超去重阈值）假设 → 产出 merge 建议。"""
    agent = SynthesisAgent()

    # 用相近文本、不同 island 模拟"互补"对
    common = "成交量放大配合价格上涨，量价共振，动量效应显著"
    note_a = _note(
        island="momentum",
        hypothesis=common + "，动量视角",
        economic_intuition=common,
        proposed_formula="Mul(Div($close, Ref($close, 5)), Div($volume, Ref($volume, 5)))",
        note_id="cross_a",
    )
    note_b = _note(
        island="volume",
        hypothesis=common + "，量能视角",
        economic_intuition=common,
        proposed_formula="Mul(Div($volume, Ref($volume, 5)), Div($close, Ref($close, 5)))",
        note_id="cross_b",
    )

    result = _run(agent.synthesize([note_a, note_b]))

    # 两个 note 都来自不同 island，相似度高但不完全相同
    # 要么被去重（duplicate），要么被建议合并（complement）
    all_insights = result.insights + result.merge_candidates
    assert len(all_insights) >= 1


@pytest.mark.unit
def test_max_merge_candidates_limit():
    """merge 建议数量不超过 MAX_MERGE_CANDIDATES（3）。"""
    agent = SynthesisAgent()

    # 生成多个跨 island 的相似 notes
    islands = ["momentum", "volume", "valuation", "volatility", "sentiment"]
    notes = []
    base = "量价动量因子分析，价格趋势与成交量相互验证，短期预测效力强"
    for i, isl in enumerate(islands):
        notes.append(
            _note(
                island=isl,
                hypothesis=base + f" 视角{i}",
                economic_intuition=base,
                proposed_formula=f"Div($close, Ref($close, {5 + i}))",
                note_id=f"multi_{isl}",
            )
        )

    result = _run(agent.synthesize(notes))

    assert len(result.merge_candidates) <= SynthesisAgent.MAX_MERGE_CANDIDATES


@pytest.mark.unit
def test_graceful_degrade_on_vectorizer_error():
    """向量化失败时降级为 pass-through，不抛出异常。"""
    agent = SynthesisAgent()
    notes = [_note(note_id="n1"), _note(note_id="n2")]

    with patch.object(agent, "_vectorize", side_effect=RuntimeError("mock vectorizer failure")):
        result = _run(agent.synthesize(notes))

    # 降级：原样返回，无去重
    assert len(result.filtered_notes) == 2
    assert result.removed_notes == []
    assert result.insights == []


@pytest.mark.unit
def test_synthesis_result_fields():
    """SynthesisResult 包含所有必需字段，类型正确。"""
    agent = SynthesisAgent()
    notes = [_note(note_id="r1"), _note(note_id="r2")]
    result = _run(agent.synthesize(notes))

    assert hasattr(result, "filtered_notes")
    assert hasattr(result, "removed_notes")
    assert hasattr(result, "insights")
    assert hasattr(result, "families")
    assert hasattr(result, "merge_candidates")
    assert isinstance(result.filtered_notes, list)
    assert isinstance(result.removed_notes, list)
    assert isinstance(result.insights, list)
    assert isinstance(result.families, dict)
    assert isinstance(result.merge_candidates, list)


@pytest.mark.unit
def test_synthesis_node_not_passthrough():
    """synthesis_node 实际调用 SynthesisAgent（不再是 pass-through）：
    输入 2 个文本相同的假设，输出 research_notes 应只有 1 个。
    """
    from src.schemas.state import AgentState
    from src.core.orchestrator import synthesis_node

    text = "完全相同的假设文本，用于测试去重逻辑是否真正执行而非直通"
    note_a = _note(
        island="momentum",
        hypothesis=text,
        economic_intuition=text,
        proposed_formula="Div($close, Ref($close, 5))",
        note_id="dup_a",
    )
    note_b = _note(
        island="momentum",
        hypothesis=text,
        economic_intuition=text,
        proposed_formula="Div($close, Ref($close, 5))",
        note_id="dup_b",
    )

    state = AgentState(current_round=0, research_notes=[note_a, note_b])
    result = synthesis_node(state)

    # 不再是 pass-through：结果中应包含 research_notes 键
    assert "research_notes" in result
    # 两个相同假设去重后只剩 1 个
    assert len(result["research_notes"]) == 1
