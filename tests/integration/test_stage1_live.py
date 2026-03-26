"""
Stage 1 live integration checks for the current Tushare blocking-core assumptions.

Run with:
    uv run pytest -q tests/integration/test_stage1_live.py -m live -v -s
"""
import asyncio
import json
import os

import pytest
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agents.market_analyst import TUSHARE_SERVER_PATH, _build_stage1_stdio_server

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("TUSHARE_TOKEN"), reason="requires TUSHARE_TOKEN"),
]


def _extract_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list) and result:
        return result[0].get("text", str(result[0]))
    return str(result)


@pytest.fixture(scope="module")
def tushare_tools():
    client = MultiServerMCPClient({"tushare": _build_stage1_stdio_server(TUSHARE_SERVER_PATH)})
    return asyncio.run(client.get_tools())


def test_tushare_blocking_tools_live_discovered(tushare_tools):
    tool_names = {tool.name for tool in tushare_tools}
    assert "get_moneyflow_hsgt" in tool_names
    assert "get_margin_data" in tool_names


def test_tushare_moneyflow_hsgt_live_returns_payload(tushare_tools):
    tool = next((candidate for candidate in tushare_tools if candidate.name == "get_moneyflow_hsgt"), None)
    assert tool is not None, "get_moneyflow_hsgt tool not found"

    raw = asyncio.run(tool.ainvoke({"limit": 5}))
    text = _extract_text(raw)
    print(f"\n[moneyflow_hsgt] {text[:300]}")

    payload = json.loads(text)
    assert "error" not in payload, f"tool returned error: {payload}"
    if isinstance(payload, dict):
        assert "data" in payload


def test_tushare_margin_data_live_returns_payload(tushare_tools):
    tool = next((candidate for candidate in tushare_tools if candidate.name == "get_margin_data"), None)
    assert tool is not None, "get_margin_data tool not found"

    raw = asyncio.run(tool.ainvoke({}))
    text = _extract_text(raw)
    print(f"\n[margin_data] {text[:300]}")

    payload = json.loads(text)
    assert "error" not in payload, f"tool returned error: {payload}"
    if isinstance(payload, dict):
        assert "data" in payload or "items" in payload
