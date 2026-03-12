from datetime import date, datetime
from typing import Literal, Optional
from src.schemas import PixiuBase


class ExecutionMeta(PixiuBase):
    engine: Literal["qlib"] = "qlib"
    engine_version: str = "unknown"
    template_version: str = "qlib_backtest.py.tpl"
    universe: str
    benchmark: str
    freq: str = "day"
    start_date: date
    end_date: date
    runtime_seconds: float
    timestamp_utc: datetime


class FactorSpecSnapshot(PixiuBase):
    formula: str
    hypothesis: str
    economic_rationale: str


class ArtifactRefs(PixiuBase):
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    script_path: Optional[str] = None
    raw_result_path: Optional[str] = None
    equity_curve_path: Optional[str] = None


class BacktestMetrics(PixiuBase):
    sharpe: float
    annualized_return: float
    annual_return: Optional[float] = None
    max_drawdown: float
    ic_mean: float
    ic_std: float
    icir: float                 # IC / IC_std
    turnover_rate: float        # 日均换手率
    turnover: Optional[float] = None
    coverage: Optional[float] = None
    win_rate: Optional[float] = None
    long_short_spread: Optional[float] = None

class BacktestReport(PixiuBase):
    # 标识
    report_id: str             # UUID
    run_id: Optional[str] = None
    note_id: str               # 对应的 FactorResearchNote
    factor_id: str             # 格式：{island}_{date}_{seq}（进入 FactorPool 的 key）
    island: str
    island_id: Optional[str] = None
    formula: str               # 实际回测的 Qlib 公式

    # 结果
    metrics: BacktestMetrics
    passed: bool               # 是否通过 Critic 阈值
    status: Literal["success", "failed", "partial"] = "success"
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None

    # 执行元数据
    execution_time_seconds: float
    qlib_output_raw: str       # 原始 stdout（调试用）
    error_message: Optional[str] = None
    execution_meta: Optional[ExecutionMeta] = None
    factor_spec: Optional[FactorSpecSnapshot] = None
    artifacts: Optional[ArtifactRefs] = None
