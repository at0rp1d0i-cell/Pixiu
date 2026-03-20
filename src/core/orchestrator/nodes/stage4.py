"""Stage 4: Exploration and coder (backtest execution) nodes."""
import asyncio
import logging
import uuid

from src.schemas.state import AgentState
from src.schemas.stage_io import ExplorationOutput, CoderOutput
from src.core.orchestrator._context import NODE_CODER

logger = logging.getLogger(__name__)


def exploration_node(state: AgentState) -> ExplorationOutput:
    """Stage 4a: 对有 exploration_questions 的 Note 执行 EDA。"""
    from src.execution.exploration_agent import ExplorationAgent

    notes_needing_exploration = [
        n for n in state.approved_notes
        if n.exploration_questions and n.final_formula is None
    ]

    if not notes_needing_exploration:
        logger.info("[Stage 4a] 无需探索，直接进入 note_refinement")
        return {"exploration_results": []}

    logger.info("[Stage 4a] 探索 %d 个 Notes...", len(notes_needing_exploration))

    async def _run_all():
        agent = ExplorationAgent()
        results = []
        for note in notes_needing_exploration:
            try:
                result = await agent.explore(note)
                results.append(result)
                logger.info("[Stage 4a] 探索完成: %s", note.note_id)
            except Exception as e:
                logger.warning("[Stage 4a] 探索失败 %s: %s", note.note_id, e)
        return results

    exploration_results = asyncio.run(_run_all())
    return {"exploration_results": exploration_results}


def coder_node(state: AgentState) -> CoderOutput:
    """Stage 4b: 对每个 approved_note 调用 Coder 执行 Qlib 回测。

    串行执行（Docker 资源限制），每个 note 生成一个 BacktestReport。
    """
    from src.execution.coder import Coder
    from src.schemas.backtest import BacktestReport, BacktestMetrics
    from .. import control_plane as _control_plane
    _write_snapshot = _control_plane._write_snapshot

    notes = state.approved_notes
    if not notes:
        logger.warning("[Stage 4b] 无待回测 Note，跳过")
        return {"backtest_reports": []}

    logger.info("[Stage 4b] 开始回测 %d 个因子...", len(notes))

    async def _run_all():
        coder = Coder()
        reports = []
        updated_notes = []

        for note in notes:
            formula = note.final_formula or note.proposed_formula
            factor_id = note.note_id
            logger.info("[Stage 4b] 回测: %s → %s", factor_id, formula[:60])

            try:
                report = await coder.run_backtest(note)
                reports.append(report)
                updated_notes.append(note.model_copy(update={"status": "completed"}))
                logger.info("[Stage 4b] %s 完成 (passed=%s)", report.factor_id, report.passed)

            except Exception as e:
                logger.error("[Stage 4b] %s 失败: %s", factor_id, e)
                reports.append(BacktestReport(
                    report_id=str(uuid.uuid4()),
                    note_id=note.note_id,
                    factor_id=factor_id,
                    island=note.island,
                    formula=formula,
                    passed=False,
                    execution_succeeded=False,
                    status="failed",
                    failure_stage="run",
                    failure_reason="orchestrator_execution_exception",
                    execution_time_seconds=0.0,
                    qlib_output_raw="",
                    error_message=str(e),
                    metrics=BacktestMetrics(
                        sharpe=0.0, annualized_return=0.0, max_drawdown=0.0,
                        ic_mean=0.0, ic_std=0.0, icir=0.0, turnover_rate=0.0,
                    ),
                ))
                updated_notes.append(note.model_copy(update={"status": "completed"}))

        return reports, updated_notes

    reports, updated_notes = asyncio.run(_run_all())

    logger.info("[Stage 4b] 回测完成：%d/%d 成功", sum(1 for r in reports if r.passed), len(reports))
    result = {
        "backtest_reports": list(state.backtest_reports) + reports,
        "approved_notes": updated_notes,
    }
    _write_snapshot(state.model_copy(update=result), NODE_CODER)
    return result
