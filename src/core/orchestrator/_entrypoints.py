"""
Entry-point async functions: run_evolve and run_single.
"""
import logging
from datetime import UTC, datetime

from src.schemas.state import AgentState

logger = logging.getLogger(__name__)


async def run_evolve(rounds: int = 20, islands: list[str] | None = None):
    """进化模式：多 Island 轮换，持续运行 rounds 轮。"""
    import src.core.orchestrator as _orch
    import src.core.orchestrator.graph as _graph_mod

    _orch.MAX_ROUNDS = rounds
    if islands:
        _orch.ACTIVE_ISLANDS = islands

    _orch._current_run_id = None
    graph = _orch.get_graph()
    thread_id = f"pixiu_evolve_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _graph_mod._graph_config = {"configurable": {"thread_id": thread_id}}
    run_id = _orch._ensure_run_record(mode="evolve")
    _orch._current_run_id = run_id

    logger.info("\n%s", "=" * 60)
    logger.info("Pixiu v2 启动（进化模式，最大 %d 轮）", rounds)
    logger.info("   Active Islands: %s", ", ".join(_orch.ACTIVE_ISLANDS))
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0)
    _orch._update_run_record(_orch.NODE_MARKET_CONTEXT, status="running", current_round=0)
    result = await graph.ainvoke(initial_state.model_dump(), config=_graph_mod._graph_config)
    status = "stopped" if result.get("human_decision") == "stop" else "completed"
    _orch._update_run_record(
        result.get("error_stage") or _orch.NODE_LOOP_CONTROL,
        status="failed" if result.get("last_error") else status,
        current_round=result.get("current_round", 0),
        finished_at=datetime.now(UTC),
        last_error=result.get("last_error"),
    )


async def run_single(island: str):
    """单次模式：指定 Island，单轮调试。"""
    import src.core.orchestrator as _orch
    import src.core.orchestrator.graph as _graph_mod

    _orch.MAX_ROUNDS = 1
    _orch._current_run_id = None
    graph = _orch.get_graph()
    thread_id = f"pixiu_single_{island}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _graph_mod._graph_config = {"configurable": {"thread_id": thread_id}}
    run_id = _orch._ensure_run_record(mode="single")
    _orch._current_run_id = run_id

    logger.info("\n%s", "=" * 60)
    logger.info("Pixiu v2 启动（单次模式，Island=%s）", island)
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0, current_island=island)
    _orch._update_run_record(_orch.NODE_MARKET_CONTEXT, status="running", current_round=0)
    result = await graph.ainvoke(initial_state.model_dump(), config=_graph_mod._graph_config)
    status = "stopped" if result.get("human_decision") == "stop" else "completed"
    _orch._update_run_record(
        result.get("error_stage") or _orch.NODE_LOOP_CONTROL,
        status="failed" if result.get("last_error") else status,
        current_round=result.get("current_round", 0),
        finished_at=datetime.now(UTC),
        last_error=result.get("last_error"),
    )
