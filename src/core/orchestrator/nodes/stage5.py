"""Stage 5: Judgment, portfolio, and report nodes."""
import asyncio
import logging
from typing import Optional

from src.schemas.state import AgentState
from src.schemas.stage_io import JudgmentOutput, PortfolioOutput, ReportOutput

logger = logging.getLogger(__name__)


def judgment_node(state: AgentState) -> JudgmentOutput:
    """Stage 5: Critic + RiskAuditor + FactorPool 写入。"""
    from src.agents.judgment import Critic, RiskAuditor, ConstraintExtractor
    import src.core.orchestrator as _orch
    get_factor_pool = _orch.get_factor_pool
    _write_snapshot = _orch._write_snapshot
    NODE_JUDGMENT = _orch.NODE_JUDGMENT

    if not state.backtest_reports:
        logger.warning("[Stage 5] 无回测报告，跳过 Judgment")
        return {"critic_verdicts": [], "risk_audit_reports": []}

    logger.info("[Stage 5] 评判 %d 个回测报告...", len(state.backtest_reports))

    pool = get_factor_pool()
    verdicts = []
    risk_reports = []

    async def _run_judgment():
        critic = Critic()
        auditor = RiskAuditor(factor_pool=pool)
        note_map: dict[str, object] = {
            note.note_id: note
            for note in state.approved_notes
        }
        extractor = ConstraintExtractor()
        regime: Optional[str] = (
            state.market_context.market_regime.value
            if state.market_context is not None
            else None
        )
        for report in state.backtest_reports:
            verdict = await critic.evaluate(report, regime=regime)
            verdicts.append(verdict)
            logger.info(
                "[Stage 5] %s → passed=%s, failure=%s",
                report.factor_id, verdict.overall_passed, verdict.failure_mode or "—",
            )
            risk_report = await auditor.audit(report)
            risk_reports.append(risk_report)
            if verdict.register_to_pool:
                note = note_map.get(report.note_id)
                hypothesis = note.hypothesis if note else ""
                try:
                    pool.register_factor(
                        report=report,
                        verdict=verdict,
                        risk_report=risk_report,
                        hypothesis=hypothesis,
                    )
                except Exception as e:
                    logger.warning("[Stage 5] FactorPool 写入失败: %s", e)
            if not verdict.overall_passed:
                note = note_map.get(report.note_id)
                if note is not None:
                    try:
                        constraint = extractor.extract(verdict, note)
                        if constraint is not None:
                            pool.register_constraint(constraint)
                            logger.info(
                                "[Stage 5] 约束写入: %s → island=%s, mode=%s",
                                constraint.constraint_id, constraint.island,
                                constraint.failure_mode.value,
                            )
                    except Exception as e:
                        logger.warning("[Stage 5] ConstraintExtractor 失败，静默降级: %s", e)

    asyncio.run(_run_judgment())

    passed_count = sum(1 for v in verdicts if v.overall_passed)
    logger.info("[Stage 5] 通过: %d/%d", passed_count, len(verdicts))
    result = {"critic_verdicts": verdicts, "risk_audit_reports": risk_reports}
    _write_snapshot(state.model_copy(update=result), NODE_JUDGMENT)
    return result


def portfolio_node(state: AgentState) -> PortfolioOutput:
    """Stage 5b: PortfolioManager 更新组合权重。"""
    from src.agents.judgment import PortfolioManager
    import src.core.orchestrator as _orch
    get_factor_pool = _orch.get_factor_pool

    logger.info("[Stage 5b] 更新组合权重...")

    async def _run():
        pm = PortfolioManager(factor_pool=get_factor_pool())
        allocation = await pm.rebalance(state)
        return allocation

    try:
        allocation = asyncio.run(_run())
        logger.info("[Stage 5b] 组合更新完成：%d 个因子", len(allocation.factor_weights))
        return {"portfolio_allocation": allocation}
    except Exception as e:
        logger.error("[Stage 5b] Portfolio 更新失败: %s", e)
        return {"last_error": str(e), "error_stage": "portfolio"}


def report_node(state: AgentState) -> ReportOutput:
    """Stage 5c: ReportWriter 生成 CIOReport，标记等待人类审批。"""
    from src.agents.judgment import ReportWriter
    import src.core.orchestrator as _orch
    _persist_cio_report = _orch._persist_cio_report
    _update_run_record = _orch._update_run_record
    _write_snapshot = _orch._write_snapshot
    NODE_REPORT = _orch.NODE_REPORT

    logger.info("[Stage 5c] 生成 CIO 报告 (Round %d)...", state.current_round)

    async def _run():
        writer = ReportWriter()
        return await writer.generate_cio_report(state)

    try:
        cio_report = asyncio.run(_run())
        logger.info("[Stage 5c] CIO 报告生成完成，等待审批...")
        result = {
            "cio_report": cio_report,
            "awaiting_human_approval": True,
            "human_decision": None,
        }
        next_state = state.model_copy(update=result)
        _persist_cio_report(cio_report)
        _update_run_record(NODE_REPORT, status="awaiting_human_approval")
        _write_snapshot(next_state, NODE_REPORT, awaiting_human_approval=True)
        return result
    except Exception as e:
        logger.error("[Stage 5c] 报告生成失败: %s", e)
        _update_run_record(NODE_REPORT, status="failed", last_error=str(e))
        return {"last_error": str(e), "error_stage": "report", "awaiting_human_approval": True}
