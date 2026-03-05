"""
EvoQuant: 结构化数据模型
统一定义 Agent 间传递的数据结构，消除自由文本接缝。
"""
from typing import Literal
from pydantic import BaseModel, Field


class FactorHypothesis(BaseModel):
    """Researcher 输出的结构化因子假设。"""

    name: str = Field(
        description="因子英文名（snake_case），如 northbound_momentum_5d"
    )
    formula: str = Field(
        description="标准 Qlib 表达式，如 Mean($volume, 5) / Ref(Mean($volume, 5), 5)"
    )
    hypothesis: str = Field(
        description="因子的中文假设描述（1-3句话）"
    )
    market_observation: str = Field(
        default="",
        description="Researcher 调用 MCP 工具后观察到的关键市场数据（可为空）"
    )
    expected_direction: Literal["positive", "negative", "unknown"] = Field(
        default="unknown",
        description="预期因子方向：positive=因子越大收益越高，negative=反之"
    )
    rationale: str = Field(
        description="为什么这个因子在 A 股应该有 Alpha（1-3句话）"
    )


class BacktestMetrics(BaseModel):
    """Coder 回测完成后的结构化指标结果。"""

    sharpe: float = Field(default=0.0, description="年化夏普比率")
    annualized_return: float = Field(default=0.0, description="年化收益率（%）")
    max_drawdown: float = Field(default=0.0, description="最大回撤（%，负数）")
    ic: float = Field(default=0.0, description="因子 IC 均值")
    icir: float = Field(default=0.0, description="IC 信息比率（IC均值/IC标准差）")
    turnover: float = Field(default=0.0, description="日均换手率（%）")
    win_rate: float = Field(default=0.0, description="胜率（%）")
    parse_success: bool = Field(
        default=False,
        description="是否成功从回测日志解析到有效指标"
    )
    raw_log_tail: str = Field(
        default="",
        description="回测日志最后 500 字符（用于调试）"
    )
