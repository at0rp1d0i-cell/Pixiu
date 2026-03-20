"""Pixiu v2 Orchestrator package compatibility facade."""
from __future__ import annotations

import logging

from src.core.orchestrator import config as _config
from src.core.orchestrator import control_plane as _control_plane
from src.core.orchestrator import runtime as _runtime
from src.core.orchestrator.graph import (
    build_graph,
    get_graph,
    get_latest_config,
    route_after_human,
    route_after_judgment,
    route_after_portfolio,
    route_after_prefilter,
    route_loop,
)
from src.core.orchestrator.nodes import (
    coder_node,
    exploration_node,
    human_gate_node,
    hypothesis_gen_node,
    judgment_node,
    loop_control_node,
    market_context_node,
    note_refinement_node,
    portfolio_node,
    prefilter_node,
    report_node,
    synthesis_node,
)
from src.core.orchestrator._entrypoints import run_evolve, run_single
from src.core.orchestrator._context import (
    NODE_CODER,
    NODE_EXPLORATION,
    NODE_HUMAN_GATE,
    NODE_HYPOTHESIS_GEN,
    NODE_JUDGMENT,
    NODE_LOOP_CONTROL,
    NODE_MARKET_CONTEXT,
    NODE_NOTE_REFINEMENT,
    NODE_PORTFOLIO,
    NODE_PREFILTER,
    NODE_REPORT,
    NODE_SYNTHESIS,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

get_scheduler = _runtime.get_scheduler
get_state_store = _control_plane.get_state_store
get_factor_pool = _control_plane.get_factor_pool
_ensure_run_record = _control_plane._ensure_run_record
_update_run_record = _control_plane._update_run_record
_write_snapshot = _control_plane._write_snapshot
_persist_cio_report = _control_plane._persist_cio_report

__all__ = [
    "NODE_MARKET_CONTEXT", "NODE_HYPOTHESIS_GEN", "NODE_SYNTHESIS",
    "NODE_PREFILTER", "NODE_EXPLORATION", "NODE_NOTE_REFINEMENT",
    "NODE_CODER", "NODE_JUDGMENT", "NODE_PORTFOLIO", "NODE_REPORT",
    "NODE_HUMAN_GATE", "NODE_LOOP_CONTROL",
    "MAX_ROUNDS", "REPORT_EVERY_N_ROUNDS", "ACTIVE_ISLANDS", "REPORTS_DIR",
    "MAX_CONCURRENT_BACKTESTS",
    "get_scheduler", "get_state_store", "get_factor_pool",
    "_ensure_run_record", "_update_run_record", "_write_snapshot",
    "_persist_cio_report",
    "market_context_node", "hypothesis_gen_node", "synthesis_node",
    "note_refinement_node", "prefilter_node", "exploration_node",
    "coder_node", "judgment_node", "portfolio_node", "report_node",
    "human_gate_node", "loop_control_node",
    "route_after_prefilter", "route_after_judgment", "route_after_portfolio",
    "route_after_human", "route_loop",
    "build_graph", "get_graph", "get_latest_config",
    "run_evolve", "run_single",
]


def __getattr__(name: str):
    if name in {
        "MAX_ROUNDS",
        "ACTIVE_ISLANDS",
        "REPORT_EVERY_N_ROUNDS",
        "MAX_CONCURRENT_BACKTESTS",
        "REPORTS_DIR",
    }:
        return getattr(_config, name)
    if name in {"_scheduler", "_current_run_id", "_graph", "_graph_config"}:
        return getattr(_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
