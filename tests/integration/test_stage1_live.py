"""
Stage 1 真实场景测试：使用真实 DeepSeek API + AKShare MCP Server
运行前需要设置 .env：RESEARCHER_API_KEY, RESEARCHER_BASE_URL, RESEARCHER_MODEL

运行方式：
    uv run pytest -q tests/integration/test_stage1_live.py -v -s
"""
import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.llm.openai_compat import load_dotenv_if_available
load_dotenv_if_available()

# 没有 API key 就跳过整个模块
pytestmark = pytest.mark.skipif(
    not os.getenv("RESEARCHER_API_KEY"),
    reason="RESEARCHER_API_KEY 未设置，跳过真实场景测试",
)


from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agents.market_analyst import MarketAnalyst, MCP_SERVER_PATH, market_context_node
from src.schemas.market_context import MarketContextMemo
from src.schemas.state import AgentState

# Proxy 变量名（socks proxy 会导致 ChatOpenAI httpx 初始化失败）
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def _extract_text(result) -> str:
    """从 MCP 工具返回值中提取 JSON 文本。

    langchain-mcp-adapters content_and_artifact 模式返回 list[dict]，
    每个 dict 含 type='text' + text='...'。直接字符串则原样返回。
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list) and result:
        return result[0].get("text", str(result[0]))
    return str(result)


@pytest.fixture(scope="module")
def mcp_tools():
    client = MultiServerMCPClient(
        {"akshare": {"command": "python3", "args": [MCP_SERVER_PATH], "transport": "stdio"}}
    )
    return asyncio.run(client.get_tools())


@pytest.fixture(autouse=True)
def _clear_proxy(monkeypatch):
    """临时清除 socks proxy 环境变量，避免 ChatOpenAI/httpx 初始化失败。"""
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)


# ─────────────────────────────────────────────────────────
# Test 1: AKShare MCP 工具能真实调用
# ─────────────────────────────────────────────────────────

def test_akshare_macro_indicators_live(mcp_tools):
    """直接调用 get_macro_indicators 工具，验证能拿到真实数据。"""
    tool = next((t for t in mcp_tools if t.name == "get_macro_indicators"), None)
    assert tool is not None, "get_macro_indicators 工具不存在"

    raw = asyncio.run(tool.ainvoke({}))
    text = _extract_text(raw)
    print(f"\n[宏观指标] {text[:300]}")

    data = json.loads(text)
    assert "error" not in data or len(data) > 1, f"工具返回错误: {data}"
    assert any(k in data for k in ("pmi_manufacturing", "m2_yoy", "cpi_yoy"))


def test_akshare_northbound_flow_live(mcp_tools):
    """调用 get_northbound_flow_today，验证北向资金数据可获取。"""
    tool = next((t for t in mcp_tools if t.name == "get_northbound_flow_today"), None)
    assert tool is not None

    raw = asyncio.run(tool.ainvoke({}))
    text = _extract_text(raw)
    print(f"\n[北向资金] {text[:300]}")

    data = json.loads(text)
    # 允许返回空列表（非交易日），但不能是错误
    if isinstance(data, dict):
        assert "error" not in data, f"工具返回错误: {data}"


# ─────────────────────────────────────────────────────────
# Test 2: MarketAnalyst 真实 LLM + 真实 MCP 工具
# ─────────────────────────────────────────────────────────

def test_market_analyst_live(mcp_tools):
    """使用真实 DeepSeek API + 真实 MCP 工具，生成 MarketContextMemo。"""
    analyst = MarketAnalyst(mcp_tools=mcp_tools)
    memo = asyncio.run(analyst.analyze())

    print(f"\n[MarketContextMemo]")
    print(f"  date:          {memo.date}")
    print(f"  market_regime: {memo.market_regime}")
    print(f"  hot_themes:    {memo.hot_themes}")
    print(f"  suggested_islands: {memo.suggested_islands}")
    print(f"  raw_summary:   {memo.raw_summary[:200]}")
    if memo.northbound:
        print(f"  northbound:    net_buy={memo.northbound.net_buy_bn}亿, sentiment={memo.northbound.sentiment}")
    if memo.macro_signals:
        print(f"  macro_signals: {[s.source for s in memo.macro_signals]}")

    assert isinstance(memo, MarketContextMemo)
    assert memo.date, "date 不能为空"
    assert memo.market_regime in ("bull_trend", "bear_trend", "high_volatility", "range_bound", "structural_break")
    assert isinstance(memo.suggested_islands, list)
    assert len(memo.suggested_islands) > 0
    assert memo.raw_summary, "raw_summary 不能为空"


# ─────────────────────────────────────────────────────────
# Test 3: market_context_node 完整节点（含 LiteratureMiner）
# ─────────────────────────────────────────────────────────

def test_market_context_node_live():
    """跑完整的 market_context_node，验证 MarketAnalyst + LiteratureMiner 合并输出。"""
    state = AgentState(current_round=1)
    result = market_context_node(dict(state))

    memo = result.get("market_context")
    assert memo is not None, "market_context 不能为 None"
    assert isinstance(memo, MarketContextMemo)

    print(f"\n[market_context_node 输出]")
    print(f"  regime:   {memo.market_regime}")
    print(f"  insights: {len(memo.historical_insights)} 条历史洞察")
    for ins in memo.historical_insights:
        print(f"    [{ins.island}] best_sharpe={ins.best_sharpe}, directions={ins.suggested_directions}")

    # 验证 LiteratureMiner 已合并（historical_insights 是列表，即使为空也合法）
    assert isinstance(memo.historical_insights, list)
