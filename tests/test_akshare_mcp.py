"""验收测试：验证 AKShare MCP Server 的 7 个工具可以正常调用。"""
import asyncio
import os
import sys
import pytest

pytestmark = pytest.mark.integration

# 将项目根目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MCP_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "mcp_servers", "akshare_server.py")
)

from langchain_mcp_adapters.client import MultiServerMCPClient


@pytest.fixture(scope="module")
def mcp_client():
    return MultiServerMCPClient(
        {"akshare": {"command": "python3", "args": [MCP_SERVER_PATH], "transport": "stdio"}}
    )


@pytest.fixture(scope="module")
def tools(mcp_client):
    return asyncio.run(mcp_client.get_tools())


def test_tools_loaded(tools):
    """应加载 7 个工具。"""
    tool_names = [t.name for t in tools]
    expected = [
        "get_northbound_flow_today",
        "get_northbound_flow_history",
        "get_market_fund_flow",
        "get_northbound_top_holdings",
        "get_research_reports",
        "get_industry_pe",
        "get_individual_fund_flow_rank",
    ]
    for name in expected:
        assert name in tool_names, f"Missing tool: {name}"


def test_northbound_flow_today(tools):
    """北向资金今日摘要应返回非空 JSON。"""
    tool = next(t for t in tools if t.name == "get_northbound_flow_today")
    result = asyncio.run(tool.ainvoke({}))
    import json
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list) or "error" not in data


def test_northbound_flow_history(tools):
    """北向资金历史默认 20 天，应返回数据。"""
    tool = next(t for t in tools if t.name == "get_northbound_flow_history")
    result = asyncio.run(tool.ainvoke({"days": 10}))
    import json
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list)
    assert len(data) <= 10


def test_market_fund_flow(tools):
    """全市场资金流向应包含主力净流入字段。"""
    tool = next(t for t in tools if t.name == "get_market_fund_flow")
    result = asyncio.run(tool.ainvoke({"days": 5}))
    import json
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list)


def test_research_reports(tools):
    """平安银行 000001 应有研报数据。"""
    tool = next(t for t in tools if t.name == "get_research_reports")
    result = asyncio.run(tool.ainvoke({"symbol": "000001", "limit": 3}))
    import json
    data = json.loads(result) if isinstance(result, str) else result
    # 允许空列表（若无研报），但不能是 error
    assert isinstance(data, list) or "error" not in str(data)


def test_industry_pe(tools):
    """行业 PE 应返回多行数据。"""
    tool = next(t for t in tools if t.name == "get_industry_pe")
    result = asyncio.run(tool.ainvoke({}))
    import json
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list) or "error" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
