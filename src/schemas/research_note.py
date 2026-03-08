from typing import Optional, List
from src.schemas import PixiuBase

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
    exploration_questions: List[ExplorationQuestion] = []  

    # 参数
    universe: str = "csi300"
    holding_period: int = 1      # 持仓天数
    backtest_start: str = "2021-06-01"
    backtest_end: str = "2025-03-31"

    # 预期与风险
    expected_ic_min: float = 0.02
    risk_factors: List[str]      # 可能导致失败的因素

    # 元数据
    inspired_by: Optional[str] = None  # 启发来源
    market_context_date: str     # 对应的 MarketContextMemo 日期

    # 状态
    status: str = "draft"  # "draft" | "exploring" | "ready_for_backtest" | "completed"

class SynthesisInsight(PixiuBase):
    """SynthesisAgent 发现的跨 Island 关联"""
    island_a: str
    island_b: str
    note_id_a: str
    note_id_b: str
    relationship: str           # 描述两个假设的关联
    combined_hypothesis: Optional[str]  # 如果值得合并，给出合并假设
    priority: str               # "high" | "medium" | "low"
