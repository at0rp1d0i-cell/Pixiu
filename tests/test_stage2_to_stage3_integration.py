"""
Stage 2 → Stage 3 集成测试
测试 FactorResearchNote 通过 PreFilter 的完整流程

Tier C: Local Integration
- 不依赖真实 LLM
- 不依赖网络
- 使用 mock 数据验证数据流
"""
import asyncio
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.integration
from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import Hypothesis, StrategySpec
from src.agents.prefilter import Validator, NoveltyFilter, AlignmentChecker


def _make_mock_pool(existing_formulas=None):
    """创建 mock FactorPool，返回指定的历史因子公式"""
    pool = MagicMock()
    factors = [{"factor_id": f"f{i}", "formula": f} for i, f in enumerate(existing_formulas or [])]
    pool.get_island_factors.return_value = factors
    return pool


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
    from unittest.mock import patch, AsyncMock

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
    with patch("src.agents.prefilter.ChatOpenAI") as mock_llm_cls:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM 不可用"))
        mock_llm_cls.return_value = mock_llm

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
