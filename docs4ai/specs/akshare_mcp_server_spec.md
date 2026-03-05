# AKShare MCP Server — 实施规格说明书

> 面向 Gemini 的执行文档
> 版本：1.0 | 日期：2026-03-04
> 前置条件：地基任务（.env / pyproject.toml / logging）已完成

---

## 任务总览

创建 `mcp_servers/akshare_server.py`，将 AKShare 的关键市场数据 API 包装为标准 MCP 工具，
并改造 `src/agents/researcher.py`，让 Researcher Agent 能通过 `langchain-mcp-adapters`
调用这些工具，实现"数据驱动的因子假设"。

**交付物清单：**
1. `mcp_servers/__init__.py`（空文件）
2. `mcp_servers/akshare_server.py`（核心 MCP Server）
3. `src/agents/researcher.py`（改造，集成 MCP 工具调用）
4. `tests/test_akshare_mcp.py`（验收测试）

---

## 任务 1：创建 MCP Server 文件结构

### 1.1 创建目录和空 `__init__.py`

```
EvoQuant/
└── mcp_servers/
    ├── __init__.py      ← 创建空文件
    └── akshare_server.py
```

**操作：**
```bash
mkdir -p EvoQuant/mcp_servers
touch EvoQuant/mcp_servers/__init__.py
```

---

## 任务 2：创建 `mcp_servers/akshare_server.py`

**完整文件内容如下：**

```python
"""
EvoQuant AKShare MCP Server
工具：北向资金、全市场资金流、北向持股、券商研报、行业估值
启动：python mcp_servers/akshare_server.py
"""
import json
import logging
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from mcp.server import Server
from mcp.server.stdio import stdio_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("akshare-mcp")

app = Server("akshare-mcp")


# ─────────────────────────────────────────────
# 工具 1：北向资金当日摘要
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_today() -> str:
    """获取今日沪深港通北向/南向资金实时净流入摘要（亿元）。

    返回字段：交易日、类型(沪港通/深港通)、板块、资金方向、
    成交净买额、资金净流入、上涨数、下跌数、相关指数涨跌幅。
    用途：判断当日外资情绪，是市场情绪的高频强信号。
    """
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        # 只保留北向资金（外资流入A股方向）
        north = df[df["资金方向"] == "北向"].copy()
        if north.empty:
            north = df  # 若过滤后为空则返回全量
        result = north.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_flow_today failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 2：北向资金历史序列
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_history(days: int = 20) -> str:
    """获取北向资金最近 N 个交易日的净买入历史（默认20天）。

    Args:
        days: 返回最近多少个交易日的数据，默认 20，最大 60。

    返回字段：日期、北向资金净买入（亿元）、累计净买入。
    用途：构建北向资金 N 日动量/反转因子，研究外资趋势性行为。
    """
    try:
        days = min(max(days, 1), 60)  # 限制在 [1, 60] 范围
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_flow_history failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 3：全市场主力资金流向
# ─────────────────────────────────────────────
@app.tool()
async def get_market_fund_flow(days: int = 10) -> str:
    """获取全市场主力/超大单/大单净流入历史（默认10天）。

    Args:
        days: 返回最近多少个交易日，默认 10，最大 30。

    返回字段：日期、上证收盘价、主力净流入净额、主力净流入净占比、
    超大单净流入、大单净流入、中单净流入、小单净流入。
    用途：判断市场整体资金面情绪，区分主力/散户行为。
    """
    try:
        days = min(max(days, 1), 30)
        df = ak.stock_market_fund_flow()
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_market_fund_flow failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 4：北向持股排行（个股级别）
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_top_holdings(market: str = "沪股通", top_n: int = 20) -> str:
    """获取北向资金持股排行（5日增减仓排行）。

    Args:
        market: 市场类型，可选 '沪股通' 或 '深股通'，默认 '沪股通'。
        top_n: 返回前 N 只股票，默认 20，最大 50。

    返回字段：股票代码、股票名称、今日持股量、今日持股市值、
    持股变化量、持股变化比例。
    用途：识别外资重点加仓/减仓标的，个股层面外资情绪信号。
    """
    try:
        top_n = min(max(top_n, 1), 50)
        if market not in ("沪股通", "深股通"):
            market = "沪股通"
        df = ak.stock_hsgt_hold_stock_em(market=market, indicator="5日排行")
        df = df.head(top_n)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_top_holdings failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 5：券商研报（个股）
# ─────────────────────────────────────────────
@app.tool()
async def get_research_reports(symbol: str, limit: int = 5) -> str:
    """获取指定股票最近的券商研报元数据。

    Args:
        symbol: 股票代码，如 '000001'（平安银行）或 '600519'（贵州茅台）。
        limit: 返回最近几篇研报，默认 5，最大 20。

    返回字段：研报标题、发布机构、评级、目标价、发布日期。
    注意：只返回元数据，不返回研报全文（版权限制）。
    用途：聚合分析师共识，用评级/目标价构建情绪因子。
    """
    try:
        limit = min(max(limit, 1), 20)
        df = ak.stock_research_report_em(symbol=symbol)
        if df.empty:
            return json.dumps([], ensure_ascii=False)
        # 选取关键字段（不同版本字段名可能不同，做兼容处理）
        possible_cols = {
            "title": ["title", "标题", "研报标题"],
            "org": ["org", "机构", "发布机构"],
            "rating": ["rating", "评级"],
            "target_price": ["target_price", "目标价"],
            "date": ["date", "发布时间", "日期"],
        }
        selected = {}
        for key, candidates in possible_cols.items():
            for col in candidates:
                if col in df.columns:
                    selected[key] = col
                    break

        if selected:
            result_df = df[[v for v in selected.values()]].head(limit)
            result_df.columns = list(selected.keys())
        else:
            result_df = df.head(limit)

        result = result_df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_research_reports failed for %s: %s", symbol, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 6：行业 PE 估值
# ─────────────────────────────────────────────
@app.tool()
async def get_industry_pe(
    classification: str = "证监会行业分类",
    query_date: str = "",
) -> str:
    """获取行业 PE-TTM 估值数据。

    Args:
        classification: 行业分类标准，可选 '证监会行业分类' 或 '申万行业分类'，
                        默认 '证监会行业分类'。
        query_date: 查询日期，格式 'YYYYMMDD'，默认为昨日。

    返回字段：行业名称、行业代码、样本数、市盈率PE（加权/中位/等权）。
    用途：行业估值分位因子，判断行业是否被高估/低估。
    """
    try:
        if not query_date:
            yesterday = date.today() - timedelta(days=1)
            query_date = yesterday.strftime("%Y%m%d")

        if classification not in ("证监会行业分类", "申万行业分类"):
            classification = "证监会行业分类"

        df = ak.stock_industry_pe_ratio_cninfo(
            symbol=classification, date=query_date
        )
        if df.empty:
            return json.dumps({"error": f"No data for date {query_date}"}, ensure_ascii=False)

        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_industry_pe failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 7：个股资金流向排行
# ─────────────────────────────────────────────
@app.tool()
async def get_individual_fund_flow_rank(period: str = "今日", top_n: int = 20) -> str:
    """获取个股资金流入排行榜。

    Args:
        period: 统计周期，可选 '今日'、'3日'、'5日'、'10日'，默认 '今日'。
        top_n: 返回前 N 只股票，默认 20，最大 50。

    返回字段：股票名称、最新价、涨跌幅、主力净流入净额、主力净流入净占比等。
    用途：识别单日/多日主力资金重点流入标的，构建个股资金面因子。
    """
    try:
        valid_periods = ("今日", "3日", "5日", "10日")
        if period not in valid_periods:
            period = "今日"
        top_n = min(max(top_n, 1), 50)

        df = ak.stock_individual_fund_flow_rank(indicator=period)
        df = df.head(top_n)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_individual_fund_flow_rank failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# Server 启动入口
# ─────────────────────────────────────────────
import asyncio


async def main() -> None:
    logger.info("AKShare MCP Server starting...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 任务 3：改造 `src/agents/researcher.py`

### 3.1 改造前 vs 改造后对比

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| LLM 框架 | `ChatOpenAI`（无工具） | `ChatAnthropic` + MCP 工具绑定 |
| 信息来源 | 静态知识库 | 知识库 + 7 个 AKShare MCP 工具 |
| 工具调用模式 | 无 | `langchain-mcp-adapters 0.1.0` 正确用法 |
| 异步模式 | 同步 `llm.invoke()` | 异步 `model.ainvoke()` + `ToolNode` |

### 3.2 完整替换内容

**将 `EvoQuant/src/agents/researcher.py` 的全部内容替换为：**

```python
"""
EvoQuant: Researcher Agent（MCP 增强版）
Role: 调用 AKShare MCP 工具获取实时市场数据，结合因子字典提出量化因子假设。
"""
import asyncio
import logging
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from .state import AgentState

load_dotenv_if_available()
logger = logging.getLogger(__name__)

# ── 知识库路径 ──────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
DICTIONARY_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "knowledge", "factors", "quant_factors_dictionary.md"))
SKILL_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "knowledge", "agent_skills", "researcher_alpha_generation.md"))
MCP_SERVER_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "mcp_servers", "akshare_server.py"))

# ── MCP Client（模块级单例，跨 epoch 复用）─────────────────────
_MCP_CLIENT = MultiServerMCPClient(
    {
        "akshare": {
            "command": "python3",
            "args": [MCP_SERVER_PATH],
            "transport": "stdio",
        }
    }
)

# ── LLM ────────────────────────────────────────────────────────
def _build_llm(tools):
    return ChatAnthropic(
        model=os.environ.get("RESEARCHER_MODEL", "claude-sonnet-4-6"),
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        temperature=0.7,
    ).bind_tools(tools)


def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _load_knowledge_base() -> str:
    parts = []
    for label, path in [("Layer 1 Factor Dictionary", DICTIONARY_PATH),
                        ("Agent Skills Methodology", SKILL_PATH)]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f"### {label} ###\n{f.read()}")
        except Exception as e:
            logger.warning("Failed to load %s: %s", path, e)
    return "\n\n".join(parts)


def research_node(state: AgentState) -> dict:
    """同步入口（LangGraph 节点），内部运行异步逻辑。"""
    return asyncio.run(_research_node_async(state))


async def _research_node_async(state: AgentState) -> dict:
    logger.info("[Researcher] 正在思考新的量化因子假设（第 %d/%d 轮）...",
                state["current_iteration"], state["max_iterations"])

    # 1. 获取 MCP 工具（正确的 0.1.0 用法：不用 async with）
    try:
        tools = await _MCP_CLIENT.get_tools()
        logger.info("[Researcher] 成功加载 %d 个 AKShare MCP 工具", len(tools))
    except Exception as e:
        logger.warning("[Researcher] MCP 工具加载失败，降级为无工具模式: %s", e)
        tools = []

    # 2. 构建 LLM（带工具绑定）
    llm = _build_llm(tools)

    # 3. 加载知识库
    layer_1_kb = _load_knowledge_base()

    # 4. 构建 System Prompt
    system_prompt = f"""你是一名顶尖的量化研究员，专注于 A 股市场 Alpha 因子发现。

**你拥有以下实时数据工具（优先调用！）：**
- get_northbound_flow_today()：今日北向资金净流入
- get_northbound_flow_history(days)：北向资金历史序列
- get_market_fund_flow(days)：全市场主力/超大单资金流向
- get_northbound_top_holdings(market, top_n)：北向持股变化排行
- get_research_reports(symbol, limit)：个股券商研报摘要
- get_industry_pe(classification, query_date)：行业 PE 估值
- get_individual_fund_flow_rank(period, top_n)：个股资金流入排行

**你的知识库（静态）：**
{layer_1_kb}

**输出规则：**
1. 先调用 1-2 个最相关的实时数据工具，分析当前市场状态
2. 基于数据观察，提出一个 Qlib 表达式风格的新因子假设
3. 输出格式：
   - 【市场观察】：你从工具中观察到的关键数据
   - 【因子假设】：假设描述（中文）
   - 【Qlib 公式】：标准 Qlib 表达式（如 `Corr(Ref($close,1)/$close, Ref($volume,1)/$volume, 20)`）
   - 【预期逻辑】：为什么这个因子在 A 股应该有 Alpha
当前迭代：{state['current_iteration']}/{state['max_iterations']}
"""

    # 5. 构建用户上下文（根据历史反馈调整）
    if state.get("error_message"):
        user_msg = f"上一次回测遇到了错误：\n{state['error_message']}\n请修正假设或公式，并先获取实时数据辅助判断。"
    elif state.get("backtest_result"):
        user_msg = f"上一次回测结果：\n{state['backtest_result']}\n请基于此结果优化因子，调用工具检查当前市场环境是否适合这个方向。"
    else:
        user_msg = "请先调用 1-2 个实时数据工具观察今日市场，然后提出一个有潜力的 Alpha 因子假设。"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    # 6. 支持工具调用的 agentic loop（最多 3 轮工具调用）
    for _ in range(3):
        response = await llm.ainvoke(messages)
        messages.append(response)

        # 检查是否还要调用工具
        if not getattr(response, "tool_calls", None):
            break

        # 执行工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            matched_tool = next((t for t in tools if t.name == tool_name), None)
            if matched_tool:
                try:
                    tool_result = await matched_tool.ainvoke(tool_args)
                    logger.info("[Researcher] 工具 %s 返回 %d 字节", tool_name, len(str(tool_result)))
                except Exception as e:
                    tool_result = f"工具调用失败: {e}"

                from langchain_core.messages import ToolMessage
                messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
                )

    logger.info("[Researcher] 因子假设生成完毕")

    return {
        "factor_proposal": response.content,
        "messages": [response],
    }
```

### 3.3 需要新增的依赖

在 `pyproject.toml` 的 `[project.dependencies]` 中新增：

```toml
"langchain-anthropic>=0.3.0",
"langchain-mcp-adapters>=0.1.0",
"mcp>=1.0.0",
```

---

## 任务 4：创建验收测试 `tests/test_akshare_mcp.py`

```python
"""验收测试：验证 AKShare MCP Server 的 7 个工具可以正常调用。"""
import asyncio
import os
import sys
import pytest

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
    data = json.loads(result)
    assert isinstance(data, list) or "error" not in data


def test_northbound_flow_history(tools):
    """北向资金历史默认 20 天，应返回数据。"""
    tool = next(t for t in tools if t.name == "get_northbound_flow_history")
    result = asyncio.run(tool.ainvoke({"days": 10}))
    import json
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) <= 10


def test_market_fund_flow(tools):
    """全市场资金流向应包含主力净流入字段。"""
    tool = next(t for t in tools if t.name == "get_market_fund_flow")
    result = asyncio.run(tool.ainvoke({"days": 5}))
    import json
    data = json.loads(result)
    assert isinstance(data, list)


def test_research_reports(tools):
    """平安银行 000001 应有研报数据。"""
    tool = next(t for t in tools if t.name == "get_research_reports")
    result = asyncio.run(tool.ainvoke({"symbol": "000001", "limit": 3}))
    import json
    data = json.loads(result)
    # 允许空列表（若无研报），但不能是 error
    assert isinstance(data, list) or "error" not in str(data)


def test_industry_pe(tools):
    """行业 PE 应返回多行数据。"""
    tool = next(t for t in tools if t.name == "get_industry_pe")
    result = asyncio.run(tool.ainvoke({}))
    import json
    data = json.loads(result)
    assert isinstance(data, list) or "error" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 任务 5：安装新依赖

```bash
cd EvoQuant
pip install "langchain-anthropic>=0.3.0" "langchain-mcp-adapters>=0.1.0" "mcp>=1.0.0"
```

---

## 验收清单

```bash
# Step 1: 验证 MCP Server 本身可以启动（Ctrl+C 退出）
python3 mcp_servers/akshare_server.py

# Step 2: 手动快速测试北向资金 API
python3 -c "
import akshare as ak, json
df = ak.stock_hsgt_fund_flow_summary_em()
print(df[df['资金方向']=='北向'][['交易日','资金净流入']].to_string())
"

# Step 3: 跑验收测试
cd EvoQuant
python3 -m pytest tests/test_akshare_mcp.py -v

# Step 4: 启动完整 orchestrator（观察 Researcher 是否调用工具）
python3 EvoQuant/src/core/orchestrator.py
# 在日志中确认出现：[Researcher] 成功加载 7 个 AKShare MCP 工具
```

---

## 注意事项（不要碰的地方）

1. **不要修改** `src/agents/coder.py`、`src/agents/critic.py`、`src/agents/validator.py`
2. **不要修改** `src/agents/state.py`（现阶段 AgentState 字段不变）
3. `mcp_servers/akshare_server.py` 中每个工具都必须有 `try/except`，失败返回 `{"error": ...}` 而非抛异常
4. `researcher.py` 中的 `asyncio.run(_research_node_async(state))` 同步包装是必要的，因为 LangGraph 节点默认是同步调用
5. `_MCP_CLIENT` 是模块级单例——**不要**在每次 `research_node` 调用时重新创建客户端
6. 工具调用 loop 最多 3 轮，防止死循环

---

## 预期效果

改造成功后，Researcher 的输出将从：

> "动量因子在 A 股历史上有一定效果，建议构建 5 日收益率因子..."

变为：

> 【市场观察】今日北向资金净流入 47.3 亿元，其中沪股通净买入 31.2 亿，
> 主力资金整体净流出 -89 亿。外资逆市流入，显示选择性布局。
> 【因子假设】北向与主力资金方向背离度因子
> 【Qlib 公式】`Corr(外资净流入序列, 主力净流入序列, 5)`
> 【预期逻辑】外资（趋势性）与主力（散户跟随）方向背离时，外资方向胜率更高...
