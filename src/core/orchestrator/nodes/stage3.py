"""Stage 3: Prefilter node."""
import logging
from time import perf_counter

from src.schemas.state import AgentState
from src.schemas.stage_io import PrefilterOutput
from src.core.orchestrator.timing import merge_stage_timing

logger = logging.getLogger(__name__)


def prefilter_node(state: AgentState) -> PrefilterOutput:
    """Stage 3: Validator + NoveltyFilter + AlignmentChecker，最多放行 Top K。"""
    from src.agents.prefilter import prefilter_node as _prefilter

    logger.info("[Stage 3] 过滤 %d 个候选...", len(state.research_notes))
    started = perf_counter()
    result = _prefilter(dict(state))
    approved = result.get("approved_notes", [])
    filtered = len(state.research_notes) - len(approved)
    diagnostics = result.get("prefilter_diagnostics", {})
    elapsed_ms = round((perf_counter() - started) * 1000.0, 2)
    logger.info(
        "[Stage 3] 放行 %d 个，淘汰 %d 个（基准：Synthesis 后 %d 个），耗时 %.2f ms",
        len(approved), filtered, len(state.research_notes), elapsed_ms,
    )
    return {
        "approved_notes": approved,
        "filtered_count": filtered,
        "prefilter_diagnostics": diagnostics,
        **merge_stage_timing(state, "prefilter", elapsed_ms),
    }
