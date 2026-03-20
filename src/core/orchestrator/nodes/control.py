"""Control nodes: human gate and loop control."""
import logging
import os
import time

from src.schemas.state import AgentState
from src.schemas.stage_io import HumanGateOutput, LoopControlOutput
from src.core.experiment_logger import get_experiment_logger
from src.core.orchestrator.timing import merge_stage_timing

logger = logging.getLogger(__name__)


def human_gate_node(state: AgentState) -> HumanGateOutput:
    """Human Gate: 通过 control plane 轮询人类决策，支持跨进程审批。"""
    from .. import control_plane as _control_plane
    started_at = time.perf_counter()

    if not state.awaiting_human_approval:
        logger.info("[Human Gate] 当前状态未等待审批，直接结束当前 run")
        return {
            "human_decision": "stop",
            "awaiting_human_approval": False,
            **merge_stage_timing(state, "human_gate", round((time.perf_counter() - started_at) * 1000.0, 2)),
        }

    run_id = _control_plane._ensure_run_record()
    if not run_id:
        logger.warning("[Human Gate] 缺少 run_id，默认批准继续")
        return {
            "human_decision": "approve",
            "awaiting_human_approval": False,
            **merge_stage_timing(state, "human_gate", round((time.perf_counter() - started_at) * 1000.0, 2)),
        }

    store = _control_plane.get_state_store()
    poll_interval = float(os.getenv("PIXIU_HUMAN_GATE_POLL_INTERVAL_SEC", "1.0"))
    timeout_sec = float(os.getenv("PIXIU_HUMAN_GATE_TIMEOUT_SEC", "0"))
    started_at = time.monotonic()

    logger.info("[Human Gate] 等待 run=%s 的人类决策...", run_id)
    while True:
        decision = store.pop_latest_human_decision(run_id)
        if decision is not None:
            logger.info("[Human Gate] 收到决策: %s", decision.action)
            next_state = state.model_copy(
                update={
                    "human_decision": decision.action,
                    "awaiting_human_approval": False,
                }
            )
            if decision.action == "stop":
                _control_plane._update_run_record(
                    "human_gate",
                    status="stopped",
                    current_round=state.current_round,
                )
            else:
                _control_plane._update_run_record(
                    "human_gate",
                    status="running",
                    current_round=state.current_round,
                )
            _control_plane._write_snapshot(
                next_state,
                "human_gate",
                awaiting_human_approval=False,
            )
            return {
                "human_decision": decision.action,
                "awaiting_human_approval": False,
                **merge_stage_timing(state, "human_gate", round((time.perf_counter() - started_at) * 1000.0, 2)),
            }

        if timeout_sec > 0 and (time.monotonic() - started_at) >= timeout_sec:
            logger.warning("[Human Gate] 等待超时，默认 stop")
            next_state = state.model_copy(
                update={"human_decision": "stop", "awaiting_human_approval": False}
            )
            _control_plane._update_run_record(
                "human_gate",
                status="stopped",
                current_round=state.current_round,
            )
            _control_plane._write_snapshot(
                next_state,
                "human_gate",
                awaiting_human_approval=False,
            )
            return {
                "human_decision": "stop",
                "awaiting_human_approval": False,
                **merge_stage_timing(state, "human_gate", round((time.perf_counter() - started_at) * 1000.0, 2)),
            }

        time.sleep(poll_interval)


def loop_control_node(state: AgentState) -> LoopControlOutput:
    """轮次控制：更新调度器，清空本轮状态，递增 current_round。"""
    from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
    from src.schemas.hypothesis import ExplorationSubspace
    from .. import control_plane as _control_plane
    from .. import runtime as _runtime
    started_at = time.perf_counter()

    scheduler = _runtime.get_scheduler()

    epoch_island = None
    for verdict in state.critic_verdicts:
        if verdict.overall_passed:
            matching = [r for r in state.backtest_reports if r.factor_id == verdict.factor_id]
            if matching:
                epoch_island = matching[0].island
                break

    island_for_epoch = epoch_island or (state.current_island or "unknown")
    scheduler.on_epoch_done(island_for_epoch, state.current_round)

    subspace_scheduler = SubspaceScheduler()

    raw_sched_state = state.scheduler_state
    if raw_sched_state:
        sched_state = SchedulerState(**raw_sched_state)
    else:
        sched_state = SchedulerState()

    note_subspace: dict[str, str | None] = {
        note.note_id: (note.exploration_subspace.value if note.exploration_subspace else None)
        for note in state.approved_notes
    }
    factor_to_note: dict[str, str] = {
        r.factor_id: r.note_id
        for r in state.backtest_reports
    }

    generated: dict[str, int] = dict(state.subspace_generated) if state.subspace_generated else {}

    passed: dict[str, int] = {}
    for verdict in state.critic_verdicts:
        if verdict.overall_passed:
            note_id = factor_to_note.get(verdict.factor_id)
            if note_id:
                subspace_val = note_subspace.get(note_id)
                if subspace_val:
                    passed[subspace_val] = passed.get(subspace_val, 0) + 1

    subspace_results: dict[ExplorationSubspace, tuple[int, int]] = {}
    for subspace in ExplorationSubspace:
        g = generated.get(subspace.value, 0)
        p = passed.get(subspace.value, 0)
        subspace_results[subspace] = (g, p)

    updated_sched_state = subspace_scheduler.update_state(sched_state, subspace_results)

    for warning in subspace_scheduler.get_warnings(updated_sched_state):
        logger.warning("[Loop Control] SubspaceScheduler: %s", warning)

    next_round = state.current_round + 1
    logger.info(
        "[Loop Control] Round %d 完成: subspace_generated=%s, filtered=%d, "
        "approved=%d, verdicts_passed=%d",
        state.current_round,
        dict(state.subspace_generated) if state.subspace_generated else {},
        state.filtered_count,
        len(state.approved_notes),
        sum(1 for v in state.critic_verdicts if v.overall_passed),
    )
    logger.info(
        "[Loop Control] 进入第 %d 轮 (scheduler warm_start=%s, total_passed=%s)",
        next_round,
        updated_sched_state.warm_start,
        sum(updated_sched_state.total_passed.values()),
    )

    final_timing_update = merge_stage_timing(
        state,
        "loop_control",
        round((time.perf_counter() - started_at) * 1000.0, 2),
    )

    # 透明度层：在清除 state 之前写入本轮快照，失败不影响主链路
    try:
        get_experiment_logger().snapshot(
            round_n=state.current_round,
            state=state.model_copy(update=final_timing_update),
            scheduler=subspace_scheduler,
            scheduler_state_snapshot=updated_sched_state.model_dump(),
        )
    except Exception as _snap_exc:
        logger.warning("[Loop Control] 快照写入异常: %s", _snap_exc)

    _control_plane._update_run_record(
        "loop_control",
        status="running",
        current_round=next_round,
    )

    return {
        "current_round": next_round,
        "scheduler_state": updated_sched_state.model_dump(),
        "research_notes": [],
        "approved_notes": [],
        "subspace_generated": {},
        "filtered_count": 0,
        "prefilter_diagnostics": {},
        "exploration_results": [],
        "backtest_reports": [],
        "critic_verdicts": [],
        "risk_audit_reports": [],
        "awaiting_human_approval": False,
        "human_decision": None,
        "last_error": None,
        "error_stage": None,
        "stage_timings": {},
        "stage_step_timings": {},
    }
