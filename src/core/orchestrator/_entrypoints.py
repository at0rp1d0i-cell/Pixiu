"""
Entry-point async functions: run_evolve and run_single.
"""
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, MutableMapping

from src.core.env import ResolvedEnv, resolve_and_apply_layered_env
from src.schemas.state import AgentState
from . import config as _config
from . import control_plane as _control_plane
from . import runtime as _runtime

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
_RUN_ENV_KEYS = ("TUSHARE_TOKEN", "QLIB_DATA_DIR")
_DEFAULT_QLIB_DATA_DIR = PROJECT_ROOT / "data" / "qlib_bin"


def _resolve_run_env_truth(
    *,
    process_env: Mapping[str, str] | None = None,
    target_env: MutableMapping[str, str] | None = None,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
) -> ResolvedEnv:
    resolved = resolve_and_apply_layered_env(
        keys=_RUN_ENV_KEYS,
        process_env=process_env,
        target_env=target_env,
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path if repo_env_path is not None else PROJECT_ROOT / ".env",
        defaults={"QLIB_DATA_DIR": str(_DEFAULT_QLIB_DATA_DIR)},
    )
    logger.info(
        "[pixiu run] env truth: TUSHARE_TOKEN=%s (%s) | QLIB_DATA_DIR=%s (%s)",
        "set" if resolved.values.get("TUSHARE_TOKEN") else "missing",
        resolved.sources.get("TUSHARE_TOKEN", "unset"),
        resolved.values.get("QLIB_DATA_DIR", ""),
        resolved.sources.get("QLIB_DATA_DIR", "unset"),
    )
    return resolved


async def run_evolve(rounds: int = 20, islands: list[str] | None = None):
    """进化模式：多 Island 轮换，持续运行 rounds 轮。"""
    _resolve_run_env_truth()
    _config.MAX_ROUNDS = rounds
    if islands:
        _config.ACTIVE_ISLANDS = list(islands)

    _runtime.reset_scheduler()
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
    _resolve_run_env_truth()
    _config.MAX_ROUNDS = 1
    _config.ACTIVE_ISLANDS = [island]
    _runtime.reset_scheduler()
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
    logger.info("   Active Islands: %s", ", ".join(_config.ACTIVE_ISLANDS))
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
