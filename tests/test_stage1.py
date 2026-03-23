"""
Stage 1 merged tests: market_context + regime_detector.

Sources:
  - tests/test_market_context.py
  - tests/test_regime_detector.py
"""
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import math
from datetime import date

import pytest

from src.schemas.market_context import MarketContextMemo, HistoricalInsight, MarketRegime
from src.agents.literature_miner import LiteratureMiner
from src.market.regime_detector import RegimeDetector, RegimeSignals
from src.schemas.state import AgentState

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────
# From test_market_context.py — MarketAnalyst Tests
# ─────────────────────────────────────────────────────────

def test_market_analyst_empty_fallback():
    """MCP 工具全部失败时应返回合法的空 MarketContextMemo"""
    from src.agents.market_analyst import MarketAnalyst

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '{"invalid": "json_no_schema_match"}'

    with patch('src.agents.market_analyst.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            analyst = MarketAnalyst(mcp_tools=[])
            memo = asyncio.run(analyst.analyze())

    assert isinstance(memo, MarketContextMemo)
    assert memo.market_regime == "range_bound"
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

    with patch('src.agents.market_analyst.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            analyst = MarketAnalyst(mcp_tools=[])
            memo = asyncio.run(analyst.analyze())

    assert memo.market_regime == "bull_trend"
    assert "momentum" in memo.suggested_islands
    assert memo.northbound is not None
    assert memo.northbound.net_buy_bn == 12.5


def test_market_analyst_falls_back_to_openai_env():
    """当 RESEARCHER_* 未设置时，Stage 1 应回退到 OPENAI_* 配置。"""
    from src.agents.market_analyst import MarketAnalyst

    with patch('src.agents.market_analyst.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_builder.return_value = mock_chat
        MarketAnalyst(mcp_tools=[])

    mock_builder.assert_called_once_with(profile="market_analyst")


def test_market_analyst_loads_dotenv_before_llm_init():
    """Stage 1 应通过共享 helper 初始化 LLM。"""
    from src.agents.market_analyst import MarketAnalyst

    with patch('src.agents.market_analyst.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {}, clear=True):
            MarketAnalyst(mcp_tools=[])

    mock_builder.assert_called_once()


def test_market_analyst_injects_context_skill_into_system_prompt():
    from src.agents.market_analyst import MarketAnalyst

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.append(messages)
        response = MagicMock()
        response.tool_calls = []
        response.content = """{
            "date": "2026-03-19",
            "northbound": null,
            "macro_signals": [],
            "hot_themes": [],
            "historical_insights": [],
            "suggested_islands": ["momentum"],
            "market_regime": "range_bound",
            "raw_summary": "测试"
        }"""
        return response

    with patch('src.agents.market_analyst.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            analyst = MarketAnalyst(mcp_tools=[])
            asyncio.run(analyst.analyze())

    assert captured_messages
    system_message = captured_messages[0][0]
    assert "<!-- SKILL:MARKET_ANALYST_CONTEXT_FRAMING -->" in system_message.content


def test_market_context_node_timeout_falls_back_to_empty_memo():
    from src.agents.market_analyst import market_context_node

    async def _hang(_state):
        await asyncio.sleep(0.05)
        return {"market_context": _make_market_memo()}

    with patch.dict("os.environ", {"PIXIU_STAGE1_TIMEOUT_SEC": "0.01"}):
        with patch("src.agents.market_analyst._run_market_context_once", side_effect=_hang):
            result = market_context_node({"active_islands": ["momentum"]})

    memo = result["market_context"]
    assert isinstance(memo, MarketContextMemo)
    assert memo.market_regime == MarketRegime.RANGE_BOUND
    assert "timeout" in memo.raw_summary.lower()


def test_market_context_node_converts_blocking_tool_error_to_degraded_memo():
    from src.agents.market_analyst import market_context_node

    with patch(
        "src.agents.market_analyst._run_market_context_once",
        side_effect=RuntimeError("No Stage 1 blocking tools available"),
    ):
        result = market_context_node({"active_islands": ["momentum"]})

    memo = result["market_context"]
    assert isinstance(memo, MarketContextMemo)
    assert "No Stage 1 blocking tools available" in memo.raw_summary


def test_run_market_context_once_uses_akshare_only_by_default():
    from src.agents.market_analyst import _run_market_context_once

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[])

    with patch.dict("os.environ", {}, clear=True):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient", return_value=mock_client) as mock_ctor:
            with pytest.raises(RuntimeError, match="No Stage 1 blocking tools available"):
                asyncio.run(_run_market_context_once({}))

    servers = mock_ctor.call_args.args[0]
    assert "akshare" in servers
    assert "rss" not in servers
    assert "tushare" not in servers


def test_run_market_context_once_includes_rss_when_opted_in():
    from src.agents.market_analyst import _run_market_context_once

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[])

    with patch.dict("os.environ", {"PIXIU_STAGE1_ENABLE_RSS": "1"}, clear=True):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient", return_value=mock_client) as mock_ctor:
            with pytest.raises(RuntimeError, match="No Stage 1 blocking tools available"):
                asyncio.run(_run_market_context_once({}))

    servers = mock_ctor.call_args.args[0]
    assert "akshare" in servers
    assert "rss" in servers


def test_run_market_context_once_includes_tushare_when_token_present():
    from src.agents.market_analyst import _run_market_context_once

    tool = MagicMock()
    tool.name = "get_moneyflow_hsgt"
    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[tool])

    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test-token"}, clear=True):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient", return_value=mock_client) as mock_ctor:
            with patch("src.agents.market_analyst.build_researcher_llm") as mock_builder:
                mock_chat = MagicMock()
                mock_chat.bind_tools = MagicMock(return_value=mock_chat)
                mock_builder.return_value = mock_chat
                with patch("src.agents.market_analyst.MarketAnalyst.analyze", new=AsyncMock(return_value=_make_market_memo())):
                    result = asyncio.run(_run_market_context_once({}))

    servers = mock_ctor.call_args.args[0]
    assert "tushare" in servers
    assert isinstance(result["market_context"], MarketContextMemo)


def test_stage1_node_reuses_same_day_market_context_after_round_zero():
    from src.core.orchestrator.nodes.stage1 import market_context_node

    cached_memo = _make_market_memo()
    state = AgentState(current_round=1, market_context=cached_memo)

    with patch("src.agents.market_analyst.market_context_node") as mock_market_node:
        result = market_context_node(state)

    assert result["market_context"] == cached_memo
    assert result["stage_timings"]["market_context"] >= 0
    assert result["stage_step_timings"]["market_context"]["cache_hit_ms"] >= 0
    mock_market_node.assert_not_called()


def test_stage1_node_does_not_reuse_degraded_same_day_market_context():
    from src.core.orchestrator.nodes.stage1 import market_context_node

    degraded = _make_market_memo().model_copy(
        update={"raw_summary": "市场数据获取失败：Stage 1 timeout after 60.0s"}
    )
    state = AgentState(current_round=1, market_context=degraded)

    with patch(
        "src.agents.market_analyst.market_context_node",
        return_value={"market_context": _make_market_memo()},
    ) as mock_market_node:
        with patch("src.factor_pool.pool.get_factor_pool", return_value=MagicMock()):
            with patch(
                "src.agents.literature_miner.LiteratureMiner.retrieve_insights",
                new=AsyncMock(return_value=[]),
            ):
                market_context_node(state)

    mock_market_node.assert_called_once()


def test_stage1_node_raises_in_strict_mode_when_blocking_core_is_degraded():
    from src.core.orchestrator.nodes.stage1 import market_context_node

    degraded = _make_market_memo().model_copy(
        update={"raw_summary": "市场数据获取失败：Stage 1 timeout after 60.0s"}
    )
    state = AgentState(current_round=0)

    with patch("src.core.orchestrator.config.MAX_ROUNDS", 2):
        with patch(
            "src.agents.market_analyst.market_context_node",
            return_value={"market_context": degraded},
        ):
            with pytest.raises(RuntimeError, match="blocking core degraded"):
                market_context_node(state)


def test_stage1_node_raises_in_strict_mode_when_market_analyst_raises():
    from src.core.orchestrator.nodes.stage1 import market_context_node

    state = AgentState(current_round=0)

    with patch("src.core.orchestrator.config.MAX_ROUNDS", 2):
        with patch(
            "src.agents.market_analyst.market_context_node",
            side_effect=RuntimeError("No Stage 1 blocking tools available"),
        ):
            with pytest.raises(RuntimeError, match="No Stage 1 blocking tools available"):
                market_context_node(state)


def test_stage1_node_queries_literature_for_suggested_islands_only():
    from src.core.orchestrator.nodes.stage1 import market_context_node

    memo = _make_market_memo().model_copy(update={"suggested_islands": ["momentum"]})
    state = AgentState(current_round=0)

    with patch("src.agents.market_analyst.market_context_node", return_value={"market_context": memo}):
        with patch("src.factor_pool.pool.get_factor_pool", return_value=MagicMock()):
            with patch("src.agents.literature_miner.LiteratureMiner.retrieve_insights", new=AsyncMock(return_value=[])) as mock_retrieve:
                result = market_context_node(state)

    assert result["market_context"].suggested_islands == ["momentum"]
    mock_retrieve.assert_awaited_once_with(active_islands=["momentum"])


def test_select_stage1_tools_uses_allowlists():
    from src.agents.market_analyst import _select_stage1_tools

    def _tool(name: str):
        tool = MagicMock()
        tool.name = name
        return tool

    tools = [
        _tool("get_moneyflow_hsgt"),
        _tool("get_margin_data"),
        _tool("get_news"),
        _tool("get_market_hot_topics"),
        _tool("unknown_tool"),
    ]

    selected = _select_stage1_tools(tools)

    assert [tool.name for tool in selected["blocking"]] == [
        "get_moneyflow_hsgt",
        "get_margin_data",
    ]
    assert [tool.name for tool in selected["enrichment"]] == [
        "get_news",
        "get_market_hot_topics",
    ]


# ─────────────────────────────────────────────────────────
# From test_market_context.py — LiteratureMiner Tests
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


# ─────────────────────────────────────────────────────────
# From test_regime_detector.py — helpers
# ─────────────────────────────────────────────────────────

def _make_detector() -> RegimeDetector:
    return RegimeDetector()


def _make_market_memo() -> MarketContextMemo:
    return MarketContextMemo(
        date=date.today().strftime("%Y-%m-%d"),
        northbound=None,
        macro_signals=[],
        hot_themes=["AI算力"],
        historical_insights=[],
        suggested_islands=["momentum"],
        market_regime=MarketRegime.BULL_TREND,
        raw_summary="测试 market context",
    )


def _make_rising_closes(n: int = 60, start: float = 3000.0, slope: float = 10.0) -> list[float]:
    return [start + i * slope for i in range(n)]


def _make_falling_closes(n: int = 60, start: float = 3600.0, slope: float = 10.0) -> list[float]:
    return [start - i * slope for i in range(n)]


def _make_flat_closes(n: int = 60, base: float = 3000.0, noise: float = 5.0) -> list[float]:
    return [base + noise * math.sin(i) for i in range(n)]


def _make_volatile_closes(n: int = 60, base: float = 3000.0, amplitude: float = 200.0) -> list[float]:
    return [base + amplitude * math.sin(i * 0.7) for i in range(n)]


# ─────────────────────────────────────────────────────────
# From test_regime_detector.py — detect(market_data) tests
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_detect_structural_break_by_volatility():
    """波动率超过 3% 应触发 STRUCTURAL_BREAK。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 3.5})
    assert result == MarketRegime.STRUCTURAL_BREAK


def test_detect_structural_break_by_max_daily_return():
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.0, "max_daily_return": 6.0})
    assert result == MarketRegime.STRUCTURAL_BREAK


def test_detect_structural_break_max_daily_negative():
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.0, "max_daily_return": -7.5})
    assert result == MarketRegime.STRUCTURAL_BREAK


@pytest.mark.smoke
def test_detect_high_volatility():
    d = _make_detector()
    result = d.detect({"volatility_30d": 2.0})
    assert result == MarketRegime.HIGH_VOLATILITY


@pytest.mark.smoke
def test_detect_bull_trend():
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 4200.0,
        "ma20": 4100.0,
        "ma60": 3900.0,
        "market_return_30d": 15.0,
    })
    assert result == MarketRegime.BULL_TREND


@pytest.mark.smoke
def test_detect_bear_trend():
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 3500.0,
        "ma20": 3700.0,
        "ma60": 3900.0,
        "market_return_30d": -12.0,
    })
    assert result == MarketRegime.BEAR_TREND


@pytest.mark.smoke
def test_detect_range_bound_default():
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.9,
        "ma5": 3800.0,
        "ma20": 3820.0,
        "ma60": 3810.0,
        "market_return_30d": 3.0,
    })
    assert result == MarketRegime.RANGE_BOUND


def test_detect_range_bound_no_data():
    d = _make_detector()
    result = d.detect({})
    assert result == MarketRegime.RANGE_BOUND


def test_detect_bull_trend_requires_alignment():
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 4200.0,
        "ma20": 4100.0,
        "ma60": 3900.0,
        "market_return_30d": 5.0,
    })
    assert result == MarketRegime.RANGE_BOUND


def test_detect_bear_trend_requires_alignment():
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 3500.0,
        "ma20": 3700.0,
        "ma60": 3900.0,
        "market_return_30d": -5.0,
    })
    assert result == MarketRegime.RANGE_BOUND


def test_detect_volatility_exact_structural_break_boundary():
    d = _make_detector()
    result = d.detect({"volatility_30d": 3.0})
    assert result == MarketRegime.HIGH_VOLATILITY


def test_detect_volatility_exact_high_vol_boundary():
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.5})
    assert result == MarketRegime.RANGE_BOUND


def test_detect_partial_data_missing_ma():
    d = _make_detector()
    result = d.detect({"volatility_30d": 0.5, "market_return_30d": 20.0})
    assert result == MarketRegime.RANGE_BOUND


# ─────────────────────────────────────────────────────────
# From test_regime_detector.py — detect_from_signals() tests
# ─────────────────────────────────────────────────────────

def test_detect_from_signals_bull_trend():
    d = _make_detector()
    closes = _make_rising_closes(n=60, start=3000.0, slope=10.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.BULL_TREND


def test_detect_from_signals_bear_trend():
    d = _make_detector()
    closes = _make_falling_closes(n=60, start=3600.0, slope=10.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.BEAR_TREND


def test_detect_from_signals_range_bound():
    d = _make_detector()
    closes = _make_flat_closes(n=60, base=3000.0, noise=5.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.RANGE_BOUND


def test_detect_from_signals_high_volatility():
    d = _make_detector()
    closes = _make_volatile_closes(n=60, base=3000.0, amplitude=200.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result in (MarketRegime.HIGH_VOLATILITY, MarketRegime.STRUCTURAL_BREAK)


def test_detect_from_signals_structural_break():
    d = _make_detector()
    stable = _make_flat_closes(n=55, base=3000.0, noise=3.0)
    volatile_tail = [3000.0, 3200.0, 2800.0, 3300.0, 2700.0]
    closes = stable + volatile_tail
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.STRUCTURAL_BREAK


def test_detect_from_signals_insufficient_data():
    d = _make_detector()
    signals = RegimeSignals(index_close=[3000.0, 3010.0, 3020.0])
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.RANGE_BOUND


# ─────────────────────────────────────────────────────────
# From test_regime_detector.py — RegimeFilter tests
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_regime_filter_rejects_invalid_regime():
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_regime_filter",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend", "high_volatility"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert not passed
    assert "bull_trend" in reason


@pytest.mark.smoke
def test_regime_filter_passes_when_not_in_invalid():
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_regime_pass",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        applicable_regimes=["bull_trend", "range_bound"],
        invalid_regimes=["bear_trend"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert passed


def test_regime_filter_passes_when_no_regime():
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_no_regime",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime=None)
    assert passed


def test_regime_filter_rejects_when_no_regime_scope_declared():
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_empty_invalid",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=[],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert not passed
    assert "至少声明" in reason


def test_regime_filter_rejects_unknown_regime_labels():
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_unknown_regime",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        applicable_regimes=["bull_late"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert not passed
    assert "未知 regime" in reason


def test_prefilter_filter_batch_regime_param():
    """filter_batch 接受 current_regime 参数，invalid_regimes 匹配时过滤掉该 note。"""
    from unittest.mock import MagicMock, AsyncMock, patch
    from src.agents.prefilter import PreFilter
    from src.schemas.research_note import FactorResearchNote

    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []
    mock_pool.query_constraints.return_value = []

    note_rejected = FactorResearchNote(
        note_id="rejected_note",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend"],
    )
    note_passed = FactorResearchNote(
        note_id="passed_note",
        island="momentum",
        iteration=1,
        hypothesis="动量假设2",
        economic_intuition="趋势延续2",
        proposed_formula="Corr($volume, $close, 20)",
        risk_factors=["流动性"],
        market_context_date="2026-03-17",
        applicable_regimes=["bull_trend"],
    )

    mock_response = MagicMock()
    mock_response.content = '{"aligned": true, "reason": "一致"}'

    with patch("src.agents.prefilter.build_researcher_llm") as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            pf = PreFilter(factor_pool=mock_pool)
            approved, filtered = asyncio.run(
                pf.filter_batch([note_rejected, note_passed], current_regime="bull_trend")
            )

    approved_ids = {n.note_id for n in approved}
    assert "rejected_note" not in approved_ids
    assert "passed_note" in approved_ids
