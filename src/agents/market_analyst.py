"""
Pixiu v2 Stage 1：MarketAnalyst Agent

职责：调用 AKShare MCP 工具获取实时市场数据，生成今日市场上下文 MarketContextMemo。
MCP 工具：复用 akshare_server.py 中的 10 个工具（ReAct 循环，最多 5 轮）。

降级策略：MCP 工具失败时，回退到空上下文（由 LiteratureMiner 负责历史洞察）。
"""
import asyncio
import json
import logging
import os
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.schemas.market_context import MarketContextMemo, NorthboundFlow, MacroSignal

logger = logging.getLogger(__name__)

MCP_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "akshare_server.py")
)

MARKET_ANALYST_SYSTEM_PROMPT = """你是 Pixiu 的市场分析师，负责每日开盘前生成市场上下文备忘录。

今天的日期：{today}

你需要：
1. 调用工具获取北向资金、热门板块、宏观信号（PMI/M2/CPI）
2. 判断当前市场 regime（trending_up/trending_down/sideways/volatile）
3. 基于数据推断哪些 Island 方向本轮最值得探索
4. 输出一份简洁的 MarketContextMemo JSON

Island 选项：momentum（动量）、northbound（北向资金）、
valuation（估值）、volatility（波动率）、volume（量价）、sentiment（情绪）

必须以合法的 JSON 输出，格式见 MarketContextMemo schema：
{{
    "date": "YYYY-MM-DD",
    "northbound": {{
        "net_buy_bn": 12.5,
        "top_sectors": ["科技", "消费"],
        "top_stocks": ["600519", "000858"],
        "sentiment": "bullish"
    }},
    "macro_signals": [{{"signal": "...", "source": "pmi", "direction": "positive", "confidence": 0.8}}],
    "hot_themes": ["AI算力", "新能源"],
    "historical_insights": [],
    "suggested_islands": ["momentum", "northbound"],
    "market_regime": "trending_up",
    "raw_summary": "今日北向净流入..."
}}
不需要解释，直接输出 JSON。"""


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


class MarketAnalyst:
    """Stage 1 市场上下文分析师。

    使用 MCP ReAct 循环调用 AKShare 工具，最多 5 轮，生成 MarketContextMemo。
    """

    def __init__(self, mcp_tools: list):
        self.tools = {t.name: t for t in mcp_tools}
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.1,
        ).bind_tools(mcp_tools)

    async def analyze(self) -> MarketContextMemo:
        """执行 ReAct 循环生成今日 MarketContextMemo。"""
        messages = [
            SystemMessage(content=MARKET_ANALYST_SYSTEM_PROMPT.format(today=_today_str())),
            HumanMessage(content="请生成今日市场上下文备忘录。"),
        ]

        # ReAct 循环（最多 5 轮工具调用）
        for _ in range(5):
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            if not getattr(response, "tool_calls", None):
                break

            for call in response.tool_calls:
                tool = self.tools.get(call["name"])
                if tool:
                    try:
                        tool_result = await tool.ainvoke(call["args"])
                    except Exception as e:
                        tool_result = f"工具调用失败: {e}"
                    messages.append(ToolMessage(content=str(tool_result), tool_call_id=call["id"]))

        return self._parse_memo(response.content)

    def _parse_memo(self, content: str) -> MarketContextMemo:
        """解析 LLM JSON 输出为 MarketContextMemo。降级时返回空 Memo。"""
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return MarketContextMemo(**data)
            except Exception as e:
                logger.warning("[MarketAnalyst] JSON 解析失败: %s", e)
        # 降级：返回最小化空 Memo
        return _empty_memo("MarketAnalyst 输出解析失败")


def _empty_memo(reason: str, active_islands: list[str] | None = None) -> MarketContextMemo:
    """生成最小化降级 Memo。"""
    return MarketContextMemo(
        date=_today_str(),
        northbound=None,
        macro_signals=[],
        hot_themes=[],
        historical_insights=[],
        suggested_islands=active_islands or ["momentum"],
        market_regime="unknown",
        raw_summary=f"市场数据获取失败：{reason}",
    )


# ─────────────────────────────────────────────────────────
# LangGraph 节点
# ─────────────────────────────────────────────────────────

async def _market_context_async(state: dict) -> dict:
    """异步执行 Stage 1 市场上下文生成。"""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    mcp_server_path = MCP_SERVER_PATH
    active_islands = list(state.get("active_islands", ["momentum"]))

    try:
        mcp_client = MultiServerMCPClient({
            "akshare": {
                "command": "python",
                "args": [mcp_server_path],
                "transport": "stdio",
            }
        })
        tools = await mcp_client.get_tools()
        analyst = MarketAnalyst(mcp_tools=tools)
        memo = await analyst.analyze()
        logger.info("[Stage 1] 市场上下文生成成功，Regime=%s", memo.market_regime)
    except Exception as e:
        logger.warning("[Stage 1] MarketAnalyst 失败，使用空上下文: %s", e)
        memo = _empty_memo(str(e), active_islands=active_islands)

    return {**state, "market_context": memo}


def market_context_node(state: dict) -> dict:
    """LangGraph Stage 1 同步入口。"""
    return asyncio.run(_market_context_async(state))
