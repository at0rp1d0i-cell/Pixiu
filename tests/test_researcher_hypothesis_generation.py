"""
测试 FactorResearchNote 到 Hypothesis/StrategySpec 的转换
这些转换方法已经在 test_research_note_methods.py 中测试过
这里测试 AlphaResearcher 生成的 notes 可以正确转换
"""
import pytest
from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import Hypothesis, StrategySpec


def test_research_note_to_hypothesis():
    """测试 FactorResearchNote 可以转换为 Hypothesis"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转", "流动性枯竭"],
        inspired_by="AlphaAgent论文",
        market_context_date="2026-03-13"
    )
    
    hypothesis = note.to_hypothesis()
    
    assert isinstance(hypothesis, Hypothesis)
    assert hypothesis.hypothesis_id == f"hyp_{note.note_id}"
    assert hypothesis.island == "momentum"
    assert hypothesis.mechanism == "短期价格动量延续效应"
    assert hypothesis.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hypothesis.inspirations
    assert "市场反转" in hypothesis.failure_priors


def test_research_note_to_strategy_spec():
    """测试 FactorResearchNote 可以转换为 StrategySpec"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-13"
    )
    
    spec = note.to_strategy_spec()
    
    assert isinstance(spec, StrategySpec)
    assert spec.spec_id == f"spec_{note.note_id}"
    assert spec.hypothesis_id == f"hyp_{note.note_id}"
    assert spec.factor_expression == "Ref($close, -5) / Ref($close, -20) - 1"
    assert "$close" in spec.required_fields


def test_batch_notes_to_hypotheses():
    """测试 AlphaResearcherBatch 中的所有 notes 可以转换为 Hypotheses"""
    notes = [
        FactorResearchNote(
            note_id=f"momentum_001_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"动量效应{i}",
            economic_intuition=f"原理{i}",
            proposed_formula="$close",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]
    
    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试批量生成"
    )
    
    # 转换所有 notes 为 hypotheses
    hypotheses = [note.to_hypothesis() for note in batch.notes]
    
    assert len(hypotheses) == 3
    assert all(isinstance(h, Hypothesis) for h in hypotheses)
    assert all(h.island == "momentum" for h in hypotheses)
    assert hypotheses[0].mechanism == "动量效应0"
    assert hypotheses[1].mechanism == "动量效应1"
    assert hypotheses[2].mechanism == "动量效应2"


def test_batch_notes_to_strategy_specs():
    """测试 AlphaResearcherBatch 中的所有 notes 可以转换为 StrategySpecs"""
    notes = [
        FactorResearchNote(
            note_id=f"vol_001_{i}",
            island="volatility",
            iteration=1,
            hypothesis=f"波动率假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula=f"Std($close, {10 + i * 5})",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]
    
    batch = AlphaResearcherBatch(
        island="volatility",
        notes=notes,
        generation_rationale="测试批量生成"
    )
    
    # 转换所有 notes 为 strategy specs
    specs = [note.to_strategy_spec() for note in batch.notes]
    
    assert len(specs) == 3
    assert all(isinstance(s, StrategySpec) for s in specs)
    assert specs[0].factor_expression == "Std($close, 10)"
    assert specs[1].factor_expression == "Std($close, 15)"
    assert specs[2].factor_expression == "Std($close, 20)"


def test_hypothesis_strategy_spec_linkage_in_batch():
    """测试 batch 中 Hypothesis 和 StrategySpec 的关联关系"""
    notes = [
        FactorResearchNote(
            note_id=f"test_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula="$close",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(2)
    ]
    
    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试"
    )
    
    # 为每个 note 生成 hypothesis 和 spec
    pairs = [(note.to_hypothesis(), note.to_strategy_spec()) for note in batch.notes]
    
    # 验证每对的关联关系
    for hyp, spec in pairs:
        assert spec.hypothesis_id == hyp.hypothesis_id
        assert hyp.hypothesis_id.startswith("hyp_")
        assert spec.spec_id.startswith("spec_")


def test_multi_island_batch_conversion():
    """测试多个 Island 的 notes 转换"""
    islands = ["momentum", "volatility", "valuation"]
    all_notes = []
    
    for island in islands:
        for i in range(2):
            note = FactorResearchNote(
                note_id=f"{island}_{i}",
                island=island,
                iteration=1,
                hypothesis=f"{island}假设{i}",
                economic_intuition=f"{island}原理{i}",
                proposed_formula="$close",
                risk_factors=[],
                market_context_date="2026-03-13"
            )
            all_notes.append(note)
    
    # 转换所有 notes
    hypotheses = [note.to_hypothesis() for note in all_notes]
    specs = [note.to_strategy_spec() for note in all_notes]
    
    assert len(hypotheses) == 6
    assert len(specs) == 6
    
    # 验证每个 island 都有对应的 hypotheses
    for island in islands:
        island_hyps = [h for h in hypotheses if h.island == island]
        assert len(island_hyps) == 2


def test_note_with_final_formula_conversion():
    """测试包含 final_formula 的 note 转换"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        final_formula="Rank($close)",  # 有 final_formula
        risk_factors=[],
        market_context_date="2026-03-13"
    )
    
    spec = note.to_strategy_spec()
    
    # 应该使用 final_formula 而不是 proposed_formula
    assert spec.factor_expression == "Rank($close)"
