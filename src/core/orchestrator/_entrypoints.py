"""
Entry-point async functions: run_evolve and run_single.
"""
import logging
from datetime import UTC, datetime

from src.schemas.state import AgentState
from . import config as _config
from . import control_plane as _control_plane
from . import runtime as _runtime

logger = logging.getLogger(__name__)


async def run_evolve(rounds: int = 20, islands: list[str] | None = None):
    """进化模式：多 Island 轮换，持续运行 rounds 轮。"""
    _config.MAX_ROUNDS = rounds
    if islands:
        _config.ACTIVE_ISLANDS = islands

    _runtime.reset_current_run_id()
    graph = _runtime.get_graph()
    if graph is None:
        from .graph import get_graph as _get_graph

        graph = _get_graph()
    thread_id = f"pixiu_evolve_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _runtime.set_graph_config({"configurable": {"thread_id": thread_id}})
    run_id = _control_plane._ensure_run_record(mode="evolve")
    _runtime.set_current_run_id(run_id)

    logger.info("\n%s", "=" * 60)
    logger.info("Pixiu v2 启动（进化模式，最大 %d 轮）", rounds)
    logger.info("   Active Islands: %s", ", ".join(_config.ACTIVE_ISLANDS))
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0)
    _control_plane._update_run_record("market_context", status="running", current_round=0)
    try:
        result = await graph.ainvoke(initial_state.model_dump(), config=_runtime.get_graph_config())
    except Exception as exc:
        _control_plane._update_run_record(
            "market_context",
            status="failed",
            current_round=0,
            finished_at=datetime.now(UTC),
            last_error=str(exc),
        )
        raise
    status = "stopped" if result.get("human_decision") == "stop" else "completed"
    _control_plane._update_run_record(
        result.get("error_stage") or "loop_control",
        status="failed" if result.get("last_error") else status,
        current_round=result.get("current_round", 0),
        finished_at=datetime.now(UTC),
        last_error=result.get("last_error"),
    )


async def run_single(island: str):
    """单次模式：指定 Island，单轮调试。"""
    _config.MAX_ROUNDS = 1
    _runtime.reset_current_run_id()
    graph = _runtime.get_graph()
    if graph is None:
        from .graph import get_graph as _get_graph

        graph = _get_graph()
    thread_id = f"pixiu_single_{island}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _runtime.set_graph_config({"configurable": {"thread_id": thread_id}})
    run_id = _control_plane._ensure_run_record(mode="single")
    _runtime.set_current_run_id(run_id)

    logger.info("\n%s", "=" * 60)
    logger.info("Pixiu v2 启动（单次模式，Island=%s）", island)
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0, current_island=island)
    _control_plane._update_run_record("market_context", status="running", current_round=0)
    try:
        result = await graph.ainvoke(initial_state.model_dump(), config=_runtime.get_graph_config())
    except Exception as exc:
        _control_plane._update_run_record(
            "market_context",
            status="failed",
            current_round=0,
            finished_at=datetime.now(UTC),
            last_error=str(exc),
        )
        raise
    status = "stopped" if result.get("human_decision") == "stop" else "completed"
    _control_plane._update_run_record(
        result.get("error_stage") or "loop_control",
        status="failed" if result.get("last_error") else status,
        current_round=result.get("current_round", 0),
        finished_at=datetime.now(UTC),
        last_error=result.get("last_error"),
    )
