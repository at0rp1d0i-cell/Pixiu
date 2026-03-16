"""
Stage 1 集成测试：验证 MCP Server 连接、LiteratureMiner 真实 FactorPool 交互、
orchestrator 节点降级路径、以及 Stage 1→2 数据流衔接。
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agents.literature_miner import LiteratureMiner
from src.agents.market_analyst import (
    MarketAnalyst,
    MCP_SERVER_PATH,
    _empty_memo,
    market_context_node,
)
from src.agents.schemas import BacktestMetrics, FactorHypothesis
from src.factor_pool.pool import FactorPool
from src.schemas.market_context import HistoricalInsight, MarketContextMemo
from src.schemas.state import AgentState


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mcp_client():
    """启动 AKShare MCP Server（stdio transport）。"""
    return MultiServerMCPClient(
        {"akshare": {"command": "python3", "args": [MCP_SERVER_PATH], "transport": "stdio"}}
    )


@pytest.fixture(scope="module")
def mcp_tools(mcp_client):
    return asyncio.run(mcp_client.get_tools())


@pytest.fixture()
def real_pool(tmp_path):
    """用 tmp_path 创建真实 FactorPool（降级为 in-memory ChromaDB）。"""
    return FactorPool(db_path=str(tmp_path / "test_pool"))
def _seed_pool(pool: FactorPool):
    """向 FactorPool 写入测试因子记录。"""
    factors = [
        ("momentum", "mom_5d", "Mean($close,5)/Ref(Mean($close,5),5)-1", 3.5),
        ("momentum", "mom_fail", "Ref($close,1)/$close-1", 0.5),
    ]
    for island, name, formula, sharpe in factors:
        hyp = FactorHypothesis(
            name=name,
            formula=formula,
            hypothesis=f"测试因子 {name}",
            rationale="测试用",
            expected_direction="positive",
        )
        metrics = BacktestMetrics(
            sharpe=sharpe,
            ic=0.03,
            icir=0.5,
            turnover=10.0,
            annualized_return=15.0,
            max_drawdown=-8.0,
            parse_success=True,
        )
        pool.register(hypothesis=hyp, metrics=metrics, island_name=island)

    # 写入一条带 failure_mode 的记录（v2 格式需要 passed=False）
    pool._collection.upsert(
        ids=["momentum_high_turnover_fail"],
        documents=["公式: Rank($volume)"],
        metadatas=[{
            "island": "momentum",
            "formula": "Rank($volume)",
            "sharpe": 0.2,
            "passed": False,
            "failure_mode": "high_turnover",
            "beats_baseline": False,
            "parse_success": True,
        }],
    )


def _make_memo() -> MarketContextMemo:
    """构造完整的 MarketContextMemo 用于数据流测试。"""
    return MarketContextMemo(
        date="2026-03-16",
        northbound=None,
        macro_signals=[],
        hot_themes=["AI算力"],
        historical_insights=[],
        suggested_islands=["momentum", "northbound"],
        market_regime="trending_up",
        raw_summary="测试用市场摘要",
    )


# ─────────────────────────────────────────────────────────
# Test 1: MCP Server 工具发现
# ─────────────────────────────────────────────────────────

def test_market_analyst_mcp_tools_available(mcp_tools):
    """启动 AKShare MCP Server，验证能获取到 10 个工具。"""
    tool_names = [t.name for t in mcp_tools]
    assert len(mcp_tools) == 10, f"Expected 10 tools, got {len(mcp_tools)}: {tool_names}"

    expected = [
        "get_northbound_flow_today",
        "get_northbound_flow_history",
        "get_market_fund_flow",
        "get_northbound_top_holdings",
        "get_research_reports",
        "get_industry_pe",
        "get_individual_fund_flow_rank",
        "get_stock_financial_summary",
        "get_macro_indicators",
        "get_margin_trading_summary",
    ]
    for name in expected:
        assert name in tool_names, f"Missing tool: {name}"


# ─────────────────────────────────────────────────────────
# Test 2: LiteratureMiner + 真实 FactorPool
# ─────────────────────────────────────────────────────────

def test_literature_miner_with_real_pool(real_pool):
    """用真实 FactorPool（in-memory ChromaDB）验证 LiteratureMiner 检索。"""
    _seed_pool(real_pool)

    miner = LiteratureMiner(factor_pool=real_pool)
    insights = asyncio.run(miner.retrieve_insights(active_islands=["momentum", "valuation"]))

    assert len(insights) == 2

    # momentum island 有数据 → 应返回真实 best_factor
    mom = next(i for i in insights if i.island == "momentum")
    assert mom.best_sharpe == 3.5
    assert "Mean($close,5)" in mom.best_factor_formula
    # high_turnover 失败模式应触发方向建议
    assert any("high_turnover" in m for m in mom.common_failure_modes)
    assert len(mom.suggested_directions) > 0

    # valuation island 无数据 → 应返回引导性提示
    val = next(i for i in insights if i.island == "valuation")
    assert val.best_sharpe == 0.0
    assert "无历史记录" in val.best_factor_formula


# ─────────────────────────────────────────────────────────
# Test 3: market_context_node 降级路径
# ─────────────────────────────────────────────────────────

def test_market_context_node_fallback():
    """Mock 掉 MCP 连接使其失败，验证降级返回合法 MarketContextMemo。"""
    state = AgentState(current_round=1, current_island="momentum")

    with patch(
        "langchain_mcp_adapters.client.MultiServerMCPClient",
    ) as MockClient:
        # 让 get_tools() 抛异常，触发降级
        mock_instance = MagicMock()
        mock_instance.get_tools = AsyncMock(side_effect=ConnectionError("MCP server down"))
        MockClient.return_value = mock_instance

        result = market_context_node(dict(state))

    memo = result.get("market_context")
    assert memo is not None
    assert isinstance(memo, MarketContextMemo)
    assert memo.market_regime == "unknown"
    assert memo.date  # 非空日期
    assert "失败" in memo.raw_summary or "MCP server down" in memo.raw_summary


# ─────────────────────────────────────────────────────────
# Test 4: MarketAnalyst + Mock LLM + 真实 MCP 工具列表
# ─────────────────────────────────────────────────────────

def test_market_context_node_with_mock_llm(mcp_tools):
    """Mock LLM 返回合法 JSON，真实 MCP 工具列表，验证解析。"""
    memo_json = json.dumps({
        "date": "2026-03-16",
        "northbound": {
            "net_buy_bn": 25.3,
            "top_sectors": ["科技", "消费"],
            "top_stocks": ["600519"],
            "sentiment": "bullish",
        },
        "macro_signals": [
            {"signal": "PMI 回升", "source": "pmi", "direction": "positive", "confidence": 0.8}
        ],
        "hot_themes": ["AI算力", "新能源"],
        "historical_insights": [],
        "suggested_islands": ["momentum", "northbound"],
        "market_regime": "trending_up",
        "raw_summary": "北向资金大幅流入，市场偏多。",
    }, ensure_ascii=False)

    # 构造一个不带 tool_calls 的 LLM 响应（直接输出 JSON，跳过 ReAct 循环）
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = memo_json

    # Mock ChatOpenAI 构造，避免需要真实 API key
    mock_llm = AsyncMock(return_value=mock_response)
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    with patch("src.agents.market_analyst.ChatOpenAI", return_value=mock_llm):
        analyst = MarketAnalyst(mcp_tools=mcp_tools)

    memo = asyncio.run(analyst.analyze())

    assert isinstance(memo, MarketContextMemo)
    assert memo.market_regime == "trending_up"
    assert memo.date == "2026-03-16"
    assert memo.northbound is not None
    assert memo.northbound.net_buy_bn == 25.3
    assert len(memo.macro_signals) == 1
    assert memo.macro_signals[0].source == "pmi"
    assert "AI算力" in memo.hot_themes
    assert len(memo.suggested_islands) == 2


# ─────────────────────────────────────────────────────────
# Test 5: Stage 1 输出 → Stage 2 输入衔接
# ─────────────────────────────────────────────────────────

def test_stage1_output_feeds_stage2_input():
    """验证 Stage 1 的 MarketContextMemo 能被 Stage 2 节点正确读取。"""
    memo = _make_memo()
    state = AgentState(current_round=1, market_context=memo)

    # Stage 2 的 hypothesis_gen_node 读取 state.market_context
    assert state.market_context is not None
    assert state.market_context.market_regime == "trending_up"
    assert "momentum" in state.market_context.suggested_islands

    # 验证序列化往返（LangGraph 节点间通过 dict 传递）
    state_dict = dict(state)
    assert state_dict["market_context"] is memo

    # 重建 AgentState 验证反序列化
    restored = AgentState(**state_dict)
    assert restored.market_context.market_regime == "trending_up"
    assert restored.market_context.hot_themes == ["AI算力"]
    # Stage 2 字段初始为空
    assert restored.research_notes == []
