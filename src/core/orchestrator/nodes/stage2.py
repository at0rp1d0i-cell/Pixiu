"""Stage 2: Hypothesis generation, synthesis, and note refinement nodes."""
import asyncio
import logging
import os
from typing import List

from src.schemas.state import AgentState

logger = logging.getLogger(__name__)

ACTIVE_ISLANDS: List[str] = os.getenv(
    "ACTIVE_ISLANDS", "momentum,northbound,valuation,volatility,volume,sentiment"
).split(",")


def hypothesis_gen_node(state: AgentState) -> dict:
    """Stage 2: 并行调用所有 Island 的 AlphaResearcher，展开 Batch。"""
    from src.agents.researcher import hypothesis_gen_node as _gen_node
    from src.core.orchestrator._context import get_scheduler

    logger.info("[Stage 2] 并行生成假设... (Round %d)", state.current_round)

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
        return {
            "research_notes": [], "hypotheses": [], "strategy_specs": [],
            "subspace_generated": {}, "last_error": str(e), "error_stage": "hypothesis_gen",
        }


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


def note_refinement_node(state: AgentState) -> dict:
    """Stage 4a→2: 将 ExplorationResult 反馈给对应 ResearchNote，更新 final_formula。"""
    if not state.exploration_results:
        return {}

    result_map = {r.note_id: r for r in state.exploration_results}

    updated_notes = []
    for note in state.approved_notes:
        if note.note_id in result_map:
            er = result_map[note.note_id]
            refined_formula = er.refined_formula_suggestion or note.proposed_formula
            note = note.model_copy(update={
                "final_formula": refined_formula,
                "status": "ready_for_backtest",
            })
            logger.info("[Stage 4a→2] 精化 %s: %s", note.note_id, refined_formula[:60])
        else:
            note = note.model_copy(update={"final_formula": note.proposed_formula, "status": "ready_for_backtest"})
        updated_notes.append(note)

    return {"approved_notes": updated_notes}
