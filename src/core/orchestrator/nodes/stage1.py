"""Stage 1: Market Context node."""
import asyncio
import logging
from time import perf_counter

from src.schemas.state import AgentState
from src.schemas.market_context import MarketContextMemo
from src.schemas.stage_io import MarketContextOutput
from src.core.orchestrator.timing import merge_stage_timing

logger = logging.getLogger(__name__)


def market_context_node(state: AgentState) -> MarketContextOutput:
    """Stage 1: MarketAnalyst + LiteratureMiner，生成 MarketContextMemo。"""
    from src.agents.market_analyst import market_context_node as _market_node
    from .. import config as _config
    from src.factor_pool.pool import get_factor_pool

    logger.info("[Stage 1] 生成市场上下文... (Round %d)", state.current_round)
    stage_started = perf_counter()
    market_analyst_ms = 0.0
    literature_miner_ms = 0.0

    try:
        market_started = perf_counter()
        result = _market_node(dict(state))
        market_analyst_ms = round((perf_counter() - market_started) * 1000.0, 2)
        memo: MarketContextMemo = result.get("market_context")

        try:
            from src.agents.literature_miner import LiteratureMiner
            pool = get_factor_pool()
            miner = LiteratureMiner(factor_pool=pool)
            literature_started = perf_counter()
            insights = asyncio.run(miner.retrieve_insights(active_islands=_config.ACTIVE_ISLANDS))
            literature_miner_ms = round((perf_counter() - literature_started) * 1000.0, 2)
            if memo and not memo.historical_insights:
                memo = memo.model_copy(update={"historical_insights": insights})
        except Exception as e:
            logger.warning("[Stage 1] LiteratureMiner 失败（跳过）: %s", e)

        stage_elapsed_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        timing_update = merge_stage_timing(
            state,
            "market_context",
            stage_elapsed_ms,
            step_timings={
                "market_analyst_ms": market_analyst_ms,
                "literature_miner_ms": literature_miner_ms,
            },
        )
        logger.info(
            "[Stage 1] 市场上下文完成，Regime=%s，耗时 %.2f ms (analyst %.2f ms, literature %.2f ms)",
            getattr(memo, "market_regime", "unknown"),
            stage_elapsed_ms,
            market_analyst_ms,
            literature_miner_ms,
        )
        return {"market_context": memo, **timing_update}
    except Exception as e:
        stage_elapsed_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        timing_update = merge_stage_timing(
            state,
            "market_context",
            stage_elapsed_ms,
            step_timings={
                "market_analyst_ms": market_analyst_ms,
                "literature_miner_ms": literature_miner_ms,
            },
        )
        logger.error("[Stage 1] 失败: %s (%.2f ms)", e, stage_elapsed_ms)
        return {
            "last_error": str(e),
            "error_stage": "market_context",
            **timing_update,
        }
