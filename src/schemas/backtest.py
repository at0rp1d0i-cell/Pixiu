from typing import Optional, Literal
from datetime import datetime, date
from src.schemas import PixiuBase

class ExecutionMeta(PixiuBase):
    """执行上下文元数据，确保指标可比较"""
    engine: Literal["qlib"] = "qlib"
    engine_version: str = "0.9.0"
    template_version: str = "v2.0"
    universe: str
    benchmark: str = "csi300"
    freq: str = "day"
    start_date: date
    end_date: date
    runtime_seconds: float
    timestamp_utc: datetime

class FactorSpecSnapshot(PixiuBase):
    """因子规格快照，保留语义锚点"""
    formula: str
    hypothesis: str
    economic_rationale: str

class BacktestMetrics(PixiuBase):
    """回测指标 - 最小充分集"""
    sharpe: Optional[float] = None
    annual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    ic_mean: Optional[float] = None
    ic_std: Optional[float] = None
    icir: Optional[float] = None
    turnover: Optional[float] = None
    coverage: Optional[float] = None

class ArtifactRefs(PixiuBase):
    """产物引用，用于排障和审计"""
    stdout_path: str
    stderr_path: str
    script_path: str
    raw_result_path: Optional[str] = None
    equity_curve_path: Optional[str] = None

class BacktestReport(PixiuBase):
    """Stage 4 的唯一标准输出"""
    # 标识
    report_id: str
    run_id: str
    note_id: str
    island_id: str

    # 状态
    status: Literal["success", "failed", "partial"]
    failure_stage: Optional[str] = None  # "compile" | "run" | "parse" | "judge"
    failure_reason: Optional[str] = None

    # 核心内容
    execution_meta: ExecutionMeta
    factor_spec: FactorSpecSnapshot
    metrics: BacktestMetrics
    artifacts: ArtifactRefs
