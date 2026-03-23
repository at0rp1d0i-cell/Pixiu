"""Orchestrator control-plane helpers.

These helpers manage run records, snapshots, and CIO report persistence.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from . import config, runtime
from src.control_plane.state_store import get_state_store as _get_state_store
from src.llm.usage_ledger import get_run_usage_snapshot
from src.schemas.control_plane import ArtifactRecord, RunSnapshot
from src.schemas.state import AgentState

logger = logging.getLogger(__name__)


def get_state_store():
    return _get_state_store()


def get_factor_pool():
    from src.factor_pool.pool import get_factor_pool as _get_factor_pool

    return _get_factor_pool()


def _ensure_run_record(mode: str = "adhoc") -> Optional[str]:
    run_id = runtime.get_current_run_id()
    if run_id:
        return run_id
    try:
        record = get_state_store().create_run(mode=mode)
        runtime.set_current_run_id(record.run_id)
        return record.run_id
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
    run_id = _ensure_run_record()
    if not run_id:
        return
    try:
        llm_usage = get_run_usage_snapshot(run_id=run_id)
        snapshot = RunSnapshot(
            run_id=run_id,
            approved_notes_count=len(state.approved_notes),
            backtest_reports_count=len(state.backtest_reports),
            verdicts_count=len(state.critic_verdicts),
            llm_calls=llm_usage["calls"],
            llm_prompt_tokens=llm_usage["prompt_tokens"],
            llm_completion_tokens=llm_usage["completion_tokens"],
            llm_total_tokens=llm_usage["total_tokens"],
            llm_estimated_cost_usd=llm_usage["estimated_cost_usd"],
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
    run_id = _ensure_run_record()
    if not run_id:
        return
    try:
        report_dir = config.REPORTS_DIR / run_id
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
