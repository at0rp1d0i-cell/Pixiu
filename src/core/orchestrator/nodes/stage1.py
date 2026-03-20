"""Stage 1: Market Context node."""
import asyncio
import logging

from src.schemas.state import AgentState
from src.schemas.market_context import MarketContextMemo
from src.schemas.stage_io import MarketContextOutput

logger = logging.getLogger(__name__)


def market_context_node(state: AgentState) -> MarketContextOutput:
    """Stage 1: MarketAnalyst + LiteratureMiner，生成 MarketContextMemo。"""
    from src.agents.market_analyst import market_context_node as _market_node
    from .. import config as _config
    from src.factor_pool.pool import get_factor_pool

    logger.info("[Stage 1] 生成市场上下文... (Round %d)", state.current_round)

    try:
        result = _market_node(dict(state))
        memo: MarketContextMemo = result.get("market_context")

        try:
            from src.agents.literature_miner import LiteratureMiner
            pool = get_factor_pool()
            miner = LiteratureMiner(factor_pool=pool)
            insights = asyncio.run(miner.retrieve_insights(active_islands=_config.ACTIVE_ISLANDS))
            if memo and not memo.historical_insights:
                memo = memo.model_copy(update={"historical_insights": insights})
        except Exception as e:
            logger.warning("[Stage 1] LiteratureMiner 失败（跳过）: %s", e)

        logger.info("[Stage 1] 市场上下文完成，Regime=%s", getattr(memo, "market_regime", "unknown"))
        return {"market_context": memo}
    except Exception as e:
        logger.error("[Stage 1] 失败: %s", e)
        return {"last_error": str(e), "error_stage": "market_context"}
