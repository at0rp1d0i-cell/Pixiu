"""
测试 FactorResearchNote 与 Hypothesis/StrategySpec 的桥接关系
按照 docs/design/interface-contracts.md §4 Runtime Bridge 设计
"""
import pytest

pytestmark = pytest.mark.unit

from src.schemas.research_note import FactorResearchNote, ExplorationQuestion
from src.schemas.hypothesis import Hypothesis, StrategySpec


def test_factor_research_note_to_hypothesis():
    """测试从 FactorResearchNote 提取 Hypothesis"""
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

    # 从 note 提取 Hypothesis
    hypothesis = Hypothesis(
        hypothesis_id=f"hyp_{note.note_id}",
        island=note.island,
        mechanism=note.hypothesis,
        economic_rationale=note.economic_intuition,
        inspirations=[note.inspired_by] if note.inspired_by else [],
        failure_priors=note.risk_factors,
    )

    assert hypothesis.hypothesis_id == "hyp_momentum_20260313_001"
    assert hypothesis.island == "momentum"
    assert hypothesis.mechanism == "价格动量延续效应"
    assert hypothesis.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hypothesis.inspirations
    assert "市场反转" in hypothesis.failure_priors


def test_factor_research_note_to_strategy_spec():
    """测试从 FactorResearchNote 提取 StrategySpec"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        final_formula="Ref($close, -5) / Ref($close, -20) - 1",
        universe="csi300",
        holding_period=5,
        risk_factors=["市场反转"],
        market_context_date="2026-03-13",
    )

    # 从 note 提取 StrategySpec
    spec = StrategySpec(
        spec_id=f"spec_{note.note_id}",
        hypothesis_id=f"hyp_{note.note_id}",
        factor_expression=note.final_formula or note.proposed_formula,
        universe=note.universe,
        benchmark="SH000300",  # 默认基准
        freq="day",  # 默认频率
        holding_period=note.holding_period,
        required_fields=["$close"],  # 从公式中提取
    )

    assert spec.spec_id == "spec_momentum_20260313_001"
    assert spec.hypothesis_id == "hyp_momentum_20260313_001"
    assert spec.factor_expression == "Ref($close, -5) / Ref($close, -20) - 1"
    assert spec.universe == "csi300"
    assert spec.holding_period == 5


def test_note_with_exploration_questions():
    """测试包含探索性问题的 note"""
    note = FactorResearchNote(
        note_id="vol_20260313_001",
        island="volatility",
        iteration=1,
        hypothesis="波动率均值回归",
        economic_intuition="极端波动后市场趋于平静",
        proposed_formula="Std($close, 20)",
        exploration_questions=[
            ExplorationQuestion(
                question="波动率在不同市场环境下的表现如何？",
                suggested_analysis="ic_by_regime",
                required_fields=["$close", "$volume"],
            )
        ],
        risk_factors=["持续高波动"],
        market_context_date="2026-03-13",
    )

    assert len(note.exploration_questions) == 1
    assert note.exploration_questions[0].suggested_analysis == "ic_by_regime"
    assert note.status == "draft"


def test_note_lifecycle_status():
    """测试 note 的生命周期状态"""
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    # 初始状态
    assert note.status == "draft"

    # 模拟状态转换
    note.status = "exploring"
    assert note.status == "exploring"

    note.final_formula = "$close / Ref($close, -1) - 1"
    note.status = "ready_for_backtest"
    assert note.status == "ready_for_backtest"
    assert note.final_formula is not None


def test_bridge_preserves_all_information():
    """测试桥接过程不丢失信息"""
    note = FactorResearchNote(
        note_id="complete_001",
        island="valuation",
        iteration=2,
        hypothesis="低估值修复",
        economic_intuition="价值回归原理",
        proposed_formula="$pe_ratio",
        final_formula="1 / $pe_ratio",
        universe="csi300",
        holding_period=10,
        backtest_start="2021-06-01",
        backtest_end="2025-03-31",
        expected_ic_min=0.03,
        risk_factors=["估值陷阱", "行业轮动"],
        inspired_by="价值投资理论",
        market_context_date="2026-03-13",
        status="ready_for_backtest",
    )

    # 提取 Hypothesis
    hyp = Hypothesis(
        hypothesis_id=f"hyp_{note.note_id}",
        island=note.island,
        mechanism=note.hypothesis,
        economic_rationale=note.economic_intuition,
        inspirations=[note.inspired_by] if note.inspired_by else [],
        failure_priors=note.risk_factors,
    )

    # 提取 StrategySpec
    spec = StrategySpec(
        spec_id=f"spec_{note.note_id}",
        hypothesis_id=hyp.hypothesis_id,
        factor_expression=note.final_formula or note.proposed_formula,
        universe=note.universe,
        benchmark="SH000300",
        freq="day",
        holding_period=note.holding_period,
        required_fields=["$pe_ratio"],
    )

    # 验证信息完整性
    assert hyp.mechanism == note.hypothesis
    assert hyp.economic_rationale == note.economic_intuition
    assert spec.factor_expression == note.final_formula
    assert spec.holding_period == note.holding_period
    assert len(hyp.failure_priors) == len(note.risk_factors)
