"""
Exploration schemas
包含 Stage 4a 的 ExplorationRequest/Result（原有）
和 Stage 2 的 Exploration Subspace Registry（新增）
"""
from typing import List, Dict, Optional, Any
from enum import Enum
from src.schemas import PixiuBase
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator
from src.schemas.research_note import ExplorationQuestion


# ─────────────────────────────────────────────────────────
# Stage 4a: Exploration Request/Result (原有类，保持兼容)
# ─────────────────────────────────────────────────────────

class ExplorationRequest(PixiuBase):
    request_id: str             # UUID
    note_id: str                # 对应的 FactorResearchNote
    question: ExplorationQuestion
    data_fields: List[str]      # 实际需要从 Qlib 加载的字段


class ExplorationResult(PixiuBase):
    request_id: str
    note_id: str
    success: bool
    script_used: str            # ExplorationAgent 生成的 Python 脚本（审计用）
    findings: str               # 自然语言总结（给 Researcher 读）
    key_statistics: Dict[str, Any]  # 关键统计数值（IC、相关性等）
    refined_formula_suggestion: Optional[str] = None # 基于探索结果建议的公式修正
    error_message: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Stage 2: Exploration Subspace Registry (新增)
# ─────────────────────────────────────────────────────────

class PrimitiveCategory(str, Enum):
    """数据原语类别（用于 Factor Algebra Search）"""
    PRICE_VOLUME = "price_volume"
    FUNDAMENTAL = "fundamental"
    EVENT_DERIVED = "event_derived"
    TEMPORAL_TRANSFORM = "temporal_transform"
    CROSS_SECTIONAL = "cross_sectional"
    REGIME_SWITCH = "regime_switch"


class SubspaceConfig(PixiuBase):
    """探索子空间配置"""
    subspace: ExplorationSubspace
    enabled: bool = True
    priority: int = 1
    description: str
    applicable_islands: List[str] = []
    allowed_primitives: List[str] = []
    allowed_operators: List[MutationOperator] = []
    source_markets: List[str] = []
    narrative_sources: List[str] = []
    regime_types: List[str] = []


class ExplorationStrategy(PixiuBase):
    """探索策略 - 定义如何在子空间中搜索"""
    strategy_id: str
    subspace: ExplorationSubspace
    name: str
    description: str
    max_candidates: int = 3
    diversity_threshold: float = 0.3
    required_context: List[str] = []
    forbidden_patterns: List[str] = []


class SubspaceRegistry(PixiuBase):
    """探索子空间注册表 - 管理所有子空间配置"""
    configs: Dict[str, SubspaceConfig] = {}
    strategies: Dict[str, ExplorationStrategy] = {}

    @classmethod
    def get_default_registry(cls) -> "SubspaceRegistry":
        """获取默认注册表配置"""
        configs = {
            "factor_algebra": SubspaceConfig(
                subspace=ExplorationSubspace.FACTOR_ALGEBRA,
                enabled=True,
                priority=5,
                description="原语空间搜索 - 基于受约束的数据原语组合",
                allowed_primitives=["$close", "$open", "$high", "$low", "$volume", "$vwap", "$amount", "$turn", "$factor"],
            ),
            "symbolic_mutation": SubspaceConfig(
                subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
                enabled=True,
                priority=4,
                description="符号变异 - 对现有因子进行结构化变异",
                allowed_operators=[MutationOperator.ADD_OPERATOR, MutationOperator.SWAP_HORIZON, MutationOperator.CHANGE_NORMALIZATION],
            ),
            "cross_market": SubspaceConfig(
                subspace=ExplorationSubspace.CROSS_MARKET,
                enabled=True,
                priority=3,
                description="跨市场模式挖掘 - 从其他市场迁移机制",
                source_markets=["US", "HK", "crypto"],
            ),
            "narrative_mining": SubspaceConfig(
                subspace=ExplorationSubspace.NARRATIVE_MINING,
                enabled=True,
                priority=3,
                description="经济叙事挖掘 - 从政策、产业链等叙事中抽取机制",
                narrative_sources=["policy", "industry", "macro"],
            ),
            "regime_conditional": SubspaceConfig(
                subspace=ExplorationSubspace.REGIME_CONDITIONAL,
                enabled=True,
                priority=2,
                description="Regime 条件因子 - 只在特定市场环境下有效的因子",
                regime_types=["bull", "bear", "high_vol", "low_vol", "crisis"],
            ),
        }
        return cls(configs=configs, strategies={})

    def get_enabled_subspaces(self) -> List[ExplorationSubspace]:
        """获取所有启用的子空间"""
        return [config.subspace for config in self.configs.values() if config.enabled]

    def get_subspace_config(self, subspace: ExplorationSubspace) -> Optional[SubspaceConfig]:
        """获取指定子空间的配置"""
        return self.configs.get(subspace.value)

    def get_subspaces_for_island(self, island: str) -> List[ExplorationSubspace]:
        """获取适用于指定 Island 的子空间"""
        result = []
        for config in self.configs.values():
            if not config.enabled:
                continue
            if not config.applicable_islands or island in config.applicable_islands:
                result.append(config.subspace)
        return result

    def get_sorted_subspaces(self, island: Optional[str] = None) -> List[ExplorationSubspace]:
        """获取按优先级排序的子空间"""
        if island:
            subspaces = self.get_subspaces_for_island(island)
            configs = [self.configs[s.value] for s in subspaces]
        else:
            configs = [c for c in self.configs.values() if c.enabled]
        sorted_configs = sorted(configs, key=lambda c: c.priority, reverse=True)
        return [c.subspace for c in sorted_configs]
