"""
Hypothesis 和 StrategySpec schemas
按照 docs/design/interface-contracts.md 和 stage-2-hypothesis-expansion.md 设计

Hypothesis: 回答"为什么值得测"
StrategySpec: 回答"到底测什么"
"""
from typing import Optional, List, Dict
from enum import Enum
from src.schemas import PixiuBase


class ExplorationSubspace(str, Enum):
    """四个探索子空间 — Regime 已升级为基础设施层，不再作为独立子空间"""
    FACTOR_ALGEBRA = "factor_algebra"           # 原语空间搜索
    SYMBOLIC_MUTATION = "symbolic_mutation"     # 符号变异
    CROSS_MARKET = "cross_market"               # 跨市场模式挖掘
    NARRATIVE_MINING = "narrative_mining"       # 经济叙事挖掘


class MutationOperator(str, Enum):
    """符号变异算子（docs/design/stage-2-hypothesis-expansion.md §4.2）"""
    ADD_OPERATOR = "add_operator"               # 添加算子
    REMOVE_OPERATOR = "remove_operator"         # 移除算子
    SWAP_HORIZON = "swap_horizon"               # 交换时间窗口
    CHANGE_NORMALIZATION = "change_normalization"  # 改变归一化方式
    ALTER_INTERACTION = "alter_interaction"     # 改变交互项


class RegimeCondition(PixiuBase):
    """Regime 条件表达"""
    regime_name: str                            # regime 名称
    description: str                            # 描述
    detection_rule: Optional[str] = None        # 检测规则（可选）


class Hypothesis(PixiuBase):
    """
    表达市场机制假设、适用/失效 regime、启发来源
    回答"为什么值得测"

    设计来源：docs/design/interface-contracts.md §3
    """
    hypothesis_id: str                          # 唯一标识
    island: str                                 # 所属 Island
    mechanism: str                              # 市场机制描述
    economic_rationale: str                     # 经济学原理

    # Regime 基础设施层 — 每个 hypothesis 必须声明 regime 适用性
    applicable_regimes: List[str] = []          # 适用的 regime（如 bull, low_vol）
    invalid_regimes: List[str] = []             # 失效的 regime（如 crisis, bear）
    regime_switch_rule: Optional[str] = None    # regime 切换规则（如何判断进入/退出）

    # 可选字段
    candidate_driver: Optional[str] = None      # 潜在驱动因素
    inspirations: List[str] = []                # 启发来源
    failure_priors: List[str] = []              # 已知失败前提


class StrategySpec(PixiuBase):
    """
    表达可执行因子语义与参数边界
    回答"到底测什么"

    设计来源：docs/design/interface-contracts.md §3
    """
    spec_id: str                                # 唯一标识
    hypothesis_id: str                          # 关联的 Hypothesis
    factor_expression: str                      # 因子表达式（Qlib 格式）
    universe: str                               # 股票池
    benchmark: str                              # 基准
    freq: str                                   # 频率（day/week/month）
    required_fields: List[str]                  # 需要的数据字段

    # 可选字段
    holding_period: Optional[int] = None        # 持仓周期（天）
    parameter_notes: Dict[str, str] = {}        # 参数说明
