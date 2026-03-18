"""Stage 3: Prefilter node."""
import logging

from src.schemas.state import AgentState

logger = logging.getLogger(__name__)


def prefilter_node(state: AgentState) -> dict:
    """Stage 3: Validator + NoveltyFilter + AlignmentChecker，最多放行 Top K。"""
    from src.agents.prefilter import prefilter_node as _prefilter

    logger.info("[Stage 3] 过滤 %d 个候选...", len(state.research_notes))
    result = _prefilter(dict(state))
    approved = result.get("approved_notes", [])
    filtered = len(state.research_notes) - len(approved)
    logger.info(
        "[Stage 3] 放行 %d 个，淘汰 %d 个（基准：Synthesis 后 %d 个）",
        len(approved), filtered, len(state.research_notes),
    )
    return {"approved_notes": approved, "filtered_count": filtered}
