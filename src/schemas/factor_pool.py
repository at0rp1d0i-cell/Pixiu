from typing import List, Optional

from src.schemas import PixiuBase


class FactorPoolRecord(PixiuBase):
    factor_id: str
    note_id: str
    formula: str
    hypothesis: str
    economic_rationale: str
    backtest_report_id: str
    verdict_id: str
    decision: str
    score: float
    sharpe: Optional[float] = None
    ic_mean: Optional[float] = None
    icir: Optional[float] = None
    turnover: Optional[float] = None
    max_drawdown: Optional[float] = None
    coverage: Optional[float] = None
    tags: List[str] = []
