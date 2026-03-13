"""
测试 FactorResearchNote 的辅助方法
验证 to_hypothesis() 和 to_strategy_spec() 方法
"""
import pytest
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion


def test_to_hypothesis_method():
    """测试 to_hypothesis() 方法"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转", "流动性枯竭"],
        inspired_by="AlphaAgent论文",
        market_context_date="2026-03-13",
    )

    hyp = note.to_hypothesis()

    assert hyp.hypothesis_id == "hyp_momentum_20260313_001"
    assert hyp.island == "momentum"
    assert hyp.mechanism == "价格动量延续效应"
    assert hyp.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hyp.inspirations
    assert "市场反转" in hyp.failure_priors
    assert "流动性枯竭" in hyp.failure_priors


def test_to_strategy_spec_method():
    """测试 to_strategy_spec() 方法"""
    note = FactorResearchNote(
        note_id="vol_20260313_001",
        island="volatility",
        iteration=1,
        hypothesis="波动率均值回归",
        economic_intuition="极端波动后市场趋于平静",
        proposed_formula="Std($close, 20)",
        final_formula="Std($close, 20) / Mean(Std($close, 20), 60)",
        universe="csi300",
        holding_period=5,
        risk_factors=["持续高波动"],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec()

    assert spec.spec_id == "spec_vol_20260313_001"
    assert spec.hypothesis_id == "hyp_vol_20260313_001"
    assert spec.factor_expression == "Std($close, 20) / Mean(Std($close, 20), 60)"
    assert spec.universe == "csi300"
    assert spec.benchmark == "SH000300"
    assert spec.freq == "day"
    assert spec.holding_period == 5
    assert "$close" in spec.required_fields


def test_to_strategy_spec_uses_proposed_formula_when_no_final():
    """测试当没有 final_formula 时使用 proposed_formula"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close / Ref($close, -1) - 1",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec()

    assert spec.factor_expression == "$close / Ref($close, -1) - 1"
    assert "$close" in spec.required_fields


def test_extract_required_fields_single_field():
    """测试提取单个字段"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="Ref($close, -5)",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]


def test_extract_required_fields_multiple_fields():
    """测试提取多个字段"""
    note = FactorResearchNote(
        note_id="test_001",
        island="volume",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="($volume / Mean($volume, 20)) * ($close / Ref($close, -5))",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert "$volume" in fields
    assert "$close" in fields
    assert len(fields) == 2


def test_extract_required_fields_deduplication():
    """测试字段去重"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="$close / Ref($close, -1) + Ref($close, -5)",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]  # 去重后只有一个


def test_extract_required_fields_no_fields():
    """测试没有字段时返回默认值"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="1 + 1",  # 没有字段
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]  # 默认返回 $close


def test_to_strategy_spec_custom_benchmark():
    """测试自定义基准"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="$close",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec(benchmark="SH000905", freq="week")

    assert spec.benchmark == "SH000905"
    assert spec.freq == "week"


def test_note_without_inspired_by():
    """测试没有 inspired_by 的情况"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        risk_factors=["风险1"],
        market_context_date="2026-03-13",
    )

    hyp = note.to_hypothesis()

    assert hyp.inspirations == []
    assert len(hyp.failure_priors) == 1


def test_round_trip_conversion():
    """测试完整的转换流程"""
    # 创建原始 note
    note = FactorResearchNote(
        note_id="complete_001",
        island="valuation",
        iteration=2,
        hypothesis="低估值修复",
        economic_intuition="价值回归原理",
        proposed_formula="1 / $pe_ratio",
        final_formula="Rank(1 / $pe_ratio)",
        universe="csi300",
        holding_period=10,
        risk_factors=["估值陷阱", "行业轮动"],
        inspired_by="价值投资理论",
        market_context_date="2026-03-13",
    )

    # 转换为 Hypothesis 和 StrategySpec
    hyp = note.to_hypothesis()
    spec = note.to_strategy_spec()

    # 验证关联关系
    assert spec.hypothesis_id == hyp.hypothesis_id
    assert hyp.hypothesis_id == f"hyp_{note.note_id}"
    assert spec.spec_id == f"spec_{note.note_id}"

    # 验证信息完整性
    assert hyp.mechanism == note.hypothesis
    assert hyp.economic_rationale == note.economic_intuition
    assert spec.factor_expression == note.final_formula
    assert spec.holding_period == note.holding_period
