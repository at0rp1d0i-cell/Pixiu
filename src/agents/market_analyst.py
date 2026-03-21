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

from src.llm.openai_compat import build_researcher_llm
from src.schemas.market_context import MarketContextMemo, MarketRegime
from src.market.regime_detector import RegimeDetector
from src.schemas.stage_io import MarketContextOutput
from src.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()

MCP_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "akshare_server.py")
)

RSS_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "rss_server.py")
)

TUSHARE_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "tushare_server.py")
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
    "market_regime": "bull_trend",
    "index_ma5": 3320.5,
    "index_ma20": 3280.1,
    "index_ma60": 3150.8,
    "volatility_30d": 1.2,
    "return_30d": 5.3,
    "raw_summary": "今日北向净流入..."
}}
注意：
- historical_insights 必须是空列表 []，该字段由下游 LiteratureMiner 填充，你不需要生成。
- index_ma5/index_ma20/index_ma60：上证指数对应均线值，数据不可用时填 null。
- volatility_30d：近 30 日日均波动率（%），数据不可用时填 null。
- return_30d：近 30 日累计涨跌幅（%），数据不可用时填 null。
不需要解释，直接输出 JSON。"""

_DEFAULT_STAGE1_TIMEOUT_SEC = 60.0
_DEFAULT_STAGE1_MAX_TOOL_ROUNDS = 3


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def _get_stage1_timeout_sec() -> float:
    """Return a conservative wall-clock timeout for Stage 1 market fetching."""
    raw = os.getenv("PIXIU_STAGE1_TIMEOUT_SEC")
    if raw is None:
        return _DEFAULT_STAGE1_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "[Stage 1] 无法解析 PIXIU_STAGE1_TIMEOUT_SEC=%r，回退默认值 %.1fs",
            raw,
            _DEFAULT_STAGE1_TIMEOUT_SEC,
        )
        return _DEFAULT_STAGE1_TIMEOUT_SEC
    if value <= 0:
        logger.warning(
            "[Stage 1] PIXIU_STAGE1_TIMEOUT_SEC=%r 非法，回退默认值 %.1fs",
            raw,
            _DEFAULT_STAGE1_TIMEOUT_SEC,
        )
        return _DEFAULT_STAGE1_TIMEOUT_SEC
    return value


def _get_stage1_max_tool_rounds() -> int:
    """Return the maximum number of ReAct tool rounds allowed in Stage 1."""
    raw = os.getenv("PIXIU_STAGE1_MAX_TOOL_ROUNDS")
    if raw is None:
        return _DEFAULT_STAGE1_MAX_TOOL_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "[Stage 1] 无法解析 PIXIU_STAGE1_MAX_TOOL_ROUNDS=%r，回退默认值 %d",
            raw,
            _DEFAULT_STAGE1_MAX_TOOL_ROUNDS,
        )
        return _DEFAULT_STAGE1_MAX_TOOL_ROUNDS
    if value <= 0:
        logger.warning(
            "[Stage 1] PIXIU_STAGE1_MAX_TOOL_ROUNDS=%r 非法，回退默认值 %d",
            raw,
            _DEFAULT_STAGE1_MAX_TOOL_ROUNDS,
        )
        return _DEFAULT_STAGE1_MAX_TOOL_ROUNDS
    return value


def _stage1_rss_enabled() -> bool:
    raw = os.getenv("PIXIU_STAGE1_ENABLE_RSS", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class MarketAnalyst:
    """Stage 1 市场上下文分析师。

    使用 MCP ReAct 循环调用 AKShare 工具，最多 5 轮，生成 MarketContextMemo。
    """

    def __init__(self, mcp_tools: list, skill_loader: SkillLoader | None = None):
        self.tools = {t.name: t for t in mcp_tools}
        self.skill_loader = skill_loader or _SKILL_LOADER
        self.llm = build_researcher_llm(profile="market_analyst").bind_tools(mcp_tools)

    _TOOL_CALL_TIMEOUT_SEC = 15.0

    async def _invoke_tool_call(self, call: dict) -> ToolMessage:
        """Invoke one MCP tool call and normalize it into a ToolMessage."""
        tool = self.tools.get(call["name"])
        if tool:
            try:
                raw_result = await asyncio.wait_for(
                    tool.ainvoke(call["args"]),
                    timeout=self._TOOL_CALL_TIMEOUT_SEC,
                )
            except TimeoutError:
                raw_result = f"工具调用超时（{self._TOOL_CALL_TIMEOUT_SEC}s）: {call['name']}"
                logger.warning("[MarketAnalyst] 工具 %s 超时（%.0fs）", call["name"], self._TOOL_CALL_TIMEOUT_SEC)
            except Exception as e:
                raw_result = f"工具调用失败: {e}"
        else:
            raw_result = f"工具不存在: {call['name']}"
        return ToolMessage(
            content=self._extract_tool_text(raw_result),
            tool_call_id=call["id"],
        )

    @staticmethod
    def _extract_tool_text(result) -> str:
        """从 MCP 工具返回值中提取纯文本。

        langchain-mcp-adapters content_and_artifact 模式返回 list[dict]，
        每个 dict 含 type='text' + text='...'。需要提取 text 字段，
        否则 LLM 收到的是 Python repr 而非可解析的数据。
        """
        if isinstance(result, str):
            return result
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "text" in first:
                return first["text"]
        return str(result)

    async def analyze(self) -> MarketContextMemo:
        """执行 ReAct 循环生成今日 MarketContextMemo。"""
        system_content = MARKET_ANALYST_SYSTEM_PROMPT.format(today=_today_str())
        skill_context = self.skill_loader.load_for_agent("market_analyst")
        if skill_context:
            system_content = (
                system_content + "\n\n## 市场分析规范\n\n" + skill_context
            )

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content="请生成今日市场上下文备忘录。"),
        ]

        # ReAct 循环（默认最多 3 轮工具调用）
        used_all_rounds = False
        max_tool_rounds = _get_stage1_max_tool_rounds()
        for _ in range(max_tool_rounds):
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            if not getattr(response, "tool_calls", None):
                break

            tool_messages = await asyncio.gather(
                *(self._invoke_tool_call(call) for call in response.tool_calls)
            )
            messages.extend(tool_messages)
        else:
            used_all_rounds = True

        # 如果工具轮次用完 LLM 还在调工具，追加一轮无工具调用让它输出 JSON
        if used_all_rounds and not response.content.strip():
            logger.info("[MarketAnalyst] 工具轮次用尽（max=%d），追加 final call", max_tool_rounds)
            messages.append(HumanMessage(
                content="工具调用轮次已用完。请根据已获取的数据，直接输出 MarketContextMemo JSON。"
            ))
            llm_no_tools = build_researcher_llm(profile="market_analyst")
            response = await llm_no_tools.ainvoke(messages)

        return self._parse_memo(response.content)

    def _parse_memo(self, content: str) -> MarketContextMemo:
        """解析 LLM JSON 输出为 MarketContextMemo。降级时返回空 Memo。"""
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                # historical_insights 由 LiteratureMiner 填充，LLM 可能填错格式，强制清空
                if "historical_insights" in data:
                    hi = data["historical_insights"]
                    if not isinstance(hi, list) or (hi and not isinstance(hi[0], dict)):
                        data["historical_insights"] = []
                memo = MarketContextMemo(**data)
                # 确定性优先：从 memo 的类型化字段读取技术指标，用 RegimeDetector 覆盖 LLM 的 regime。
                # 数据不足时保留 LLM 的 regime（已通过 coerce validator 标准化）。
                regime = _apply_regime_detector(memo)
                if regime is not None:
                    memo = memo.model_copy(update={"market_regime": regime})
                    logger.info("[MarketAnalyst] RegimeDetector 覆盖 regime: %s", regime.value)
                return memo
            except Exception as e:
                logger.warning("[MarketAnalyst] JSON 解析失败: %s", e)
        # 降级：返回最小化空 Memo
        return _empty_memo("MarketAnalyst 输出解析失败")


def _apply_regime_detector(memo: "MarketContextMemo") -> MarketRegime | None:
    """从 MarketContextMemo 的类型化技术指标字段调用 RegimeDetector 产生确定性 regime。

    当 memo 包含 index_ma5/index_ma20/index_ma60 和 volatility_30d 四个字段时执行检测（数据充分）。
    数据不足时返回 None，调用方保留 LLM 的 regime。
    """
    ma5 = memo.index_ma5
    ma20 = memo.index_ma20
    ma60 = memo.index_ma60
    volatility_30d = memo.volatility_30d

    # 必须同时具备均线三值和波动率才算数据充分
    if any(v is None for v in (ma5, ma20, ma60, volatility_30d)):
        return None

    try:
        detector = RegimeDetector()
        market_data = {
            "volatility_30d": float(volatility_30d),
            "ma5": float(ma5),
            "ma20": float(ma20),
            "ma60": float(ma60),
        }
        # return_30d 可选，有则带入
        if memo.return_30d is not None:
            market_data["market_return_30d"] = float(memo.return_30d)

        return detector.detect(market_data)
    except Exception as e:
        logger.warning("[MarketAnalyst] RegimeDetector 调用失败，保留 LLM regime: %s", e)
        return None


def _empty_memo(reason: str, active_islands: list[str] | None = None) -> MarketContextMemo:
    """生成最小化降级 Memo。"""
    return MarketContextMemo(
        date=_today_str(),
        northbound=None,
        macro_signals=[],
        hot_themes=[],
        historical_insights=[],
        suggested_islands=active_islands or ["momentum"],
        market_regime="range_bound",
        raw_summary=f"市场数据获取失败：{reason}",
    )


# ─────────────────────────────────────────────────────────
# LangGraph 节点
# ─────────────────────────────────────────────────────────

async def _run_market_context_once(state: dict) -> dict:
    """Execute one market-context fetch attempt without outer timeout handling."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    mcp_server_path = MCP_SERVER_PATH

    servers: dict = {
        "akshare": {
            "command": "python",
            "args": [mcp_server_path],
            "transport": "stdio",
        },
    }
    if _stage1_rss_enabled():
        servers["rss"] = {
            "command": "python",
            "args": [RSS_SERVER_PATH],
            "transport": "stdio",
        }
    if os.getenv("TUSHARE_TOKEN"):
        servers["tushare"] = {
            "command": "python",
            "args": [TUSHARE_SERVER_PATH],
            "transport": "stdio",
        }
    mcp_client = MultiServerMCPClient(servers)
    tools = await mcp_client.get_tools()
    analyst = MarketAnalyst(mcp_tools=tools)
    memo = await analyst.analyze()
    logger.info("[Stage 1] 市场上下文生成成功，Regime=%s", memo.market_regime)
    return {"market_context": memo}


async def _market_context_async(state: dict) -> dict:
    """异步执行 Stage 1 市场上下文生成。"""
    active_islands = list(state.get("active_islands", ["momentum"]))
    timeout_sec = _get_stage1_timeout_sec()

    try:
        return await asyncio.wait_for(_run_market_context_once(state), timeout=timeout_sec)
    except TimeoutError:
        logger.warning("[Stage 1] MarketAnalyst 超时（%.1fs），使用空上下文", timeout_sec)
        return {
            "market_context": _empty_memo(
                f"Stage 1 timeout after {timeout_sec:.1f}s",
                active_islands=active_islands,
            )
        }
    except Exception as e:
        logger.warning("[Stage 1] MarketAnalyst 失败，使用空上下文: %s", e)
        return {"market_context": _empty_memo(str(e), active_islands=active_islands)}


def market_context_node(state: dict) -> MarketContextOutput:
    """LangGraph Stage 1 同步入口。"""
    return asyncio.run(_market_context_async(state))
