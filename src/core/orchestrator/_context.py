"""
Infrastructure helpers: singleton getters, run record management, snapshots.
Also holds node-name constants (imported by both graph.py and node files).
"""
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from src.schemas.state import AgentState

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parents[3] / "data" / "reports"

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
        _update_run_record(stage)
    except Exception as e:
        logger.warning("[ControlPlane] 写 snapshot 失败: %s", e)


def _persist_cio_report(cio_report) -> None:
    from src.schemas.control_plane import ArtifactRecord

    run_id = _ensure_run_record()
    if not run_id:
        return

    try:
        report_dir = REPORTS_DIR / run_id
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
