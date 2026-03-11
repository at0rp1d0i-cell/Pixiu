from typing import Optional, List
from datetime import datetime
from src.schemas import PixiuBase

class FactorPoolRecord(PixiuBase):
    """FactorPool 写回的最小结构"""
    factor_id: str
    note_id: str
    formula: str
    hypothesis: str
    economic_rationale: str

    backtest_report_id: str
    verdict_id: str
    decision: str  # "promote" | "archive" | "reject" | "retry"
    score: float

    # 核心指标
    sharpe: Optional[float] = None
    ic_mean: Optional[float] = None
    icir: Optional[float] = None
    turnover: Optional[float] = None
    max_drawdown: Optional[float] = None
    coverage: Optional[float] = None

    created_at: datetime
    tags: List[str] = []
