"""
Stage 1 → Stage 2 → Stage 3 端到端集成测试

合并来源:
- tests/test_e2e_stage1_to_stage3.py: Stage 1→2→3 完整数据流验证
- tests/test_stage2_to_stage3_integration.py: Stage 2→3 FactorResearchNote 过滤流程

Tier: integration（mock LLM，不依赖网络）
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.market_context import (
    MarketContextMemo, NorthboundFlow, MacroSignal, HistoricalInsight,
)
from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import ExplorationSubspace
from src.schemas.exploration import SubspaceRegistry
from src.schemas.state import AgentState
from src.agents.prefilter import Validator, NoveltyFilter, AlignmentChecker

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

def _make_market_context() -> MarketContextMemo:
    """构造一个最小合法 MarketContextMemo。"""
    return MarketContextMemo(
        date="2026-03-17",
        northbound=NorthboundFlow(
            net_buy_bn=52.3,
            top_sectors=["白酒", "新能源"],
            top_stocks=["贵州茅台", "宁德时代"],
            sentiment="bullish",
        ),
        macro_signals=[
            MacroSignal(signal="MLF利率维持2.50%", source="news", direction="neutral", confidence=0.8),
        ],
        hot_themes=["AI算力", "低空经济"],
        historical_insights=[
            HistoricalInsight(
                island="momentum",
                best_factor_formula="Ref($close, 5) / Ref($close, 20) - 1",
                best_sharpe=2.1,
                common_failure_modes=["震荡市回撤大"],
                suggested_directions=["尝试加入波动率过滤"],
            ),
        ],
        suggested_islands=["momentum", "volatility"],
        market_regime="range_bound",
        raw_summary="市场横盘震荡，北向资金小幅净买入，AI算力主题活跃。",
    )


def _make_llm_batch_response(island: str, subspace: str) -> str:
    """构造 AlphaResearcher 的 mock LLM 响应 JSON。"""
    formulas = {
        "factor_algebra": [
            "Ref($close, 5) / Ref($close, 20) - 1",
            "Mean($volume, 10) / Mean($volume, 30) - 1",
        ],
        "symbolic_mutation": [
            "Rank(Ref($close, 5) / Ref($close, 20) - 1)",
            "Std($close, 10) / Mean($close, 10)",
        ],
        "cross_market": [
            "($high - $low) / $close",
            "Mean($amount, 5) / Mean($amount, 20) - 1",
        ],
        "narrative_mining": [
            "($close - Min($close, 20)) / (Max($close, 20) - Min($close, 20))",
            "Mean($volume, 5) / Mean($volume, 20) - 1",
        ],
    }
    fs = formulas.get(subspace, formulas["factor_algebra"])
    notes = []
    for i, f in enumerate(fs):
        notes.append({
            "note_id": f"{island}_{subspace}_{i}",
            "island": island,
            "iteration": 1,
            "hypothesis": f"{island} {subspace} 假设 {i}",
            "economic_intuition": f"{subspace} 经济直觉 {i}",
            "proposed_formula": f,
            "risk_factors": ["市场风格切换"],
            "market_context_date": "2026-03-17",
            "applicable_regimes": ["range_bound"],
            "invalid_regimes": ["structural_break"],
            "exploration_subspace": subspace,
        })
    return json.dumps({
        "notes": notes,
        "generation_rationale": f"{island} {subspace} 测试生成",
    })


def _make_mock_pool(existing_formulas=None):
    """创建 mock FactorPool，返回指定的历史因子公式"""
    pool = MagicMock()
    factors = [{"factor_id": f"f{i}", "formula": f} for i, f in enumerate(existing_formulas or [])]
    pool.get_island_factors.return_value = factors
    pool.get_island_best_factors.return_value = []
    return pool


# ─────────────────────────────────────────────────────────
# Tests from test_e2e_stage1_to_stage3.py
# ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestE2EStage1ToStage3:
    """Stage 1 → 2 → 3 端到端测试。"""

    def test_full_pipeline_data_flow(self):
        """
        完整流程：
        1. Stage 1 产出 MarketContextMemo
        2. Stage 2 使用结构化子空间上下文生成 notes + hypotheses + strategy_specs
        3. Stage 3 过滤无效公式，保留合法候选
        4. 验证 exploration_subspace 溯源字段全程流通
        """
        from src.core.orchestrator import (
            hypothesis_gen_node as orch_hyp_gen,
            prefilter_node as orch_prefilter,
        )

        # ── Stage 1: 构造 MarketContextMemo ──
        market_ctx = _make_market_context()
        state = AgentState(
            current_round=1,
            market_context=market_ctx,
        )

        # ── Stage 2: Mock AlphaResearcher LLM，运行 hypothesis_gen_node ──
        # 先导入真实类，再 patch
        from src.agents.researcher import AlphaResearcher as RealAR

        def make_researcher(island, **kwargs):
            instance = MagicMock()
            async def mock_generate(context, iteration, last_verdict=None,
                                    failed_formulas=None, subspace_hint=None):
                ss_val = subspace_hint.value if subspace_hint else "factor_algebra"
                content = _make_llm_batch_response(island, ss_val)
                real = object.__new__(RealAR)
                real.island = island
                real.registry = SubspaceRegistry.get_default_registry()
                real.factor_pool = None
                return real._parse_batch(content, iteration, subspace_hint)
            instance.generate_batch = mock_generate
            return instance

        with patch("src.agents.researcher.AlphaResearcher") as MockAR:
            MockAR.side_effect = make_researcher
            stage2_result = orch_hyp_gen(state)

        state_after_s2 = state.model_copy(update=stage2_result)

        # 验证 Stage 2 输出
        assert len(state_after_s2.research_notes) > 0
        assert len(state_after_s2.hypotheses) == len(state_after_s2.research_notes)
        assert len(state_after_s2.strategy_specs) == len(state_after_s2.research_notes)

        # 验证 exploration_subspace 溯源
        notes_with_subspace = [
            n for n in state_after_s2.research_notes
            if n.exploration_subspace is not None
        ]
        assert len(notes_with_subspace) == len(state_after_s2.research_notes), \
            "所有 notes 应带 exploration_subspace"

        hyps_with_subspace = [
            h for h in state_after_s2.hypotheses
            if h.exploration_subspace is not None
        ]
        assert len(hyps_with_subspace) == len(state_after_s2.hypotheses), \
            "所有 hypotheses 应带 exploration_subspace（从 note 传递）"

        # 验证 Hypothesis ↔ StrategySpec 链接
        for hyp, spec in zip(state_after_s2.hypotheses, state_after_s2.strategy_specs):
            assert hyp.hypothesis_id == spec.hypothesis_id

        # ── Stage 3: PreFilter ──
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM not available"))
        with patch("src.core.orchestrator.control_plane.get_factor_pool", return_value=_make_mock_pool()):
            with patch("src.agents.prefilter.build_researcher_llm", return_value=mock_llm):
                stage3_result = orch_prefilter(state_after_s2)

        state_after_s3 = state_after_s2.model_copy(update=stage3_result)

        # 验证 Stage 3 输出
        assert len(state_after_s3.approved_notes) > 0
        assert state_after_s3.filtered_count >= 0

        # approved_notes 应保留 exploration_subspace
        for note in state_after_s3.approved_notes:
            assert note.exploration_subspace is not None, \
                f"approved note {note.note_id} 丢失了 exploration_subspace"

        # hypotheses/strategy_specs 应在 state 中保持（Stage 3 不清除它们）
        assert len(state_after_s3.hypotheses) > 0
        assert len(state_after_s3.strategy_specs) > 0

    def test_subspace_context_reaches_prompt(self):
        """验证结构化子空间上下文确实被注入到 LLM prompt 中。"""
        from src.agents.researcher import AlphaResearcher

        captured_messages = []

        async def capture_ainvoke(messages):
            captured_messages.extend(messages)
            resp = MagicMock()
            resp.content = _make_llm_batch_response("momentum", "factor_algebra")
            return resp

        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        with patch("src.agents.researcher.build_researcher_llm", return_value=mock_chat):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
                researcher = AlphaResearcher(island="momentum")
                asyncio.run(researcher.generate_batch(
                    context=_make_market_context(),
                    iteration=1,
                    subspace_hint=ExplorationSubspace.FACTOR_ALGEBRA,
                ))

        # 验证 prompt 中包含结构化上下文（而非旧的一行 hint）
        user_msg = str(captured_messages[-1].content)
        assert "因子代数" in user_msg or "Factor Algebra" in user_msg
        assert "$close" in user_msg
        assert "原语" in user_msg or "primitive" in user_msg.lower()
        # 不应包含旧的 hint 文本
        assert "本轮优先使用" not in user_msg

    def test_multiple_subspaces_produce_diverse_notes(self):
        """验证不同子空间产出的 notes 具有不同的 exploration_subspace 标记。"""
        from src.agents.researcher import AlphaResearcher

        subspaces_seen = set()
        for ss in [ExplorationSubspace.FACTOR_ALGEBRA, ExplorationSubspace.NARRATIVE_MINING]:
            mock_resp = MagicMock()
            mock_resp.content = _make_llm_batch_response("momentum", ss.value)

            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=mock_resp)
            with patch("src.agents.researcher.build_researcher_llm", return_value=mock_chat):
                with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
                    researcher = AlphaResearcher(island="momentum")
                    batch = asyncio.run(researcher.generate_batch(
                        context=None, iteration=1, subspace_hint=ss,
                    ))

            for note in batch.notes:
                subspaces_seen.add(note.exploration_subspace)

        assert len(subspaces_seen) >= 2, \
            f"应至少看到 2 个不同子空间，实际: {subspaces_seen}"

    def test_state_schema_accepts_new_fields(self):
        """验证 AgentState 能正确存储 hypotheses 和 strategy_specs。"""
        note = FactorResearchNote(
            note_id="test_001", island="momentum", iteration=1,
            hypothesis="test", economic_intuition="test",
            proposed_formula="$close", risk_factors=[],
            market_context_date="2026-03-17",
            exploration_subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        )
        hyp = note.to_hypothesis()
        spec = note.to_strategy_spec()

        state = AgentState(
            research_notes=[note],
            hypotheses=[hyp],
            strategy_specs=[spec],
        )
        assert len(state.hypotheses) == 1
        assert len(state.strategy_specs) == 1
        assert state.hypotheses[0].exploration_subspace == ExplorationSubspace.FACTOR_ALGEBRA


# ─────────────────────────────────────────────────────────
# Tests from test_stage2_to_stage3_integration.py
# ─────────────────────────────────────────────────────────

def test_note_to_hypothesis_passes_prefilter():
    """测试从 note 转换的 hypothesis 可以通过 prefilter 验证"""
    # Stage 2: 创建 note
    note = FactorResearchNote(
        note_id="momentum_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, 5) / Ref($close, 20) - 1",
        final_formula="Ref($close, 5) / Ref($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-13"
    )

    # 转换为 Hypothesis
    hypothesis = note.to_hypothesis()

    # Stage 3: Validator 验证
    validator = Validator()
    is_valid, reason = validator.validate(note)

    assert is_valid, f"Validator 应该通过，但失败原因: {reason}"
    assert hypothesis.mechanism == "短期价格动量延续效应"


def test_batch_notes_conversion_and_filtering():
    """测试批量 notes 转换后的过滤流程"""
    # Stage 2: 创建 batch
    notes = [
        FactorResearchNote(
            note_id=f"momentum_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"动量假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula="Ref($close, 5) / Ref($close, 20) - 1",
            final_formula="Ref($close, 5) / Ref($close, 20) - 1",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]

    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试批量"
    )

    # 转换为 hypotheses 和 specs
    hypotheses = [note.to_hypothesis() for note in batch.notes]
    specs = [note.to_strategy_spec() for note in batch.notes]

    # Stage 3: 验证所有 notes
    validator = Validator()
    valid_notes = []
    for note in batch.notes:
        is_valid, _ = validator.validate(note)
        if is_valid:
            valid_notes.append(note)

    assert len(valid_notes) == 3, "所有 notes 都应该通过验证"
    assert len(hypotheses) == len(specs) == 3


def test_invalid_formula_rejected_by_validator():
    """测试无效公式被 validator 拒绝"""
    # Stage 2: 创建包含无效公式的 note
    note = FactorResearchNote(
        note_id="invalid_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="Ref($close, -5)",  # 使用未来数据，无效
        final_formula="Ref($close, -5)",
        risk_factors=[],
        market_context_date="2026-03-13"
    )

    # Stage 3: Validator 应该拒绝
    validator = Validator()
    is_valid, reason = validator.validate(note)

    assert not is_valid, "包含未来数据的公式应该被拒绝"
    assert "未来数据" in reason or "Ref($close, -" in reason


def test_novelty_filter_with_hypothesis():
    """测试 NoveltyFilter 与 hypothesis 的集成"""
    formula = "Ref($close, 5) / Ref($close, 20) - 1"

    note = FactorResearchNote(
        note_id="momentum_002",
        island="momentum",
        iteration=1,
        hypothesis="短期动量",
        economic_intuition="原理2",
        proposed_formula=formula,
        final_formula=formula,
        risk_factors=[],
        market_context_date="2026-03-13"
    )

    # pool 为空时应该通过
    pool_empty = _make_mock_pool([])
    novelty_filter = NoveltyFilter(pool=pool_empty)
    is_novel, _ = novelty_filter.check(note)
    assert is_novel

    # pool 中已有相同公式时应该被拒绝
    pool_dup = _make_mock_pool([formula])
    novelty_filter_dup = NoveltyFilter(pool=pool_dup)
    is_novel2, reason = novelty_filter_dup.check(note)
    assert not is_novel2, "相同公式应该被识别为重复"


def test_alignment_checker_with_strategy_spec():
    """测试 AlignmentChecker 失败时放行（LLM 不可用时的降级行为）"""
    note = FactorResearchNote(
        note_id="momentum_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, 5) / Ref($close, 20) - 1",
        final_formula="Ref($close, 5) / Ref($close, 20) - 1",
        risk_factors=[],
        market_context_date="2026-03-13"
    )

    spec = note.to_strategy_spec()
    assert "$close" in spec.required_fields

    # mock LLM 初始化，验证 AlignmentChecker 的降级放行逻辑
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM 不可用"))
    with patch("src.agents.prefilter.build_researcher_llm", return_value=mock_llm):
        checker = AlignmentChecker()
        is_aligned, reason = asyncio.run(checker.check(note))

    # LLM 失败时设计上应放行
    assert is_aligned, f"LLM 不可用时应放行，但得到: {reason}"


def test_full_stage2_to_stage3_pipeline():
    """测试完整的 Stage 2 → Stage 3 管道（Validator + NoveltyFilter，跳过 LLM AlignmentChecker）"""
    formulas = [
        "Ref($close, 5) / Ref($close, 20) - 1",
        "Mean($volume, 10) / Mean($volume, 30) - 1",
        "($high - $low) / $close",
    ]
    notes = [
        FactorResearchNote(
            note_id=f"test_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula=formulas[i],
            final_formula=formulas[i],
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]

    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试完整管道"
    )

    # 转换为 canonical objects
    hypotheses = [note.to_hypothesis() for note in batch.notes]
    specs = [note.to_strategy_spec() for note in batch.notes]
    assert len(hypotheses) == len(specs) == 3

    # Stage 3: Validator + NoveltyFilter（不调用 LLM）
    validator = Validator()
    pool = _make_mock_pool([])  # 空历史池
    novelty_filter = NoveltyFilter(pool=pool)

    passed_notes = []
    for note in batch.notes:
        is_valid, _ = validator.validate(note)
        if not is_valid:
            continue

        # 用已通过的 notes 的公式更新 mock pool
        pool.get_island_factors.return_value = [
            {"factor_id": f"p{j}", "formula": p.final_formula}
            for j, p in enumerate(passed_notes)
        ]
        is_novel, _ = novelty_filter.check(note)
        if not is_novel:
            continue

        passed_notes.append(note)

    assert len(passed_notes) == 3, "三个不同公式都应该通过"
    passed_hypotheses = [note.to_hypothesis() for note in passed_notes]
    passed_specs = [note.to_strategy_spec() for note in passed_notes]
    assert len(passed_hypotheses) == len(passed_specs) == 3
