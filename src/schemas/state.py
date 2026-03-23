from typing import List, Optional, Dict, Any
from pydantic import Field
from src.schemas import PixiuBase
from src.schemas.market_context import MarketContextMemo
from src.schemas.research_note import FactorResearchNote, SynthesisInsight
from src.schemas.hypothesis import Hypothesis, StrategySpec
from src.schemas.exploration import ExplorationResult
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport, PortfolioAllocation, CIOReport

class AgentState(PixiuBase):
    """LangGraph 全局状态，在节点间传递"""

    # 当前上下文
    current_round: int = 0
    current_island: str = "momentum"
    iteration: int = 0

    # SubspaceScheduler 持久化状态（跨轮次）
    scheduler_state: Optional[Dict[str, Any]] = None

    # Stage 1 输出
    market_context: Optional[MarketContextMemo] = None
    stage1_reliability: Dict[str, Any] = Field(default_factory=dict)
    stage_timings: Dict[str, float] = Field(default_factory=dict)
    stage_step_timings: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    # Stage 2 输出
    research_notes: List[FactorResearchNote] = Field(default_factory=list)
    synthesis_insights: List[SynthesisInsight] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    strategy_specs: List[StrategySpec] = Field(default_factory=list)
    # researcher 写入：每个子空间本轮原始生成数量 {subspace.value: count}
    subspace_generated: Dict[str, int] = Field(default_factory=dict)

    # Stage 3 输出（过滤后）
    approved_notes: List[FactorResearchNote] = Field(default_factory=list)
    filtered_count: int = 0  # 被过滤掉的数量
    prefilter_diagnostics: Dict[str, Any] = Field(default_factory=dict)

    # Stage 4 输出
    exploration_results: List[ExplorationResult] = Field(default_factory=list)
    backtest_reports: List[BacktestReport] = Field(default_factory=list)

    # Stage 5 输出
    critic_verdicts: List[CriticVerdict] = Field(default_factory=list)
    risk_audit_reports: List[RiskAuditReport] = Field(default_factory=list)
    portfolio_allocation: Optional[PortfolioAllocation] = None
    cio_report: Optional[CIOReport] = None

    # 人机交互
    awaiting_human_approval: bool = False
    human_decision: Optional[str] = None  # "approve" | "redirect:xxx" | "stop"

    # 错误处理
    last_error: Optional[str] = None
    error_stage: Optional[str] = None
