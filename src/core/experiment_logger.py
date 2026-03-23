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
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.schemas.state import AgentState

from src.llm.usage_ledger import get_run_usage_snapshot

logger = logging.getLogger(__name__)

# 实验数据根目录
_DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "experiment_runs"


class ExperimentLogger:
    """每轮实验快照写入器。写到 data/experiment_runs/{run_id}/round_{n:03d}.json"""

    def __init__(self, run_id: str, runs_dir: Optional[Path] = None) -> None:
        self.run_id = run_id
        self._base_dir: Path = (runs_dir or _DEFAULT_RUNS_DIR) / run_id
        self._last_llm_usage_run_id: str | None = None
        self._last_llm_usage_cumulative: dict[str, Any] | None = None
        self._last_llm_call_event_count: int = 0
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(
                "[ExperimentLogger] 无法创建目录 %s: %s", self._base_dir, e
            )

    def _build_llm_usage_payload(self) -> dict[str, Any]:
        cumulative = get_run_usage_snapshot()
        ledger_run_id = str(cumulative.get("run_id") or self.run_id)

        keys = (
            "calls",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "estimated_cost_usd",
        )

        previous = self._last_llm_usage_cumulative
        if self._last_llm_usage_run_id != ledger_run_id:
            previous = None
            self._last_llm_call_event_count = 0

        round_usage: dict[str, Any] = {}
        for key in keys:
            current_value = cumulative.get(key, 0)
            previous_value = previous.get(key, 0) if previous else 0
            if key == "estimated_cost_usd":
                round_usage[key] = round(
                    max(0.0, float(current_value) - float(previous_value)),
                    8,
                )
            else:
                round_usage[key] = max(0, int(current_value) - int(previous_value))

        self._last_llm_usage_run_id = ledger_run_id
        self._last_llm_usage_cumulative = {
            key: cumulative.get(key, 0) for key in keys
        }
        cumulative_call_events = list(cumulative.get("call_events", []))
        round_call_events = cumulative_call_events[self._last_llm_call_event_count :]
        self._last_llm_call_event_count = len(cumulative_call_events)

        return {
            "run_id": ledger_run_id,
            "round": round_usage,
            "cumulative": {
                key: cumulative.get(key, 0) for key in keys
            },
            "by_model_cumulative": cumulative.get("by_model", {}),
            "call_events_round": round_call_events,
            "call_events_cumulative_count": len(cumulative_call_events),
        }

    def snapshot(
        self,
        round_n: int,
        state: "AgentState",
        scheduler=None,
        scheduler_state_snapshot: Optional[dict] = None,
    ) -> None:
        """在 loop_control_node 清除 state 之前调用，保存当轮完整数据。

        写入失败只 log warning，不向上抛出异常。
        """
        try:
            self._write_snapshot(
                round_n,
                state,
                scheduler,
                scheduler_state_snapshot=scheduler_state_snapshot,
            )
        except Exception as e:
            logger.warning(
                "[ExperimentLogger] Round %d 快照写入失败: %s", round_n, e
            )

    def _write_snapshot(
        self,
        round_n: int,
        state: "AgentState",
        scheduler=None,
        scheduler_state_snapshot: Optional[dict] = None,
    ) -> None:
        verdicts_passed = sum(
            1 for v in state.critic_verdicts if v.overall_passed
        )
        verdicts_promoted = sum(
            1 for v in state.critic_verdicts if v.decision == "promote"
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
            if r.execution_succeeded
        ]

        # 获取 scheduler 权重：只记录可由持久化状态复原的真实分配权重
        scheduler_weights: dict = {}
        if scheduler is not None and scheduler_state_snapshot:
            try:
                from src.scheduling.subspace_scheduler import SchedulerState

                allocations = scheduler.allocate(
                    SchedulerState(**scheduler_state_snapshot)
                )
                scheduler_weights = {
                    allocation.subspace.value: allocation.weight
                    for allocation in allocations
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
        stage1_reliability = dict(getattr(state, "stage1_reliability", {}) or {})

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
            "sample_reports": [
                {
                    "factor_id": report.factor_id,
                    "status": report.status,
                    "execution_succeeded": report.execution_succeeded,
                    "sharpe": report.metrics.sharpe,
                    "ic_mean": report.metrics.ic_mean,
                    "icir": report.metrics.icir,
                    "turnover_rate": report.metrics.turnover_rate,
                    "coverage": report.metrics.coverage,
                }
                for report in state.backtest_reports[:5]
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
        llm_usage_payload = self._build_llm_usage_payload()

        payload = {
            "round": round_n,
            "timestamp": datetime.now().isoformat(),
            "subspace_generated": dict(state.subspace_generated) if state.subspace_generated else {},
            "hypotheses_count": len(state.hypotheses),
            "notes_count": len(state.research_notes),
            "approved_notes_count": len(state.approved_notes),
            "prefilter_passed_count": prefilter_summary["approved_count"],
            "filtered_count": state.filtered_count,
            "stage1_reliability": stage1_reliability,
            "prefilter": prefilter_summary,
            "verdicts": verdicts_summary,
            "verdicts_passed": verdicts_passed,
            "verdicts_promoted": verdicts_promoted,
            "verdicts_total": len(state.critic_verdicts),
            "execution": execution_summary,
            "judgment": judgment_summary,
            "sharpe_values": sharpe_values,
            "factor_pool_size": factor_pool_size,
            "scheduler_weights": scheduler_weights,
            "scheduler_state": state.scheduler_state or {},
            "llm_usage": llm_usage_payload,
            "timings": {
                "stages_ms": dict(state.stage_timings),
                "stage_steps_ms": {
                    stage: dict(step_timings)
                    for stage, step_timings in state.stage_step_timings.items()
                },
                "round_total_ms": round(sum(state.stage_timings.values()), 2),
            },
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
