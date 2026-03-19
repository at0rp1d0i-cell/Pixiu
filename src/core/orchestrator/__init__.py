"""
Pixiu v2 Orchestrator package.

All public symbols are defined or re-exported here so that existing callers
using ``from src.core.orchestrator import X`` continue to work unchanged.
Mutable module-level state (_current_run_id, _scheduler) lives here so that
test monkeypatching targets the correct namespace.
"""
# ruff: noqa: E402
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from src.schemas.state import AgentState

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─────────────────────────────────────────────────────────
# 配置常量
# ─────────────────────────────────────────────────────────
MAX_ROUNDS: int = int(os.getenv("MAX_ROUNDS", "100"))
ACTIVE_ISLANDS: list[str] = os.getenv(
    "ACTIVE_ISLANDS", "momentum,northbound,valuation,volatility,volume,sentiment"
).split(",")
REPORT_EVERY_N_ROUNDS: int = int(os.getenv("REPORT_EVERY_N_ROUNDS", "5"))
MAX_CONCURRENT_BACKTESTS: int = int(os.getenv("MAX_CONCURRENT_BACKTESTS", "2"))

REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"

# ─────────────────────────────────────────────────────────
# 节点名称常量
# ─────────────────────────────────────────────────────────
NODE_MARKET_CONTEXT  = "market_context"
NODE_HYPOTHESIS_GEN  = "hypothesis_gen"
NODE_SYNTHESIS       = "synthesis"
NODE_PREFILTER       = "prefilter"
NODE_EXPLORATION     = "exploration"
NODE_NOTE_REFINEMENT = "note_refinement"
NODE_CODER           = "coder"
NODE_JUDGMENT        = "judgment"
NODE_PORTFOLIO       = "portfolio"
NODE_REPORT          = "report"
NODE_HUMAN_GATE      = "human_gate"
NODE_LOOP_CONTROL    = "loop_control"

# ─────────────────────────────────────────────────────────
# 模块级调度器（跨轮次复用）
# ─────────────────────────────────────────────────────────
_scheduler = None
_current_run_id: Optional[str] = None
_graph = None  # Exposed here for test monkeypatching (orch._graph = None to reset)


def get_scheduler():
    from src.factor_pool.pool import get_factor_pool
    from src.factor_pool.scheduler import IslandScheduler

    global _scheduler
    if _scheduler is None:
        pool = get_factor_pool()
        _scheduler = IslandScheduler(pool=pool)
    return _scheduler


def get_state_store():
    from src.control_plane.state_store import get_state_store as _get_state_store
    return _get_state_store()


def get_factor_pool():
    from src.factor_pool.pool import get_factor_pool as _get_factor_pool
    return _get_factor_pool()


def _ensure_run_record(mode: str = "adhoc") -> Optional[str]:
    global _current_run_id
    if _current_run_id:
        return _current_run_id
    try:
        record = get_state_store().create_run(mode=mode)
        _current_run_id = record.run_id
        return _current_run_id
    except Exception as e:
        logger.warning("[ControlPlane] 创建 run 记录失败: %s", e)
        return None


def _update_run_record(stage: str, **fields) -> None:
    run_id = _ensure_run_record()
    if not run_id:
        return
    try:
        get_state_store().update_run(run_id, current_stage=stage, **fields)
    except Exception as e:
        logger.warning("[ControlPlane] 更新 run 记录失败: %s", e)


def _write_snapshot(state: AgentState, stage: str, awaiting_human_approval: Optional[bool] = None) -> None:
    from src.schemas.control_plane import RunSnapshot

    run_id = _ensure_run_record()
    if not run_id:
        return
    try:
        snapshot = RunSnapshot(
            run_id=run_id,
            approved_notes_count=len(state.approved_notes),
            backtest_reports_count=len(state.backtest_reports),
            verdicts_count=len(state.critic_verdicts),
            awaiting_human_approval=(
                state.awaiting_human_approval
                if awaiting_human_approval is None
                else awaiting_human_approval
            ),
            updated_at=datetime.now(UTC),
        )
        get_state_store().write_snapshot(snapshot)
        _update_run_record(stage, current_round=state.current_round)
    except Exception as e:
        logger.warning("[ControlPlane] 写 snapshot 失败: %s", e)


def _persist_cio_report(cio_report) -> None:
    from src.schemas.control_plane import ArtifactRecord
    import src.core.orchestrator as _self

    run_id = _ensure_run_record()
    if not run_id:
        return
    try:
        report_dir = _self.REPORTS_DIR / run_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{cio_report.report_id}.md"
        report_path.write_text(cio_report.full_report_markdown, encoding="utf-8")
        get_state_store().append_artifact(
            ArtifactRecord(
                run_id=run_id,
                kind="cio_report",
                ref_id=cio_report.report_id,
                path=str(report_path),
            )
        )
    except Exception as e:
        logger.warning("[ControlPlane] 持久化 CIO 报告失败: %s", e)


# ─────────────────────────────────────────────────────────
# Node imports (lazy, to avoid circular imports at module load)
# ─────────────────────────────────────────────────────────
from src.core.orchestrator.nodes.stage1 import market_context_node
from src.core.orchestrator.nodes.stage2 import (
    hypothesis_gen_node,
    synthesis_node,
    note_refinement_node,
)
from src.core.orchestrator.nodes.stage3 import prefilter_node
from src.core.orchestrator.nodes.stage4 import exploration_node, coder_node
from src.core.orchestrator.nodes.stage5 import judgment_node, portfolio_node, report_node
from src.core.orchestrator.nodes.control import human_gate_node, loop_control_node

# ─────────────────────────────────────────────────────────
# Graph imports
# ─────────────────────────────────────────────────────────
from src.core.orchestrator.graph import (
    route_after_prefilter,
    route_after_judgment,
    route_after_portfolio,
    route_after_human,
    route_loop,
    build_graph,
    get_graph,
    get_latest_config,
)

# ─────────────────────────────────────────────────────────
# 入口函数
# ─────────────────────────────────────────────────────────
from src.core.orchestrator._entrypoints import run_evolve, run_single


__all__ = [
    # constants
    "NODE_MARKET_CONTEXT", "NODE_HYPOTHESIS_GEN", "NODE_SYNTHESIS",
    "NODE_PREFILTER", "NODE_EXPLORATION", "NODE_NOTE_REFINEMENT",
    "NODE_CODER", "NODE_JUDGMENT", "NODE_PORTFOLIO", "NODE_REPORT",
    "NODE_HUMAN_GATE", "NODE_LOOP_CONTROL",
    "MAX_ROUNDS", "REPORT_EVERY_N_ROUNDS", "ACTIVE_ISLANDS", "REPORTS_DIR",
    # infrastructure
    "get_scheduler", "get_state_store", "get_factor_pool",
    "_current_run_id", "_ensure_run_record", "_update_run_record",
    "_write_snapshot", "_persist_cio_report",
    # nodes
    "market_context_node", "hypothesis_gen_node", "synthesis_node",
    "note_refinement_node", "prefilter_node", "exploration_node",
    "coder_node", "judgment_node", "portfolio_node", "report_node",
    "human_gate_node", "loop_control_node",
    # routing
    "route_after_prefilter", "route_after_judgment", "route_after_portfolio",
    "route_after_human", "route_loop",
    # graph
    "build_graph", "get_graph", "get_latest_config",
    # entry points
    "run_evolve", "run_single",
]
