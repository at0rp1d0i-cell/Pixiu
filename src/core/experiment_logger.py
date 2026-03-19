"""
ExperimentLogger — 每轮实验快照写入器。

写到 data/experiment_runs/{run_id}/round_{n:03d}.json。
透明度层：写入失败只 log warning，不抛出异常，不影响主链路。
"""
import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.schemas.state import AgentState

logger = logging.getLogger(__name__)

# 实验数据根目录
_DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "experiment_runs"


class ExperimentLogger:
    """每轮实验快照写入器。写到 data/experiment_runs/{run_id}/round_{n:03d}.json"""

    def __init__(self, run_id: str, runs_dir: Optional[Path] = None) -> None:
        self.run_id = run_id
        self._base_dir: Path = (runs_dir or _DEFAULT_RUNS_DIR) / run_id
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(
                "[ExperimentLogger] 无法创建目录 %s: %s", self._base_dir, e
            )

    def snapshot(self, round_n: int, state: "AgentState", scheduler=None) -> None:
        """在 loop_control_node 清除 state 之前调用，保存当轮完整数据。

        写入失败只 log warning，不向上抛出异常。
        """
        try:
            self._write_snapshot(round_n, state, scheduler)
        except Exception as e:
            logger.warning(
                "[ExperimentLogger] Round %d 快照写入失败: %s", round_n, e
            )

    def _write_snapshot(
        self, round_n: int, state: "AgentState", scheduler=None
    ) -> None:
        verdicts_passed = sum(
            1 for v in state.critic_verdicts if v.overall_passed
        )

        # 提取 verdicts 摘要（含 factor_id + overall_passed + decision）
        verdicts_summary = [
            {
                "factor_id": v.factor_id,
                "overall_passed": v.overall_passed,
                "decision": v.decision,
                "score": v.score,
            }
            for v in state.critic_verdicts
        ]

        # 提取 Sharpe 值（通过的 backtest）
        sharpe_values = [
            r.metrics.sharpe
            for r in state.backtest_reports
            if r.passed
        ]

        # 获取 scheduler 权重
        scheduler_weights: dict = {}
        if scheduler is not None:
            try:
                # SubspaceScheduler 有 COLD_START_WEIGHTS 属性
                raw_weights = getattr(scheduler, "weights", None)
                if raw_weights is None:
                    raw_weights = getattr(scheduler, "COLD_START_WEIGHTS", {})
                # 将枚举 key 转为字符串
                scheduler_weights = {
                    (k.value if hasattr(k, "value") else str(k)): v
                    for k, v in raw_weights.items()
                }
            except Exception:
                scheduler_weights = {}

        # 从 factor pool 获取当前已通过因子数
        factor_pool_size = 0
        try:
            from src.factor_pool.pool import get_factor_pool
            pool = get_factor_pool()
            passed_factors = pool.get_passed_factors(limit=9999)
            factor_pool_size = len(passed_factors)
        except Exception as e:
            logger.warning(
                "[ExperimentLogger] 获取 factor_pool_size 失败: %s", e
            )

        errors: list[str] = []
        if state.last_error is not None:
            errors.append(state.last_error)

        prefilter_diag = getattr(state, "prefilter_diagnostics", {}) or {}
        prefilter_summary = {
            "input_count": prefilter_diag.get("input_count", len(state.research_notes)),
            "approved_count": prefilter_diag.get("approved_count", len(state.approved_notes)),
            "rejection_counts_by_filter": dict(prefilter_diag.get("rejection_counts_by_filter", {})),
            "sample_rejections": list(prefilter_diag.get("sample_rejections", [])),
        }

        execution_error_count = sum(
            1 for report in state.backtest_reports
            if report.error_message or report.status != "success"
        )
        execution_summary = {
            "backtest_reports_count": len(state.backtest_reports),
            "execution_error_count": execution_error_count,
            "executed_factor_ids_sample": [
                report.factor_id for report in state.backtest_reports[:5]
            ],
        }

        verdict_counts_by_decision = Counter(
            verdict.decision or "unknown" for verdict in state.critic_verdicts
        )
        failure_mode_counts = Counter(
            (verdict.failure_mode.value if verdict.failure_mode else "unknown")
            for verdict in state.critic_verdicts
            if not verdict.overall_passed
        )
        failed_check_counts = Counter(
            failed_check
            for verdict in state.critic_verdicts
            if not (
                verdict.failure_mode is not None
                and verdict.failure_mode.value == "execution_error"
            )
            for failed_check in verdict.failed_checks
        )
        sample_failures = [
            {
                "factor_id": verdict.factor_id,
                "note_id": verdict.note_id,
                "decision": verdict.decision,
                "failure_mode": verdict.failure_mode.value if verdict.failure_mode else None,
                "failed_checks": list(verdict.failed_checks),
                "failure_explanation": verdict.failure_explanation,
                "suggested_fix": verdict.suggested_fix,
                "score": verdict.score,
            }
            for verdict in state.critic_verdicts
            if not verdict.overall_passed
        ][:5]
        judgment_summary = {
            "verdict_counts_by_decision": dict(verdict_counts_by_decision),
            "failure_mode_counts": dict(failure_mode_counts),
            "failed_check_counts": dict(failed_check_counts),
            "sample_failures": sample_failures,
        }

        payload = {
            "round": round_n,
            "timestamp": datetime.now().isoformat(),
            "subspace_generated": dict(state.subspace_generated) if state.subspace_generated else {},
            "hypotheses_count": len(state.hypotheses),
            "notes_count": len(state.research_notes),
            "approved_notes_count": len(state.approved_notes),
            "prefilter_passed_count": prefilter_summary["approved_count"],
            "filtered_count": state.filtered_count,
            "prefilter": prefilter_summary,
            "verdicts": verdicts_summary,
            "verdicts_passed": verdicts_passed,
            "verdicts_total": len(state.critic_verdicts),
            "execution": execution_summary,
            "judgment": judgment_summary,
            "sharpe_values": sharpe_values,
            "factor_pool_size": factor_pool_size,
            "scheduler_weights": scheduler_weights,
            "scheduler_state": state.scheduler_state or {},
            "errors": errors,
        }

        out_path = self._base_dir / f"round_{round_n:03d}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "[ExperimentLogger] Round %d 快照已写入: %s", round_n, out_path
        )


# ─────────────────────────────────────────────────────────
# 模块级单例（类似 get_factor_pool() 模式）
# ─────────────────────────────────────────────────────────
_logger_instance: Optional[ExperimentLogger] = None


def get_experiment_logger() -> ExperimentLogger:
    """获取 ExperimentLogger 单例。run_id 从环境变量 PIXIU_RUN_ID 读取，
    默认为当前时间戳。"""
    global _logger_instance
    if _logger_instance is None:
        run_id = os.environ.get(
            "PIXIU_RUN_ID",
            datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        _logger_instance = ExperimentLogger(run_id=run_id)
    return _logger_instance
