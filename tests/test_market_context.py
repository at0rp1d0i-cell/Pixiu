"""
Stage 1 Market Context TDD Tests
按照 `docs/design/stage-1-market-context.md` 的测试要求编写。
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from src.schemas.market_context import MarketContextMemo, HistoricalInsight
from src.agents.literature_miner import LiteratureMiner


# ─────────────────────────────────────────────────────────
# MarketAnalyst Tests
# ─────────────────────────────────────────────────────────

def test_market_analyst_empty_fallback():
    """MCP 工具全部失败时应返回合法的空 MarketContextMemo"""
    from src.agents.market_analyst import MarketAnalyst

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '{"invalid": "json_no_schema_match"}'  # 无效 JSON → 降级

    with patch('src.agents.market_analyst.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            analyst = MarketAnalyst(mcp_tools=[])
            memo = asyncio.run(analyst.analyze())

    assert isinstance(memo, MarketContextMemo)
    assert memo.market_regime == "range_bound"  # 无效 JSON → 降级到 RANGE_BOUND
    assert "失败" in memo.raw_summary


def test_market_analyst_valid_json_parsing():
    """MarketAnalyst 应能正确解析 LLM 输出的合法 JSON"""
    from src.agents.market_analyst import MarketAnalyst

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '''{
        "date": "2026-03-08",
        "northbound": {"net_buy_bn": 12.5, "top_sectors": ["科技"], "top_stocks": ["600519"], "sentiment": "bullish"},
        "macro_signals": [],
        "hot_themes": ["AI算力"],
        "historical_insights": [],
        "suggested_islands": ["momentum"],
        "market_regime": "trending_up",
        "raw_summary": "今日北向净流入12.5亿"
    }'''

    with patch('src.agents.market_analyst.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            analyst = MarketAnalyst(mcp_tools=[])
            memo = asyncio.run(analyst.analyze())

    assert memo.market_regime == "bull_trend"  # legacy "trending_up" → MarketRegime.BULL_TREND
    assert "momentum" in memo.suggested_islands
    assert memo.northbound is not None
    assert memo.northbound.net_buy_bn == 12.5


# ─────────────────────────────────────────────────────────
# LiteratureMiner Tests
# ─────────────────────────────────────────────────────────

def test_literature_miner_empty_pool():
    """FactorPool 为空时应返回提示性 HistoricalInsight，不报错"""
    mock_pool = MagicMock()
    mock_pool.get_island_best_factors.return_value = []
    mock_pool.get_common_failure_modes.return_value = []

    miner = LiteratureMiner(factor_pool=mock_pool)
    insights = asyncio.run(miner.retrieve_insights(["momentum", "volatility"]))

    assert len(insights) == 2
    assert all(isinstance(i, HistoricalInsight) for i in insights)
    assert all(i.best_factor_formula == "（无历史记录）" for i in insights)
    assert all(len(i.suggested_directions) > 0 for i in insights)


def test_literature_miner_with_data():
    """FactorPool 有数据时应返回正确的 HistoricalInsight"""
    mock_pool = MagicMock()
    mock_pool.get_island_best_factors.return_value = [
        {"formula": "Mean($close, 5) / Mean($close, 20) - 1", "sharpe": 2.9}
    ]
    mock_pool.get_common_failure_modes.return_value = []

    miner = LiteratureMiner(factor_pool=mock_pool)
    insights = asyncio.run(miner.retrieve_insights(["momentum"]))

    assert len(insights) == 1
    assert "Mean" in insights[0].best_factor_formula
    assert insights[0].best_sharpe == 2.9


def test_literature_miner_direction_inference():
    """high_turnover 失败模式应推断出增大时间窗口的建议"""
    mock_pool = MagicMock()
    mock_pool.get_island_best_factors.return_value = [
        {"formula": "Ref($close, 1) / $close - 1", "sharpe": 1.5}
    ]
    mock_pool.get_common_failure_modes.return_value = [
        {"failure_mode": "high_turnover", "count": 5}
    ]

    miner = LiteratureMiner(factor_pool=mock_pool)
    insights = asyncio.run(miner.retrieve_insights(["momentum"]))

    assert any("时间窗口" in d for d in insights[0].suggested_directions)


def test_literature_miner_low_ic_direction():
    """low_ic 失败模式应推断出换信号类型的建议"""
    mock_pool = MagicMock()
    mock_pool.get_island_best_factors.return_value = [
        {"formula": "Delta($close, 5)", "sharpe": 1.2}
    ]
    mock_pool.get_common_failure_modes.return_value = [
        {"failure_mode": "low_ic", "count": 3}
    ]

    miner = LiteratureMiner(factor_pool=mock_pool)
    insights = asyncio.run(miner.retrieve_insights(["momentum"]))

    assert any("信号" in d for d in insights[0].suggested_directions)


def test_literature_miner_pool_error_graceful():
    """FactorPool 查询异常时不崩溃，返回空洞察"""
    mock_pool = MagicMock()
    mock_pool.get_island_best_factors.side_effect = Exception("DB连接失败")
    mock_pool.get_common_failure_modes.side_effect = Exception("DB连接失败")

    miner = LiteratureMiner(factor_pool=mock_pool)
    insights = asyncio.run(miner.retrieve_insights(["momentum"]))

    assert len(insights) == 1
    assert insights[0].best_factor_formula == "（无历史记录）"
