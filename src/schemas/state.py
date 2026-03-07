from typing import List, Optional
from pydantic import Field
from src.schemas import EvoQuantBase
from src.schemas.market_context import MarketContextMemo
from src.schemas.research_note import FactorResearchNote, SynthesisInsight
from src.schemas.exploration import ExplorationResult
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport, PortfolioAllocation, CIOReport

class AgentState(EvoQuantBase):
    """LangGraph 全局状态，在节点间传递"""

    # 当前上下文
    current_round: int = 0
    current_island: str = "momentum"
    iteration: int = 0

    # Stage 1 输出
    market_context: Optional[MarketContextMemo] = None

    # Stage 2 输出
    research_notes: List[FactorResearchNote] = Field(default_factory=list)
    synthesis_insights: List[SynthesisInsight] = Field(default_factory=list)

    # Stage 3 输出（过滤后）
    approved_notes: List[FactorResearchNote] = Field(default_factory=list)
    filtered_count: int = 0  # 被过滤掉的数量

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
