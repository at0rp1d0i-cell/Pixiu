from typing import List, Optional, Literal
from src.schemas import PixiuBase

class CriticVerdict(PixiuBase):
    """Stage 5 确定性判定结果"""
    verdict_id: str
    report_id: str
    note_id: str

    # 决策（确定性状态机）
    decision: Literal["promote", "archive", "reject", "retry"]
    score: float
    passed_checks: List[str]
    failed_checks: List[str]

    # 摘要和原因码
    summary: str
    reason_codes: List[str]  # "LOW_SHARPE" | "LOW_IC" | "LOW_ICIR" | "HIGH_TURNOVER" | etc.

class CorrelationFlag(PixiuBase):
    existing_factor_id: str
    correlation: float
    flag_reason: str  # "too_similar" | "opposite" | "complement"

class RiskAuditReport(PixiuBase):
    factor_id: str
    overfitting_score: float
    overfitting_flag: bool
    correlation_flags: List[CorrelationFlag] = []
    recommendation: str
    audit_notes: str

class FactorWeight(PixiuBase):
    factor_id: str
    island: str
    weight: float
    rationale: str

class PortfolioAllocation(PixiuBase):
    allocation_id: str
    timestamp: str
    factor_weights: List[FactorWeight] = []
    expected_portfolio_sharpe: float
    expected_portfolio_ic: float
    diversification_score: float
    total_factors: int
    notes: str

class CIOReport(PixiuBase):
    """触发 interrupt()，等待人类 CIO 审批"""
    report_id: str
    period: str

    # 本轮摘要
    total_factors_tested: int
    new_factors_approved: int
    best_new_factor: Optional[str] = None
    best_new_sharpe: Optional[float] = None

    # 组合状态
    current_portfolio: PortfolioAllocation
    portfolio_change_summary: str

    # 值得关注的发现
    highlights: List[str] = []
    risks: List[str] = []

    # 全文报告
    full_report_markdown: str

    # 等待 CIO 操作
    suggested_actions: List[str] = []
    requires_human_decision: bool = True
