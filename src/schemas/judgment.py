import uuid
from typing import List, Literal, Optional
from pydantic import Field, field_validator
from src.schemas import PixiuBase
from src.schemas.failure_constraint import FailureMode


class ThresholdCheck(PixiuBase):
    metric: str
    value: float
    threshold: float
    passed: bool


# 向后兼容：旧字符串 → FailureMode enum
_LEGACY_FAILURE_MODE_MAP: dict[str, FailureMode] = {
    "execution_error": FailureMode.EXECUTION_ERROR,
    "low_sharpe": FailureMode.LOW_SHARPE,
    "low_ic": FailureMode.NO_IC,
    "negative_ic": FailureMode.NEGATIVE_IC,
    "low_icir": FailureMode.NO_IC,
    "high_turnover": FailureMode.HIGH_TURNOVER,
    "high_drawdown": FailureMode.HIGH_DRAWDOWN,
    "low_coverage": FailureMode.LOW_COVERAGE,
    "overfitting": FailureMode.OVERFITTING,
    "threshold_failure": FailureMode.LOW_SHARPE,
}


class CriticVerdict(PixiuBase):
    verdict_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    report_id: str
    factor_id: str
    note_id: Optional[str] = None
    overall_passed: bool
    decision: Optional[Literal["promote", "archive", "reject", "retry"]] = None
    score: float = 0.0

    # 逐项检查
    checks: List[ThresholdCheck] = []
    passed_checks: List[str] = []
    failed_checks: List[str] = []

    # 失败归因（overall_passed=False 时必填）
    failure_mode: Optional[FailureMode] = None
    failure_explanation: Optional[str] = None
    suggested_fix: Optional[str] = None
    summary: str = ""
    reason_codes: List[str] = []

    # 判断时的市场 regime
    regime_at_judgment: Optional[str] = None

    # FactorPool 写入决策
    register_to_pool: bool
    pool_tags: List[str] = []

    @field_validator("failure_mode", mode="before")
    @classmethod
    def coerce_failure_mode(cls, v):
        """向后兼容：接受旧字符串形式的 failure_mode。未知字符串返回 None，
        由消费方（ConstraintExtractor）通过 checks 做 fallback。"""
        if v is None or isinstance(v, FailureMode):
            return v
        if isinstance(v, str):
            # 先尝试直接用 enum value 匹配
            try:
                return FailureMode(v)
            except ValueError:
                pass
            # 再查旧字符串映射表；不在表中的未知字符串返回 None
            return _LEGACY_FAILURE_MODE_MAP.get(v, None)
        return v

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
