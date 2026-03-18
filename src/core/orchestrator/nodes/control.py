"""Control nodes: human gate and loop control."""
import logging

from src.schemas.state import AgentState
from src.schemas.stage_io import HumanGateOutput, LoopControlOutput

logger = logging.getLogger(__name__)


def human_gate_node(state: AgentState) -> HumanGateOutput:
    """Human Gate: 此节点本身不执行任何逻辑。

    LangGraph 在 interrupt_before=[NODE_HUMAN_GATE] 配置下，
    会在进入此节点前暂停，等待外部 .update_state() 注入 human_decision。

    外部（CLI）调用方式：
        graph.update_state(
            config,
            {"human_decision": "approve", "awaiting_human_approval": False},
            as_node=NODE_HUMAN_GATE
        )
    """
    return {}  # pass-through，路由在 route_after_human 中处理


def loop_control_node(state: AgentState) -> LoopControlOutput:
    """轮次控制：更新调度器，清空本轮状态，递增 current_round。"""
    from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
    from src.schemas.hypothesis import ExplorationSubspace
    import src.core.orchestrator as _orch
    get_scheduler = _orch.get_scheduler

    scheduler = get_scheduler()

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
        "[Loop Control] 进入第 %d 轮 (scheduler warm_start=%s, total_passed=%s)",
        next_round,
        updated_sched_state.warm_start,
        sum(updated_sched_state.total_passed.values()),
    )

    return {
        "current_round": next_round,
        "scheduler_state": updated_sched_state.model_dump(),
        "research_notes": [],
        "approved_notes": [],
        "subspace_generated": {},
        "filtered_count": 0,
        "exploration_results": [],
        "backtest_reports": [],
        "critic_verdicts": [],
        "risk_audit_reports": [],
        "awaiting_human_approval": False,
        "human_decision": None,
        "last_error": None,
        "error_stage": None,
    }
