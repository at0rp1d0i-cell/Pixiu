"""
测试 Hypothesis 和 StrategySpec schemas
按照 docs/design/interface-contracts.md 和 stage-2-hypothesis-expansion.md 设计
"""
import pytest

pytestmark = pytest.mark.unit

from datetime import datetime

from src.schemas.hypothesis import (
    Hypothesis,
    StrategySpec,
    ExplorationSubspace,
    MutationOperator,
    RegimeCondition,
)


# ─────────────────────────────────────────────────────────
# Hypothesis Schema Tests
# ─────────────────────────────────────────────────────────

def test_hypothesis_minimal():
    """Hypothesis 最小必填字段"""
    h = Hypothesis(
        hypothesis_id="hyp_momentum_001",
        island="momentum",
        mechanism="价格动量延续效应",
        economic_rationale="市场参与者的追涨行为导致短期趋势延续",
    )
    assert h.hypothesis_id == "hyp_momentum_001"
    assert h.island == "momentum"
    assert h.mechanism == "价格动量延续效应"
    assert h.applicable_regimes == []
    assert h.invalid_regimes == []


def test_hypothesis_with_regimes():
    """Hypothesis 包含适用和失效 regime"""
    h = Hypothesis(
        hypothesis_id="hyp_vol_001",
        island="volatility",
        mechanism="波动率均值回归",
        economic_rationale="极端波动后市场趋于平静",
        applicable_regimes=["low_volatility", "stable_market"],
        invalid_regimes=["crisis", "high_volatility"],
    )
    assert "low_volatility" in h.applicable_regimes
    assert "crisis" in h.invalid_regimes


def test_hypothesis_with_inspirations():
    """Hypothesis 包含启发来源"""
    h = Hypothesis(
        hypothesis_id="hyp_nb_001",
        island="northbound",
        mechanism="北向资金流入预示上涨",
        economic_rationale="外资配置需求",
        inspirations=["AlphaAgent论文", "2024年北向资金研究"],
        failure_priors=["节假日前资金回流", "汇率波动期"],
    )
    assert len(h.inspirations) == 2
    assert len(h.failure_priors) == 2


def test_hypothesis_with_candidate_driver():
    """Hypothesis 包含潜在驱动因素"""
    h = Hypothesis(
        hypothesis_id="hyp_val_001",
        island="valuation",
        mechanism="低估值修复",
        economic_rationale="价值回归",
        candidate_driver="市场情绪改善",
    )
    assert h.candidate_driver == "市场情绪改善"


# ─────────────────────────────────────────────────────────
# StrategySpec Schema Tests
# ─────────────────────────────────────────────────────────

def test_strategy_spec_minimal():
    """StrategySpec 最小必填字段"""
    spec = StrategySpec(
        spec_id="spec_001",
        hypothesis_id="hyp_momentum_001",
        factor_expression="Ref($close, -5) / Ref($close, -20) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )
    assert spec.spec_id == "spec_001"
    assert spec.hypothesis_id == "hyp_momentum_001"
    assert "$close" in spec.required_fields


def test_strategy_spec_with_holding_period():
    """StrategySpec 包含持仓周期"""
    spec = StrategySpec(
        spec_id="spec_002",
        hypothesis_id="hyp_vol_001",
        factor_expression="Std($close, 20)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        holding_period=5,
        required_fields=["$close"],
    )
    assert spec.holding_period == 5


def test_strategy_spec_with_parameter_notes():
    """StrategySpec 包含参数说明"""
    spec = StrategySpec(
        spec_id="spec_003",
        hypothesis_id="hyp_momentum_001",
        factor_expression="Mean($close, N) / Mean($close, M) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={
            "N": "短期窗口，建议5-10天",
            "M": "长期窗口，建议20-60天",
        },
    )
    assert "N" in spec.parameter_notes
    assert "M" in spec.parameter_notes


def test_strategy_spec_multiple_fields():
    """StrategySpec 需要多个数据字段"""
    spec = StrategySpec(
        spec_id="spec_004",
        hypothesis_id="hyp_volume_001",
        factor_expression="($volume / Mean($volume, 20) - 1) * ($close / Ref($close, -5) - 1)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close", "$volume"],
    )
    assert len(spec.required_fields) == 2
    assert "$volume" in spec.required_fields


# ─────────────────────────────────────────────────────────
# ExplorationSubspace Tests
# ─────────────────────────────────────────────────────────

def test_exploration_subspace_enum():
    """ExplorationSubspace 枚举值"""
    assert ExplorationSubspace.FACTOR_ALGEBRA == "factor_algebra"
    assert ExplorationSubspace.SYMBOLIC_MUTATION == "symbolic_mutation"
    assert ExplorationSubspace.CROSS_MARKET == "cross_market"
    assert ExplorationSubspace.NARRATIVE_MINING == "narrative_mining"
    # REGIME_CONDITIONAL 已移除 — regime 现在是基础设施层


# ─────────────────────────────────────────────────────────
# MutationOperator Tests
# ─────────────────────────────────────────────────────────

def test_mutation_operator_enum():
    """MutationOperator 枚举值"""
    assert MutationOperator.ADD_OPERATOR == "add_operator"
    assert MutationOperator.REMOVE_OPERATOR == "remove_operator"
    assert MutationOperator.SWAP_HORIZON == "swap_horizon"
    assert MutationOperator.CHANGE_NORMALIZATION == "change_normalization"
    assert MutationOperator.ALTER_INTERACTION == "alter_interaction"


# ─────────────────────────────────────────────────────────
# RegimeCondition Tests
# ─────────────────────────────────────────────────────────

def test_regime_condition_minimal():
    """RegimeCondition 最小字段"""
    regime = RegimeCondition(
        regime_name="bull_market",
        description="牛市环境",
    )
    assert regime.regime_name == "bull_market"
    assert regime.description == "牛市环境"
    assert regime.detection_rule is None


def test_regime_condition_with_detection():
    """RegimeCondition 包含检测规则"""
    regime = RegimeCondition(
        regime_name="high_volatility",
        description="高波动环境",
        detection_rule="Std($close, 20) > threshold",
    )
    assert regime.detection_rule == "Std($close, 20) > threshold"


# ─────────────────────────────────────────────────────────
# Integration: Hypothesis -> StrategySpec
# ─────────────────────────────────────────────────────────

def test_hypothesis_to_strategy_spec_linkage():
    """测试 Hypothesis 到 StrategySpec 的关联"""
    hyp = Hypothesis(
        hypothesis_id="hyp_test_001",
        island="momentum",
        mechanism="短期动量",
        economic_rationale="追涨效应",
    )

    spec = StrategySpec(
        spec_id="spec_test_001",
        hypothesis_id=hyp.hypothesis_id,  # 关联
        factor_expression="Ref($close, -5) / Ref($close, -10) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )

    assert spec.hypothesis_id == hyp.hypothesis_id
    # 验证可以通过 hypothesis_id 追溯到原始假设


def test_one_hypothesis_multiple_specs():
    """一个 Hypothesis 可以对应多个 StrategySpec（不同参数化）"""
    hyp_id = "hyp_momentum_param_test"

    hyp = Hypothesis(
        hypothesis_id=hyp_id,
        island="momentum",
        mechanism="动量效应",
        economic_rationale="趋势延续",
    )

    # 同一假设，不同窗口参数
    spec1 = StrategySpec(
        spec_id="spec_short",
        hypothesis_id=hyp_id,
        factor_expression="Ref($close, -5) / Ref($close, -10) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={"window": "短期5-10天"},
    )

    spec2 = StrategySpec(
        spec_id="spec_long",
        hypothesis_id=hyp_id,
        factor_expression="Ref($close, -20) / Ref($close, -60) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={"window": "长期20-60天"},
    )

    assert spec1.hypothesis_id == spec2.hypothesis_id == hyp_id
    assert spec1.spec_id != spec2.spec_id
