"""
Pixiu v2 Orchestrator（完全重写）

完整的 12 节点 LangGraph 图，实现高通量漏斗架构：
  Stage 1: market_context（MarketAnalyst + LiteratureMiner）
  Stage 2: hypothesis_gen → synthesis
  Stage 3: prefilter
  Stage 4: exploration → note_refinement → coder
  Stage 5: judgment → portfolio → report
  Human Gate: interrupt() 等待 CIO 审批
  Loop Control: 调度下一轮

依赖设计：docs/design/orchestrator.md
"""
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.schemas.state import AgentState
from src.schemas.market_context import MarketContextMemo
from src.factor_pool.islands import ISLANDS
from src.factor_pool.scheduler import IslandScheduler
from src.factor_pool.pool import get_factor_pool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─────────────────────────────────────────────────────────
# 配置常量（从 env 读取或使用默认值）
# ─────────────────────────────────────────────────────────
import os

MAX_ROUNDS: int = int(os.getenv("MAX_ROUNDS", "100"))
ACTIVE_ISLANDS: List[str] = os.getenv(
    "ACTIVE_ISLANDS", "momentum,northbound,valuation,volatility,volume,sentiment"
).split(",")
REPORT_EVERY_N_ROUNDS: int = int(os.getenv("REPORT_EVERY_N_ROUNDS", "5"))
MAX_CONCURRENT_BACKTESTS: int = int(os.getenv("MAX_CONCURRENT_BACKTESTS", "2"))

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
REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"

# ─────────────────────────────────────────────────────────
# 模块级调度器（跨轮次复用）
# ─────────────────────────────────────────────────────────
_scheduler: Optional[IslandScheduler] = None
_current_run_id: Optional[str] = None

def get_scheduler() -> IslandScheduler:
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


# ─────────────────────────────────────────────────────────
# Stage 1：市场上下文节点
# ─────────────────────────────────────────────────────────
def market_context_node(state: AgentState) -> dict:
    """Stage 1: MarketAnalyst + LiteratureMiner，生成 MarketContextMemo。"""
    from src.agents.market_analyst import market_context_node as _market_node

    logger.info("[Stage 1] 生成市场上下文... (Round %d)", state.current_round)

    try:
        result = _market_node(dict(state))
        memo: MarketContextMemo = result.get("market_context")

        # 将 LiteratureMiner 的历史洞察合并进 Memo
        try:
            from src.agents.literature_miner import LiteratureMiner
            pool = get_factor_pool()
            miner = LiteratureMiner(factor_pool=pool)
            insights = asyncio.run(miner.retrieve_insights(active_islands=ACTIVE_ISLANDS))
            if memo and not memo.historical_insights:
                # Pydantic is immutable - rebuild with insights
                memo = memo.model_copy(update={"historical_insights": insights})
        except Exception as e:
            logger.warning("[Stage 1] LiteratureMiner 失败（跳过）: %s", e)

        logger.info("[Stage 1] 市场上下文完成，Regime=%s", getattr(memo, "market_regime", "unknown"))
        return {"market_context": memo}
    except Exception as e:
        logger.error("[Stage 1] 失败: %s", e)
        return {"last_error": str(e), "error_stage": "market_context"}


# ─────────────────────────────────────────────────────────
# Stage 2a：假设生成节点
# ─────────────────────────────────────────────────────────
def hypothesis_gen_node(state: AgentState) -> dict:
    """Stage 2: 并行调用所有 Island 的 AlphaResearcher，展开 Batch。"""
    from src.agents.researcher import hypothesis_gen_node as _gen_node

    logger.info("[Stage 2] 并行生成假设... (Round %d)", state.current_round)

    # 注入 active_islands（从调度器选择）
    scheduler = get_scheduler()
    active = getattr(scheduler, "get_active_islands", lambda: ACTIVE_ISLANDS)()

    enriched = dict(state)
    enriched["active_islands"] = active
    enriched["iteration"] = state.current_round

    try:
        result = _gen_node(enriched)
        notes = result.get("research_notes", [])
        logger.info("[Stage 2] 生成 %d 个候选", len(notes))
        return {
            "research_notes": notes,
            "hypotheses": result.get("hypotheses", []),
            "strategy_specs": result.get("strategy_specs", []),
            "subspace_generated": result.get("subspace_generated", {}),
        }
    except Exception as e:
        logger.error("[Stage 2] 假设生成失败: %s", e)
        return {"research_notes": [], "hypotheses": [], "strategy_specs": [], "subspace_generated": {}, "last_error": str(e), "error_stage": "hypothesis_gen"}


# ─────────────────────────────────────────────────────────
# Stage 2b：Synthesis（跨 Island 洞察）
# ─────────────────────────────────────────────────────────
def synthesis_node(state: AgentState) -> dict:
    """Stage 2b: SynthesisAgent 去重、聚类、提出 merge 建议。

    任何失败均降级为 pass-through（返回 {}），不阻塞主链。
    """
    from src.agents.synthesis import SynthesisAgent

    notes = state.research_notes
    if len(notes) <= 1:
        logger.info("[Stage 2b] Synthesis: <= 1 个候选，跳过")
        return {}

    logger.info("[Stage 2b] Synthesis: 处理 %d 个候选...", len(notes))

    async def _run():
        agent = SynthesisAgent()
        return await agent.synthesize(notes)

    try:
        result = asyncio.run(_run())
        removed = len(notes) - len(result.filtered_notes)
        logger.info(
            "[Stage 2b] Synthesis 完成：去重 %d 个，识别 %d 个 family，%d 个 merge 建议",
            removed,
            len(result.families),
            len(result.merge_candidates),
        )
        return {
            "research_notes": result.filtered_notes,
            "synthesis_insights": result.insights + result.merge_candidates,
        }
    except Exception as e:
        logger.warning("[Stage 2b] Synthesis 失败（降级为 pass-through）: %s", e)
        return {}


# ─────────────────────────────────────────────────────────
# Stage 3：前置过滤
# ─────────────────────────────────────────────────────────
def prefilter_node(state: AgentState) -> dict:
    """Stage 3: Validator + NoveltyFilter + AlignmentChecker，最多放行 Top K。"""
    from src.agents.prefilter import prefilter_node as _prefilter

    logger.info("[Stage 3] 过滤 %d 个候选...", len(state.research_notes))
    result = _prefilter(dict(state))
    approved = result.get("approved_notes", [])
    # filtered = Synthesis 去重后的候选数 - Prefilter 放行数（非 Stage 2 原始生成数）
    filtered = len(state.research_notes) - len(approved)
    logger.info("[Stage 3] 放行 %d 个，淘汰 %d 个（基准：Synthesis 后 %d 个）", len(approved), filtered, len(state.research_notes))
    return {"approved_notes": approved, "filtered_count": filtered}


# ─────────────────────────────────────────────────────────
# Stage 4a：探索性分析
# ─────────────────────────────────────────────────────────
def exploration_node(state: AgentState) -> dict:
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


# ─────────────────────────────────────────────────────────
# Stage 4a→2：Note 精化
# ─────────────────────────────────────────────────────────
def note_refinement_node(state: AgentState) -> dict:
    """Stage 4a→2: 将 ExplorationResult 反馈给对应 ResearchNote，更新 final_formula。"""
    if not state.exploration_results:
        return {}

    # 建立 note_id → ExplorationResult 映射
    result_map = {r.note_id: r for r in state.exploration_results}

    updated_notes = []
    for note in state.approved_notes:
        if note.note_id in result_map:
            er = result_map[note.note_id]
            # 用探索结果精化 final_formula
            refined_formula = er.refined_formula_suggestion or note.proposed_formula
            note = note.model_copy(update={
                "final_formula": refined_formula,
                "status": "ready_for_backtest",
            })
            logger.info("[Stage 4a→2] 精化 %s: %s", note.note_id, refined_formula[:60])
        else:
            # 无探索结果，直接用 proposed_formula
            note = note.model_copy(update={"final_formula": note.proposed_formula, "status": "ready_for_backtest"})
        updated_notes.append(note)

    return {"approved_notes": updated_notes}


# ─────────────────────────────────────────────────────────
# Stage 4b：回测执行
# ─────────────────────────────────────────────────────────
def coder_node(state: AgentState) -> dict:
    """Stage 4b: 对每个 approved_note 调用 Coder 执行 Qlib 回测。

    串行执行（Docker 资源限制），每个 note 生成一个 BacktestReport。
    """
    from src.execution.coder import Coder
    from src.schemas.backtest import BacktestReport, BacktestMetrics
    import uuid

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


# ─────────────────────────────────────────────────────────
# Stage 5：判断
# ─────────────────────────────────────────────────────────
def judgment_node(state: AgentState) -> dict:
    """Stage 5: Critic + RiskAuditor + FactorPool 写入。"""
    from src.agents.judgment import Critic, RiskAuditor, ConstraintExtractor

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
        # 构建 note_id → note 映射，用于写入 pool 时携带语义锚点，以及约束提取
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
            # Critic 评判
            verdict = await critic.evaluate(report, regime=regime)
            verdicts.append(verdict)
            logger.info(
                "[Stage 5] %s → passed=%s, failure=%s",
                report.factor_id, verdict.overall_passed, verdict.failure_mode or "—",
            )
            # RiskAuditor
            risk_report = await auditor.audit(report)
            risk_reports.append(risk_report)
            # FactorPool 写入
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
            # ConstraintExtractor：对失败 verdict 提取并写入约束
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


# ─────────────────────────────────────────────────────────
# Stage 5b：Portfolio Manager
# ─────────────────────────────────────────────────────────
def portfolio_node(state: AgentState) -> dict:
    """Stage 5b: PortfolioManager 更新组合权重。"""
    from src.agents.judgment import PortfolioManager

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


# ─────────────────────────────────────────────────────────
# Stage 5c：CIO 报告生成
# ─────────────────────────────────────────────────────────
def report_node(state: AgentState) -> dict:
    """Stage 5c: ReportWriter 生成 CIOReport，标记等待人类审批。"""
    from src.agents.judgment import ReportWriter

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


# ─────────────────────────────────────────────────────────
# Human Gate（interrupt() 等待点）
# ─────────────────────────────────────────────────────────
def human_gate_node(state: AgentState) -> dict:
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


# ─────────────────────────────────────────────────────────
# Loop Control
# ─────────────────────────────────────────────────────────
def loop_control_node(state: AgentState) -> dict:
    """轮次控制：更新调度器，清空本轮状态，递增 current_round。"""
    from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
    from src.schemas.hypothesis import ExplorationSubspace

    scheduler = get_scheduler()

    # 更新调度器：对通过的因子记录 island，用于 leaderboard 更新
    epoch_island: str | None = None
    for verdict in state.critic_verdicts:
        if verdict.overall_passed:
            matching = [r for r in state.backtest_reports if r.factor_id == verdict.factor_id]
            if matching:
                epoch_island = matching[0].island
                break

    # 无论本轮是否有因子通过，都调用一次 on_epoch_done，确保温度退火正常进行
    island_for_epoch = epoch_island or (state.current_island or "unknown")
    scheduler.on_epoch_done(island_for_epoch, state.current_round)

    # ── SubspaceScheduler 反馈回路 ──────────────────────────
    # generated_count 来自 state.subspace_generated（researcher 写入的原始生成数量）
    # passed_count 来自 critic_verdicts.overall_passed（通过回测的数量）
    subspace_scheduler = SubspaceScheduler()

    # 恢复或初始化 SchedulerState
    raw_sched_state = state.scheduler_state
    if raw_sched_state:
        sched_state = SchedulerState(**raw_sched_state)
    else:
        sched_state = SchedulerState()

    # 构建 note_id → exploration_subspace 映射（用于 passed 统计）
    note_subspace: dict[str, str | None] = {
        note.note_id: (note.exploration_subspace.value if note.exploration_subspace else None)
        for note in state.approved_notes
    }
    # 构建 factor_id → note_id 映射（通过 backtest_reports）
    factor_to_note: dict[str, str] = {
        r.factor_id: r.note_id
        for r in state.backtest_reports
    }

    # 聚合 generated_count：从 state.subspace_generated 读取 Stage 2 原始生成数量
    # state.subspace_generated 格式: {subspace.value: count}，由 researcher 写入
    generated: dict[str, int] = dict(state.subspace_generated) if state.subspace_generated else {}

    # 聚合 passed_count（以 critic_verdicts.overall_passed 为准）
    passed: dict[str, int] = {}
    for verdict in state.critic_verdicts:
        if verdict.overall_passed:
            note_id = factor_to_note.get(verdict.factor_id)
            if note_id:
                subspace_val = note_subspace.get(note_id)
                if subspace_val:
                    passed[subspace_val] = passed.get(subspace_val, 0) + 1

    # 构建 SubspaceScheduler.update_state() 所需格式
    subspace_results: dict[ExplorationSubspace, tuple[int, int]] = {}
    for subspace in ExplorationSubspace:
        g = generated.get(subspace.value, 0)
        p = passed.get(subspace.value, 0)
        subspace_results[subspace] = (g, p)

    updated_sched_state = subspace_scheduler.update_state(sched_state, subspace_results)

    # 记录调度器警告
    for warning in subspace_scheduler.get_warnings(updated_sched_state):
        logger.warning("[Loop Control] SubspaceScheduler: %s", warning)

    next_round = state.current_round + 1
    logger.info(
        "[Loop Control] 进入第 %d 轮 (scheduler warm_start=%s, total_passed=%s)",
        next_round,
        updated_sched_state.warm_start,
        sum(updated_sched_state.total_passed.values()),
    )

    # 清空本轮临时状态，保留跨轮次持久数据
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


# ─────────────────────────────────────────────────────────
# 条件路由函数
# ─────────────────────────────────────────────────────────
def route_after_prefilter(state: AgentState) -> str:
    if not state.approved_notes:
        logger.info("[Route] prefilter → loop_control（无通过候选）")
        return NODE_LOOP_CONTROL
    has_exploration = any(
        note.exploration_questions
        for note in state.approved_notes
        if note.final_formula is None
    )
    target = NODE_EXPLORATION if has_exploration else NODE_CODER
    logger.info("[Route] prefilter → %s", target)
    return target


def route_after_judgment(state: AgentState) -> str:
    new_passes = [v for v in state.critic_verdicts if v.overall_passed]
    if new_passes:
        target = NODE_PORTFOLIO
    else:
        target = NODE_LOOP_CONTROL
    logger.info("[Route] judgment → %s（%d 个通过）", target, len(new_passes))
    return target


def route_after_portfolio(state: AgentState) -> str:
    """每 N 轮或有重大新发现时生成报告。"""
    if state.current_round > 0 and state.current_round % REPORT_EVERY_N_ROUNDS == 0:
        return NODE_REPORT
    # 有超越基线的因子，立即报告
    from src.schemas.thresholds import THRESHOLDS
    has_breakthrough = any(
        r.metrics.sharpe > THRESHOLDS.min_sharpe * 1.1  # 超越基线 10%
        for r in state.backtest_reports
        if r.passed
    )
    if has_breakthrough:
        return NODE_REPORT
    return NODE_LOOP_CONTROL


def route_after_human(state: AgentState) -> str:
    decision = state.human_decision or "approve"
    if decision == "stop":
        logger.info("[Route] human_gate → END（用户停止）")
        return END
    if decision.startswith("redirect:"):
        logger.info("[Route] human_gate → hypothesis_gen（重定向）")
        return NODE_HYPOTHESIS_GEN
    logger.info("[Route] human_gate → loop_control（批准继续）")
    return NODE_LOOP_CONTROL


def route_loop(state: AgentState) -> str:
    if state.current_round >= MAX_ROUNDS:
        logger.info("[Route] loop_control → END（达到最大轮次 %d）", MAX_ROUNDS)
        return END
    return NODE_MARKET_CONTEXT


# ─────────────────────────────────────────────────────────
# 图构建
# ─────────────────────────────────────────────────────────
_graph = None
_graph_config = None


def build_graph():
    """构建完整 v2 LangGraph 图。"""
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node(NODE_MARKET_CONTEXT,  market_context_node)
    graph.add_node(NODE_HYPOTHESIS_GEN,  hypothesis_gen_node)
    graph.add_node(NODE_SYNTHESIS,       synthesis_node)
    graph.add_node(NODE_PREFILTER,       prefilter_node)
    graph.add_node(NODE_EXPLORATION,     exploration_node)
    graph.add_node(NODE_NOTE_REFINEMENT, note_refinement_node)
    graph.add_node(NODE_CODER,           coder_node)
    graph.add_node(NODE_JUDGMENT,        judgment_node)
    graph.add_node(NODE_PORTFOLIO,       portfolio_node)
    graph.add_node(NODE_REPORT,          report_node)
    graph.add_node(NODE_HUMAN_GATE,      human_gate_node)
    graph.add_node(NODE_LOOP_CONTROL,    loop_control_node)

    # 固定边
    graph.add_edge(START,               NODE_MARKET_CONTEXT)
    graph.add_edge(NODE_MARKET_CONTEXT, NODE_HYPOTHESIS_GEN)
    graph.add_edge(NODE_HYPOTHESIS_GEN, NODE_SYNTHESIS)
    graph.add_edge(NODE_SYNTHESIS,      NODE_PREFILTER)
    graph.add_edge(NODE_EXPLORATION,    NODE_NOTE_REFINEMENT)
    graph.add_edge(NODE_NOTE_REFINEMENT,NODE_CODER)
    graph.add_edge(NODE_CODER,          NODE_JUDGMENT)

    # 条件边
    graph.add_conditional_edges(NODE_PREFILTER,  route_after_prefilter, {
        NODE_EXPLORATION:     NODE_EXPLORATION,
        NODE_CODER:           NODE_CODER,
        NODE_LOOP_CONTROL:    NODE_LOOP_CONTROL,
    })
    graph.add_conditional_edges(NODE_JUDGMENT, route_after_judgment, {
        NODE_PORTFOLIO:    NODE_PORTFOLIO,
        NODE_LOOP_CONTROL: NODE_LOOP_CONTROL,
    })
    graph.add_conditional_edges(NODE_PORTFOLIO, route_after_portfolio, {
        NODE_REPORT:       NODE_REPORT,
        NODE_LOOP_CONTROL: NODE_LOOP_CONTROL,
    })
    graph.add_conditional_edges(NODE_HUMAN_GATE, route_after_human, {
        NODE_LOOP_CONTROL:    NODE_LOOP_CONTROL,
        NODE_HYPOTHESIS_GEN:  NODE_HYPOTHESIS_GEN,
        END:                  END,
    })
    graph.add_conditional_edges(NODE_LOOP_CONTROL, route_loop, {
        NODE_MARKET_CONTEXT: NODE_MARKET_CONTEXT,
        END:                 END,
    })

    return graph.compile(
        checkpointer=MemorySaver(),
        interrupt_before=[NODE_HUMAN_GATE],  # 在进入 human_gate 前暂停
    )


def get_graph():
    """获取编译好的图单例（供 CLI 的 approve/redirect/stop 注入状态）。"""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def get_latest_config() -> dict:
    """获取最近一次 run 的 LangGraph config（供 CLI 注入 human_decision）。"""
    global _graph_config
    return _graph_config or {}


# ─────────────────────────────────────────────────────────
# 入口函数
# ─────────────────────────────────────────────────────────
async def run_evolve(rounds: int = 20, islands: list[str] | None = None):
    """进化模式：多 Island 轮换，持续运行 rounds 轮。"""
    global _graph_config, _current_run_id

    if islands:
        global ACTIVE_ISLANDS
        ACTIVE_ISLANDS = islands

    _current_run_id = None
    graph = get_graph()
    thread_id = f"pixiu_evolve_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _graph_config = {"configurable": {"thread_id": thread_id}}
    run_id = _ensure_run_record(mode="evolve")
    _current_run_id = run_id

    logger.info("\n%s", "=" * 60)
    logger.info("🚀 Pixiu v2 启动（进化模式，最大 %d 轮）", rounds)
    logger.info("   Active Islands: %s", ", ".join(ACTIVE_ISLANDS))
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0)
    _update_run_record(NODE_MARKET_CONTEXT, status="running", current_round=0)
    await graph.ainvoke(initial_state.model_dump(), config=_graph_config)


async def run_single(island: str):
    """单次模式：指定 Island，单轮调试。"""
    global _graph_config, _current_run_id

    _current_run_id = None
    graph = get_graph()
    thread_id = f"pixiu_single_{island}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _graph_config = {"configurable": {"thread_id": thread_id}}
    run_id = _ensure_run_record(mode="single")
    _current_run_id = run_id

    logger.info("\n%s", "=" * 60)
    logger.info("🔍 Pixiu v2 启动（单次模式，Island=%s）", island)
    logger.info("%s\n", "=" * 60)

    initial_state = AgentState(current_round=0, current_island=island)
    _update_run_record(NODE_MARKET_CONTEXT, status="running", current_round=0)
    await graph.ainvoke(initial_state.model_dump(), config=_graph_config)


# ─────────────────────────────────────────────────────────
# CLI 入口（向后兼容）
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pixiu v2 Orchestrator")
    parser.add_argument("--mode", choices=["single", "evolve"], default="evolve")
    parser.add_argument("--island", default="momentum")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--islands", default=None, help="逗号分隔的 Island 列表")
    args = parser.parse_args()

    if args.mode == "single":
        asyncio.run(run_single(island=args.island))
    else:
        island_list = args.islands.split(",") if args.islands else None
        asyncio.run(run_evolve(rounds=args.rounds, islands=island_list))
