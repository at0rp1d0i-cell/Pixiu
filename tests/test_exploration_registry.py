"""
测试 Exploration Subspace Registry
验证探索子空间的配置和管理
"""
import pytest
from src.schemas.exploration import (
    PrimitiveCategory,
    SubspaceConfig,
    ExplorationStrategy,
    SubspaceRegistry,
)
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator


def test_primitive_category_enum():
    """测试原语类别枚举"""
    assert PrimitiveCategory.PRICE_VOLUME == "price_volume"
    assert PrimitiveCategory.FUNDAMENTAL == "fundamental"
    assert PrimitiveCategory.EVENT_DERIVED == "event_derived"


def test_subspace_config_minimal():
    """测试子空间配置最小字段"""
    config = SubspaceConfig(
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        description="测试配置",
    )
    assert config.subspace == ExplorationSubspace.FACTOR_ALGEBRA
    assert config.enabled is True
    assert config.priority == 1


def test_subspace_config_with_primitives():
    """测试包含原语的配置"""
    config = SubspaceConfig(
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        description="原语空间",
        allowed_primitives=["$close", "$volume", "$open"],
    )
    assert len(config.allowed_primitives) == 3
    assert "$close" in config.allowed_primitives


def test_subspace_config_with_operators():
    """测试包含变异算子的配置"""
    config = SubspaceConfig(
        subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
        description="符号变异",
        allowed_operators=[
            MutationOperator.ADD_OPERATOR,
            MutationOperator.SWAP_HORIZON,
        ],
    )
    assert len(config.allowed_operators) == 2
    assert MutationOperator.ADD_OPERATOR in config.allowed_operators


def test_exploration_strategy():
    """测试探索策略"""
    strategy = ExplorationStrategy(
        strategy_id="strat_001",
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        name="基础原语组合",
        description="使用基础价格和成交量原语",
        max_candidates=5,
        diversity_threshold=0.4,
    )
    assert strategy.strategy_id == "strat_001"
    assert strategy.max_candidates == 5
    assert strategy.diversity_threshold == 0.4


def test_default_registry():
    """测试默认注册表"""
    registry = SubspaceRegistry.get_default_registry()
    
    assert len(registry.configs) == 5
    assert "factor_algebra" in registry.configs
    assert "symbolic_mutation" in registry.configs
    assert "cross_market" in registry.configs
    assert "narrative_mining" in registry.configs
    assert "regime_conditional" in registry.configs


def test_get_enabled_subspaces():
    """测试获取启用的子空间"""
    registry = SubspaceRegistry.get_default_registry()
    enabled = registry.get_enabled_subspaces()
    
    assert len(enabled) == 5
    assert ExplorationSubspace.FACTOR_ALGEBRA in enabled
    assert ExplorationSubspace.SYMBOLIC_MUTATION in enabled


def test_get_subspace_config():
    """测试获取指定子空间配置"""
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.FACTOR_ALGEBRA)
    
    assert config is not None
    assert config.subspace == ExplorationSubspace.FACTOR_ALGEBRA
    assert config.priority == 5
    assert len(config.allowed_primitives) > 0


def test_get_subspaces_for_island_all():
    """测试获取适用于所有 Island 的子空间"""
    registry = SubspaceRegistry.get_default_registry()
    subspaces = registry.get_subspaces_for_island("momentum")
    
    # 默认配置中所有子空间都适用于所有 Island
    assert len(subspaces) == 5


def test_get_subspaces_for_island_specific():
    """测试获取特定 Island 的子空间"""
    registry = SubspaceRegistry.get_default_registry()
    
    # 修改配置，使某个子空间只适用于特定 Island
    registry.configs["factor_algebra"].applicable_islands = ["momentum", "volatility"]
    
    subspaces_momentum = registry.get_subspaces_for_island("momentum")
    subspaces_valuation = registry.get_subspaces_for_island("valuation")
    
    assert ExplorationSubspace.FACTOR_ALGEBRA in subspaces_momentum
    assert ExplorationSubspace.FACTOR_ALGEBRA not in subspaces_valuation


def test_get_sorted_subspaces():
    """测试按优先级排序的子空间"""
    registry = SubspaceRegistry.get_default_registry()
    sorted_subspaces = registry.get_sorted_subspaces()
    
    # 应该按优先级降序排列
    assert len(sorted_subspaces) == 5
    assert sorted_subspaces[0] == ExplorationSubspace.FACTOR_ALGEBRA  # priority=5
    assert sorted_subspaces[1] == ExplorationSubspace.SYMBOLIC_MUTATION  # priority=4


def test_get_sorted_subspaces_for_island():
    """测试获取特定 Island 的排序子空间"""
    registry = SubspaceRegistry.get_default_registry()
    
    # 修改配置 - 为所有子空间设置 applicable_islands，这样只有指定的会被返回
    registry.configs["factor_algebra"].applicable_islands = ["momentum"]
    registry.configs["symbolic_mutation"].applicable_islands = ["momentum"]
    registry.configs["cross_market"].applicable_islands = ["valuation"]
    registry.configs["narrative_mining"].applicable_islands = ["valuation"]
    registry.configs["regime_conditional"].applicable_islands = ["volatility"]
    
    sorted_subspaces = registry.get_sorted_subspaces(island="momentum")
    
    assert len(sorted_subspaces) == 2
    assert sorted_subspaces[0] == ExplorationSubspace.FACTOR_ALGEBRA
    assert sorted_subspaces[1] == ExplorationSubspace.SYMBOLIC_MUTATION


def test_disable_subspace():
    """测试禁用子空间"""
    registry = SubspaceRegistry.get_default_registry()
    
    # 禁用一个子空间
    registry.configs["cross_market"].enabled = False
    
    enabled = registry.get_enabled_subspaces()
    assert len(enabled) == 4
    assert ExplorationSubspace.CROSS_MARKET not in enabled


def test_subspace_config_source_markets():
    """测试跨市场配置"""
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.CROSS_MARKET)
    
    assert config is not None
    assert "US" in config.source_markets
    assert "HK" in config.source_markets


def test_subspace_config_narrative_sources():
    """测试叙事来源配置"""
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.NARRATIVE_MINING)
    
    assert config is not None
    assert "policy" in config.narrative_sources
    assert "industry" in config.narrative_sources


def test_subspace_config_regime_types():
    """测试 Regime 类型配置"""
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.REGIME_CONDITIONAL)
    
    assert config is not None
    assert "bull" in config.regime_types
    assert "bear" in config.regime_types
    assert "crisis" in config.regime_types
