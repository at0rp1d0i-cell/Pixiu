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


class ValidationWindow(PixiuBase):
    start_date: date
    end_date: date
    coverage: Optional[float] = None
    notes: Optional[str] = None


class BacktestMetrics(PixiuBase):
    sharpe: float
    annualized_return: float
    max_drawdown: float
    ic_mean: float
    ic_std: float
    icir: float                 # IC / IC_std
    turnover_rate: float        # 日均换手率
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
    metrics_scope: Literal["full", "discovery"] = "full"
    oos_metrics: Optional[BacktestMetrics] = None
    oos_degradation: Optional[float] = None
    passed: bool               # 质量阈值是否通过（兼容旧调用点；执行是否成功见 execution_succeeded）
    execution_succeeded: Optional[bool] = None  # 这次回测/解析是否真的成功
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

    discovery_window: Optional[ValidationWindow] = None
    oos_window: Optional[ValidationWindow] = None
    discovery_passed: Optional[bool] = None
    oos_passed: Optional[bool] = None
