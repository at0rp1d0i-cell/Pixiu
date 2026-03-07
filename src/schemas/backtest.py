from typing import Optional
from src.schemas import EvoQuantBase

class BacktestMetrics(EvoQuantBase):
    sharpe: float
    annualized_return: float
    max_drawdown: float
    ic_mean: float
    ic_std: float
    icir: float                 # IC / IC_std
    turnover_rate: float        # 日均换手率
    win_rate: Optional[float] = None
    long_short_spread: Optional[float] = None

class BacktestReport(EvoQuantBase):
    # 标识
    report_id: str             # UUID
    note_id: str               # 对应的 FactorResearchNote
    factor_id: str             # 格式：{island}_{date}_{seq}（进入 FactorPool 的 key）
    island: str
    formula: str               # 实际回测的 Qlib 公式

    # 结果
    metrics: BacktestMetrics
    passed: bool               # 是否通过 Critic 阈值

    # 执行元数据
    execution_time_seconds: float
    qlib_output_raw: str       # 原始 stdout（调试用）
    error_message: Optional[str] = None
