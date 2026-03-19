from typing import Optional, List

from pydantic import Field

from src.schemas import PixiuBase
from src.schemas.hypothesis import Hypothesis, StrategySpec, ExplorationSubspace

class ExplorationQuestion(PixiuBase):
    """Researcher 提出的探索性问题，由 ExplorationAgent 在 Stage 4a 执行"""
    question: str               # 自然语言问题
    suggested_analysis: str     # 建议的分析方式（"correlation", "ic_by_regime", "quantile_return"等）
    required_fields: List[str]  # 需要的数据字段

class FactorResearchNote(PixiuBase):
    # 标识
    note_id: str                # UUID，格式：{island}_{date}_{sequence}
    island: str                 # 所属 Island
    iteration: int              # 本 Island 的第几次迭代

    # 核心内容
    hypothesis: str             # 经济/行为金融直觉（自然语言，100-300字）
    economic_intuition: str     # 为何此因子应该有效
    proposed_formula: str       # 初步 Qlib 公式
    final_formula: Optional[str] = None # 最终公式，探索完成后填入

    # 探索性请求（可选）
    exploration_questions: List[ExplorationQuestion] = Field(default_factory=list)

    # 参数
    universe: str = "csi300"
    holding_period: int = 1      # 持仓天数
    backtest_start: str = "2021-06-01"
    backtest_end: str = "2025-03-31"

    # Regime 基础设施层 — 每个 research note 必须声明 regime 适用性
    applicable_regimes: List[str] = Field(default_factory=list)  # 适用的 regime
    invalid_regimes: List[str] = Field(default_factory=list)     # 失效的 regime
    regime_switch_rule: Optional[str] = None    # regime 切换规则

    # 预期与风险
    expected_ic_min: float = 0.02
    risk_factors: List[str]      # 可能导致失败的因素

    # 元数据
    inspired_by: Optional[str] = None  # 启发来源
    market_context_date: str     # 对应的 MarketContextMemo 日期

    # 状态
    status: str = "draft"  # "draft" | "exploring" | "ready_for_backtest" | "completed"

    # Stage 2 子空间溯源
    exploration_subspace: Optional[ExplorationSubspace] = None  # 生成此 note 的子空间
    mutation_record: Optional[dict] = None                      # 变异记录（如有）

    def to_hypothesis(self) -> Hypothesis:
        """
        将 FactorResearchNote 转换为 Hypothesis
        按照 docs/design/interface-contracts.md §4 Runtime Bridge 设计
        """
        return Hypothesis(
            hypothesis_id=f"hyp_{self.note_id}",
            island=self.island,
            mechanism=self.hypothesis,
            economic_rationale=self.economic_intuition,
            applicable_regimes=self.applicable_regimes,
            invalid_regimes=self.invalid_regimes,
            regime_switch_rule=self.regime_switch_rule,
            inspirations=[self.inspired_by] if self.inspired_by else [],
            failure_priors=self.risk_factors,
            exploration_subspace=self.exploration_subspace,
            mutation_record=self.mutation_record,
        )

    def to_strategy_spec(self, benchmark: str = "SH000300", freq: str = "day") -> StrategySpec:
        """
        将 FactorResearchNote 转换为 StrategySpec
        按照 docs/design/interface-contracts.md §4 Runtime Bridge 设计

        Args:
            benchmark: 基准指数，默认 SH000300（沪深300）
            freq: 频率，默认 day
        """
        # 使用 final_formula 如果存在，否则使用 proposed_formula
        formula = self.final_formula or self.proposed_formula

        # 从公式中提取需要的字段（简单实现）
        required_fields = self._extract_required_fields(formula)

        return StrategySpec(
            spec_id=f"spec_{self.note_id}",
            hypothesis_id=f"hyp_{self.note_id}",
            factor_expression=formula,
            universe=self.universe,
            benchmark=benchmark,
            freq=freq,
            holding_period=self.holding_period,
            required_fields=required_fields,
        )

    def _extract_required_fields(self, formula: str) -> List[str]:
        """从公式中提取需要的数据字段"""
        import re
        # 匹配 $field_name 模式
        fields = re.findall(r'\$(\w+)', formula)
        # 去重并保持顺序
        seen = set()
        unique_fields = []
        for field in fields:
            field_with_dollar = f"${field}"
            if field_with_dollar not in seen:
                seen.add(field_with_dollar)
                unique_fields.append(field_with_dollar)
        return unique_fields if unique_fields else ["$close"]  # 默认至少需要 $close

class SynthesisInsight(PixiuBase):
    """SynthesisAgent 发现的跨 Island 关联"""
    island_a: str
    island_b: str
    note_id_a: str
    note_id_b: str
    relationship: str           # 描述两个假设的关联
    combined_hypothesis: Optional[str]  # 如果值得合并，给出合并假设
    priority: str               # "high" | "medium" | "low"


class AlphaResearcherBatch(PixiuBase):
    """AlphaResearcher 的单次调用输出，包含 2-3 个差异化候选。

    设计原因：单次 LLM 调用生成多个候选，成本几乎等同于单个候选，
    但可显著扩大漏斗入口（从 6 个/轮 提升到 12-18 个/轮），
    使 Stage 3 过滤有实质意义。
    """
    island: str
    notes: List[FactorResearchNote]   # 2-3 个，要求差异化经济逻辑
    generation_rationale: str          # 为何选择这几个方向（供审计）
