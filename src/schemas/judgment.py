from typing import List, Optional
from src.schemas import PixiuBase

class ThresholdCheck(PixiuBase):
    metric: str
    value: float
    threshold: float
    passed: bool

class CriticVerdict(PixiuBase):
    report_id: str
    factor_id: str
    overall_passed: bool

    # 逐项检查
    checks: List[ThresholdCheck] = []

    # 失败归因（overall_passed=False 时必填）
    failure_mode: Optional[str] = None
    failure_explanation: Optional[str] = None
    suggested_fix: Optional[str] = None

    # FactorPool 写入决策
    register_to_pool: bool
    pool_tags: List[str] = []

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
