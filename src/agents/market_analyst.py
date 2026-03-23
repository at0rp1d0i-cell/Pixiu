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
import sys
from datetime import date
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.llm.openai_compat import build_researcher_llm
from src.schemas.market_context import MarketContextMemo, MarketRegime
from src.market.regime_detector import RegimeDetector
from src.schemas.stage_io import MarketContextOutput
from src.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()
_DEGRADED_SUMMARY_PREFIX = "市场数据获取失败："

_STAGE1_BLOCKING_TOOL_NAMES = frozenset(
    {
        "get_moneyflow_hsgt",
        "get_margin_data",
    }
)

_STAGE1_ENRICHMENT_TOOL_NAMES = frozenset(
    {
        "get_news",
        "get_market_hot_topics",
    }
)

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
1. 优先调用 blocking core 工具获取北向资金和市场级风险偏好信号
2. 如有可用 enrichment 工具，再补充热点题材或新闻摘要
3. 判断当前市场 regime（trending_up/trending_down/sideways/volatile）
4. 基于数据推断哪些 Island 方向本轮最值得探索
5. 输出一份简洁的 MarketContextMemo JSON

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
- blocking core 缺失时，不要编造数据；允许 northbound=null、hot_themes=[]、macro_signals=[]。
- historical_insights 必须是空列表 []，该字段由下游 LiteratureMiner 填充，你不需要生成。
- index_ma5/index_ma20/index_ma60：上证指数对应均线值，数据不可用时填 null。
- volatility_30d：近 30 日日均波动率（%），数据不可用时填 null。
- return_30d：近 30 日累计涨跌幅（%），数据不可用时填 null。
不需要解释，直接输出 JSON。"""

_DEFAULT_STAGE1_TIMEOUT_SEC = 60.0
_DEFAULT_STAGE1_MAX_TOOL_ROUNDS = 3
_MAX_STAGE1_SAMPLE_FAILURES = 5


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


def _build_stage1_stdio_server(server_path: str) -> dict[str, object]:
    """Build stdio server config with explicit env forwarding for child MCP processes."""
    return {
        "command": sys.executable,
        "args": [server_path],
        "transport": "stdio",
        "env": dict(os.environ),
    }


def _select_stage1_tools(tools: list) -> dict[str, list]:
    """Split Stage 1 tools into blocking and enrichment allowlists."""
    selected = {"blocking": [], "enrichment": []}
    for tool in tools:
        name = getattr(tool, "name", "")
        if name in _STAGE1_BLOCKING_TOOL_NAMES:
            selected["blocking"].append(tool)
        elif name in _STAGE1_ENRICHMENT_TOOL_NAMES:
            selected["enrichment"].append(tool)
    return selected


def is_degraded_market_context(memo: MarketContextMemo | None) -> bool:
    if memo is None:
        return True
    return memo.raw_summary.startswith(_DEGRADED_SUMMARY_PREFIX)


def _extract_degrade_reason(summary: str | None) -> str | None:
    if not summary:
        return None
    if summary.startswith(_DEGRADED_SUMMARY_PREFIX):
        return summary[len(_DEGRADED_SUMMARY_PREFIX):].strip()
    return summary


def _empty_stage1_reliability() -> dict:
    return {
        "blocking_required": False,
        "blocking_tools_expected": [],
        "blocking_tools_used": [],
        "enrichment_tools_used": [],
        "tool_calls_total": 0,
        "tool_timeouts_total": 0,
        "tool_errors_total": 0,
        "finalization_forced": False,
        "degraded": False,
        "degrade_reason": None,
        "tool_stats": {},
        "sample_failures": [],
    }


class MarketAnalyst:
    """Stage 1 市场上下文分析师。

    使用 MCP ReAct 循环调用 AKShare 工具，最多 5 轮，生成 MarketContextMemo。
    """

    def __init__(self, mcp_tools: list, skill_loader: SkillLoader | None = None):
        self.tools = {t.name: t for t in mcp_tools}
        self.skill_loader = skill_loader or _SKILL_LOADER
        self.llm = build_researcher_llm(profile="market_analyst").bind_tools(mcp_tools)
        self._last_reliability_diagnostics: dict = _empty_stage1_reliability()

    _TOOL_CALL_TIMEOUT_SEC = 15.0

    async def _invoke_tool_call(self, call: dict) -> tuple[ToolMessage, dict]:
        """Invoke one MCP tool call and normalize it into a ToolMessage."""
        started = perf_counter()
        tool_name = str(call.get("name", "unknown_tool"))
        failed_kind: str | None = None
        failed_message: str | None = None
        tool = self.tools.get(call["name"])
        if tool:
            try:
                raw_result = await asyncio.wait_for(
                    tool.ainvoke(call["args"]),
                    timeout=self._TOOL_CALL_TIMEOUT_SEC,
                )
            except TimeoutError:
                raw_result = f"工具调用超时（{self._TOOL_CALL_TIMEOUT_SEC}s）: {call['name']}"
                failed_kind = "timeout"
                failed_message = raw_result
                logger.warning("[MarketAnalyst] 工具 %s 超时（%.0fs）", call["name"], self._TOOL_CALL_TIMEOUT_SEC)
            except Exception as e:
                raw_result = f"工具调用失败: {e}"
                failed_kind = "error"
                failed_message = str(e)
        else:
            raw_result = f"工具不存在: {call['name']}"
            failed_kind = "error"
            failed_message = raw_result
        elapsed_ms = round((perf_counter() - started) * 1000.0, 2)
        trace = {
            "tool": tool_name,
            "latency_ms": elapsed_ms,
            "timed_out": failed_kind == "timeout",
            "errored": failed_kind is not None,
        }
        if failed_kind is not None:
            trace["failure"] = {
                "tool": tool_name,
                "kind": failed_kind,
                "message": failed_message or raw_result,
            }
        return ToolMessage(
            content=self._extract_tool_text(raw_result),
            tool_call_id=call["id"],
        ), trace

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

    @staticmethod
    def _contains_json_payload(content: str) -> bool:
        """Best-effort check: whether response content contains a JSON object block."""
        if not isinstance(content, str):
            return False
        if not content.strip():
            return False
        return re.search(r'\{.*\}', content, re.DOTALL) is not None

    async def analyze(self) -> MarketContextMemo:
        """执行 ReAct 循环生成今日 MarketContextMemo。"""
        tool_stats: dict[str, dict[str, float | int]] = {}
        blocking_tools_used: set[str] = set()
        enrichment_tools_used: set[str] = set()
        sample_failures: list[dict[str, str]] = []
        tool_calls_total = 0
        tool_timeouts_total = 0
        tool_errors_total = 0
        finalization_forced = False

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

            tool_results = await asyncio.gather(
                *(self._invoke_tool_call(call) for call in response.tool_calls)
            )
            for tool_message, trace in tool_results:
                messages.append(tool_message)
                tool_name = trace["tool"]
                stats = tool_stats.setdefault(
                    tool_name,
                    {
                        "calls": 0,
                        "timeouts": 0,
                        "errors": 0,
                        "latency_total_ms": 0.0,
                        "max_latency_ms": 0.0,
                    },
                )
                stats["calls"] += 1
                tool_calls_total += 1
                latency_ms = float(trace.get("latency_ms", 0.0))
                stats["latency_total_ms"] += latency_ms
                stats["max_latency_ms"] = max(float(stats["max_latency_ms"]), latency_ms)
                if trace.get("timed_out"):
                    stats["timeouts"] += 1
                    tool_timeouts_total += 1
                if trace.get("errored"):
                    stats["errors"] += 1
                    tool_errors_total += 1
                if tool_name in _STAGE1_BLOCKING_TOOL_NAMES:
                    blocking_tools_used.add(tool_name)
                elif tool_name in _STAGE1_ENRICHMENT_TOOL_NAMES:
                    enrichment_tools_used.add(tool_name)
                failure = trace.get("failure")
                if isinstance(failure, dict) and len(sample_failures) < _MAX_STAGE1_SAMPLE_FAILURES:
                    sample_failures.append(
                        {
                            "tool": str(failure.get("tool", tool_name)),
                            "kind": str(failure.get("kind", "error")),
                            "message": str(failure.get("message", "")),
                        }
                    )
        else:
            used_all_rounds = True

        # 工具轮次耗尽后，若响应仍是工具意图或无 JSON，则强制收尾一次 JSON-only 响应。
        if used_all_rounds and (
            bool(getattr(response, "tool_calls", None))
            or not self._contains_json_payload(getattr(response, "content", ""))
        ):
            finalization_forced = True
            logger.info(
                "[MarketAnalyst] 工具轮次用尽（max=%d），追加 final call 强制 JSON 收尾",
                max_tool_rounds,
            )
            messages.append(HumanMessage(
                content="工具调用轮次已用完。请根据已获取的数据，直接输出 MarketContextMemo JSON。"
            ))
            llm_no_tools = build_researcher_llm(profile="market_analyst")
            response = await llm_no_tools.ainvoke(messages)

        memo = self._parse_memo(response.content)
        tool_stats_payload: dict[str, dict[str, float | int]] = {}
        for tool_name, stats in tool_stats.items():
            calls = int(stats["calls"])
            avg_latency = round(float(stats["latency_total_ms"]) / calls, 2) if calls > 0 else 0.0
            tool_stats_payload[tool_name] = {
                "calls": calls,
                "timeouts": int(stats["timeouts"]),
                "errors": int(stats["errors"]),
                "avg_latency_ms": avg_latency,
                "max_latency_ms": round(float(stats["max_latency_ms"]), 2),
            }
        self._last_reliability_diagnostics = {
            **_empty_stage1_reliability(),
            "blocking_tools_used": sorted(blocking_tools_used),
            "enrichment_tools_used": sorted(enrichment_tools_used),
            "tool_calls_total": tool_calls_total,
            "tool_timeouts_total": tool_timeouts_total,
            "tool_errors_total": tool_errors_total,
            "finalization_forced": finalization_forced,
            "degraded": is_degraded_market_context(memo),
            "degrade_reason": _extract_degrade_reason(getattr(memo, "raw_summary", None)),
            "tool_stats": tool_stats_payload,
            "sample_failures": sample_failures,
        }
        return memo

    def get_reliability_diagnostics(self) -> dict:
        return dict(self._last_reliability_diagnostics)

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

    servers: dict = {
        "akshare": _build_stage1_stdio_server(MCP_SERVER_PATH),
    }
    if _stage1_rss_enabled():
        servers["rss"] = _build_stage1_stdio_server(RSS_SERVER_PATH)
    if os.getenv("TUSHARE_TOKEN"):
        servers["tushare"] = _build_stage1_stdio_server(TUSHARE_SERVER_PATH)
    mcp_client = MultiServerMCPClient(servers)
    selected_tools = _select_stage1_tools(await mcp_client.get_tools())
    blocking_tools = selected_tools["blocking"]
    enrichment_tools = selected_tools["enrichment"]
    if not blocking_tools:
        raise RuntimeError("No Stage 1 blocking tools available")
    analyst = MarketAnalyst(mcp_tools=[*blocking_tools, *enrichment_tools])
    memo = await analyst.analyze()
    reliability = analyst.get_reliability_diagnostics()
    reliability["blocking_tools_expected"] = sorted(
        [getattr(tool, "name", "") for tool in blocking_tools if getattr(tool, "name", "")]
    )
    logger.info("[Stage 1] 市场上下文生成成功，Regime=%s", memo.market_regime)
    return {"market_context": memo, "stage1_reliability": reliability}


async def _market_context_async(state: dict) -> dict:
    """异步执行 Stage 1 市场上下文生成。"""
    active_islands = list(state.get("active_islands", ["momentum"]))
    timeout_sec = _get_stage1_timeout_sec()

    try:
        return await asyncio.wait_for(_run_market_context_once(state), timeout=timeout_sec)
    except TimeoutError:
        logger.warning("[Stage 1] MarketAnalyst 超时（%.1fs），使用空上下文", timeout_sec)
        reason = f"Stage 1 timeout after {timeout_sec:.1f}s"
        return {
            "market_context": _empty_memo(
                reason,
                active_islands=active_islands,
            ),
            "stage1_reliability": {
                **_empty_stage1_reliability(),
                "degraded": True,
                "degrade_reason": reason,
            },
        }
    except Exception as e:
        logger.warning("[Stage 1] MarketAnalyst 失败，使用空上下文: %s", e)
        reason = str(e)
        return {
            "market_context": _empty_memo(reason, active_islands=active_islands),
            "stage1_reliability": {
                **_empty_stage1_reliability(),
                "degraded": True,
                "degrade_reason": reason,
            },
        }


def market_context_node(state: dict) -> MarketContextOutput:
    """LangGraph Stage 1 同步入口。"""
    return asyncio.run(_market_context_async(state))
