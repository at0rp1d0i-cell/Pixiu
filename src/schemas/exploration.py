"""
Exploration schemas
包含 Stage 4a 的 ExplorationRequest/Result（原有）
和 Stage 2 的 Exploration Subspace Registry（新增）
"""
from typing import List, Dict, Optional, Any
from enum import Enum
from pydantic import Field
from src.formula.capabilities import (
    BASE_FIELD_SPECS,
    EXPERIMENTAL_FIELD_SPECS,
    FormulaCapabilities,
    OPERATOR_SPECS_BY_NAME,
    get_runtime_formula_capabilities,
)
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


_OPERATOR_CATEGORY_MAP = {
    "temporal_transform": PrimitiveCategory.TEMPORAL_TRANSFORM,
    "cross_sectional": PrimitiveCategory.CROSS_SECTIONAL,
    "math": PrimitiveCategory.TEMPORAL_TRANSFORM,
    "logic": PrimitiveCategory.TEMPORAL_TRANSFORM,
}


class FactorPrimitive(PixiuBase):
    """因子原语 — Factor Algebra Search 的最小构建块"""
    name: str                                      # 原语名称（如 "$close"）
    category: PrimitiveCategory                    # 所属类别
    qlib_syntax: str                               # Qlib 表达式片段
    description: str                               # 中文说明


class MarketMechanismTemplate(PixiuBase):
    """跨市场机制模板 — Cross-Market Pattern Mining 的逻辑骨架"""
    name: str                                      # 模板名称
    source_market: str                             # 来源市场（US/HK/commodity/rates）
    transmission_path: str                         # 传导路径描述
    skeleton: str                                  # 逻辑骨架（可适配 A 股的抽象表达）


class NarrativeCategory(PixiuBase):
    """叙事类别 — Narrative Mining 的抽取框架"""
    category: str                                  # 类别名称
    extraction_targets: List[str]                  # 抽取目标列表
    example_patterns: List[str]                    # 示例模式


class MutationRecord(PixiuBase):
    """变异记录 — Symbolic Mutation 的审计追踪"""
    source_factor_id: str                          # 源因子 ID
    operator: MutationOperator                     # 使用的变异算子
    parameter_change: str                          # 参数变更描述
    result_formula: str                            # 变异后的公式


class SubspaceConfig(PixiuBase):
    """探索子空间配置"""
    subspace: ExplorationSubspace
    enabled: bool = True
    priority: int = 1
    description: str
    applicable_islands: List[str] = Field(default_factory=list)
    allowed_primitives: List[str] = Field(default_factory=list)
    allowed_operators: List[MutationOperator] = Field(default_factory=list)
    source_markets: List[str] = Field(default_factory=list)
    narrative_sources: List[str] = Field(default_factory=list)
    regime_types: List[str] = Field(default_factory=list)


class ExplorationStrategy(PixiuBase):
    """探索策略 - 定义如何在子空间中搜索"""
    strategy_id: str
    subspace: ExplorationSubspace
    name: str
    description: str
    max_candidates: int = 3
    diversity_threshold: float = 0.3
    required_context: List[str] = Field(default_factory=list)
    forbidden_patterns: List[str] = Field(default_factory=list)


class CompositionConstraints(PixiuBase):
    """因子代数组合约束 — 控制组合深度和禁止模式"""
    max_nesting_depth: int = 4
    max_total_operators: int = 8
    forbidden_patterns: List[str] = Field(default_factory=list)  # 动态填充，来自 FailureConstraint hard patterns


class SubspaceRegistry(PixiuBase):
    """探索子空间注册表 - 管理所有子空间配置和结构化上下文"""
    configs: Dict[str, SubspaceConfig] = Field(default_factory=dict)
    strategies: Dict[str, ExplorationStrategy] = Field(default_factory=dict)
    primitives: List[FactorPrimitive] = Field(default_factory=list)
    mechanism_templates: List[MarketMechanismTemplate] = Field(default_factory=list)
    narrative_categories: List[NarrativeCategory] = Field(default_factory=list)
    composition_constraints: CompositionConstraints = Field(default_factory=CompositionConstraints)

    @classmethod
    def get_default_registry(
        cls,
        capabilities: Optional[FormulaCapabilities] = None,
    ) -> "SubspaceRegistry":
        """获取默认注册表配置（含原语词汇表、机制模板、叙事类别）"""
        capabilities = capabilities or get_runtime_formula_capabilities()
        available_fields = set(capabilities.available_fields)
        available_field_specs = [
            spec
            for spec in BASE_FIELD_SPECS + EXPERIMENTAL_FIELD_SPECS
            if spec.formula_name in available_fields
        ]

        configs = {
            "factor_algebra": SubspaceConfig(
                subspace=ExplorationSubspace.FACTOR_ALGEBRA,
                enabled=True,
                priority=5,
                description="原语空间搜索 - 基于受约束的数据原语组合",
                allowed_primitives=list(available_fields),
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
        }

        # ── 因子原语词汇表（15+ 个） ──
        primitives = [
            FactorPrimitive(
                name=spec.formula_name,
                category=(
                    PrimitiveCategory.PRICE_VOLUME
                    if spec.category == "price_volume"
                    else PrimitiveCategory.FUNDAMENTAL
                ),
                qlib_syntax=spec.formula_name,
                description=spec.description,
            )
            for spec in available_field_specs
        ] + [
            FactorPrimitive(
                name=spec.name,
                category=_OPERATOR_CATEGORY_MAP.get(spec.category, PrimitiveCategory.TEMPORAL_TRANSFORM),
                qlib_syntax=spec.qlib_syntax,
                description=spec.description,
            )
            for spec in (
                OPERATOR_SPECS_BY_NAME["Ref"],
                OPERATOR_SPECS_BY_NAME["Mean"],
                OPERATOR_SPECS_BY_NAME["Std"],
                OPERATOR_SPECS_BY_NAME["Corr"],
                OPERATOR_SPECS_BY_NAME["Rank"],
                OPERATOR_SPECS_BY_NAME["Max"],
                OPERATOR_SPECS_BY_NAME["Min"],
                OPERATOR_SPECS_BY_NAME["Delta"],
            )
        ]

        # ── 跨市场机制模板（5+ 个） ──
        mechanism_templates = [
            MarketMechanismTemplate(
                name="库存周期传导",
                source_market="commodity",
                transmission_path="上游库存 → 中游成本 → 下游利润",
                skeleton="当上游库存处于 {regime} 时，中游 {sector} 的利润率变化领先股价 {lag} 个交易日",
            ),
            MarketMechanismTemplate(
                name="利率敏感度分层",
                source_market="US",
                transmission_path="联储利率 → 久期敏感资产 → 成长/价值轮动",
                skeleton="利率变动 {direction} 时，高久期资产（成长股）相对低久期资产（价值股）的超额收益 {sign}",
            ),
            MarketMechanismTemplate(
                name="波动率溢价收割",
                source_market="US",
                transmission_path="隐含波动率 → 已实现波动率 → 波动率风险溢价",
                skeleton="当 IV-RV spread 处于 {quantile} 分位时，做空波动率策略的 Sharpe 为 {range}",
            ),
            MarketMechanismTemplate(
                name="资金流跨市场传导",
                source_market="HK",
                transmission_path="北向资金 → A 股行业配置 → 个股超额",
                skeleton="北向资金连续 {N} 日净流入 {sector} 时，该行业未来 {horizon} 日超额收益显著",
            ),
            MarketMechanismTemplate(
                name="动量溢出效应",
                source_market="US",
                transmission_path="美股行业动量 → A 股对标行业 → 滞后跟随",
                skeleton="美股 {sector} 过去 {lookback} 日涨幅 top decile 时，A 股对标行业未来 {horizon} 日有正超额",
            ),
            MarketMechanismTemplate(
                name="汇率-出口链传导",
                source_market="rates",
                transmission_path="人民币汇率 → 出口企业利润 → 股价反应",
                skeleton="人民币贬值 {magnitude} 后，出口占比高的企业未来 {horizon} 日超额收益为正",
            ),
        ]

        # ── 叙事类别（4 个） ──
        narrative_categories = [
            NarrativeCategory(
                category="政策口径",
                extraction_targets=["产业政策方向", "监管态度变化", "财政/货币政策信号"],
                example_patterns=["国常会提及'新质生产力'→科技板块预期升温", "央行MLF缩量→流动性收紧预期"],
            ),
            NarrativeCategory(
                category="产业链叙事",
                extraction_targets=["供需格局变化", "技术突破节点", "产能周期拐点"],
                example_patterns=["光伏硅料产能过剩→组件降价→下游装机需求释放", "AI算力需求→光模块供不应求"],
            ),
            NarrativeCategory(
                category="预期错位",
                extraction_targets=["一致预期与现实偏差", "卖方预期修正方向", "事件冲击后的过度/不足反应"],
                example_patterns=["市场一致预期降息但央行按兵不动→利率敏感股回调", "业绩超预期但股价不涨→隐含利空"],
            ),
            NarrativeCategory(
                category="公告语言风格",
                extraction_targets=["管理层措辞变化", "风险提示密度", "前瞻指引语气"],
                example_patterns=["年报中'审慎'出现频率上升→盈利下修概率增加", "回购公告密集→底部信号"],
            ),
        ]

        return cls(
            configs=configs,
            strategies={},
            primitives=primitives,
            mechanism_templates=mechanism_templates,
            narrative_categories=narrative_categories,
        )

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
