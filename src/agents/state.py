"""
Pixiu: LangGraph State Definition
"""
from typing import TypedDict, Annotated, Sequence, Optional
from langchain_core.messages import BaseMessage
import operator

from .schemas import FactorHypothesis, BacktestMetrics


class AgentState(TypedDict):
    # LangChain 消息历史
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # ── 结构化核心字段（新增）──────────────────────────────────
    factor_hypothesis: Optional[FactorHypothesis]  # Researcher 的结构化输出
    backtest_metrics: Optional[BacktestMetrics]    # Critic 解析的结构化指标

    # ── 兼容旧字段（保留，不删除）──────────────────────────────
    # Coder 仍然从 factor_proposal（str）生成代码，保持 Coder 不变
    factor_proposal: str       # 由 researcher_node 从 factor_hypothesis 自动生成
    code_snippet: str
    backtest_result: str       # Coder 的原始日志输出，Critic 从此解析

    # ── 状态追踪 ───────────────────────────────────────────────
    current_iteration: int
    max_iterations: int
    error_message: str
    island_name: str   # ← 新增：当前激活的 Island 名称
