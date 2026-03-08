# Pixiu v2 Stage 1：市场上下文层规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_interface_contracts.md`
> 文件位置：`src/agents/market_analyst.py`、`src/agents/literature_miner.py`（新建）

---

## 1. 两个 Agent

### MarketAnalyst

**职责**：整合 AKShare 实时数据 + 新闻 RSS，生成今日市场上下文。

**工具（MCP）**：复用现有 `akshare_server.py` 的全部 7 个工具：
- `get_northbound_flow_today`
- `get_northbound_holdings`
- `get_sector_pe_ratios`
- `get_hot_money_flow`
- `get_individual_stock_fund_flow`
- `get_broker_research_reports`
- `get_market_news`

```python
# src/agents/market_analyst.py

MARKET_ANALYST_PROMPT = """你是 EvoQuant 的市场分析师，负责每日开盘前生成市场上下文备忘录。

今天的日期：{today}

你需要：
1. 调用工具获取北向资金、热门板块、宏观信号
2. 判断当前市场 regime（trending_up/trending_down/sideways/volatile）
3. 基于数据推断哪些 Island 方向本轮最值得探索
4. 输出一份简洁的 MarketContextMemo JSON

Island 选项：momentum（动量）、northbound（北向资金）、
valuation（估值）、volatility（波动率）、volume（量价）、sentiment（情绪）

必须以合法的 JSON 输出，格式见 MarketContextMemo schema。
不需要解释，直接输出 JSON。"""

class MarketAnalyst:
    def __init__(self, mcp_tools: list):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.1,
        ).bind_tools(mcp_tools)
        self.tools = {t.name: t for t in mcp_tools}

    async def analyze(self) -> MarketContextMemo:
        messages = [
            SystemMessage(content=MARKET_ANALYST_PROMPT.format(today=today_str())),
            HumanMessage(content="请生成今日市场上下文备忘录。"),
        ]

        # ReAct 循环（最多 5 轮工具调用）
        for _ in range(5):
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break

            for call in response.tool_calls:
                tool_result = await self.tools[call["name"]].ainvoke(call["args"])
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=call["id"]))

        # 解析最终 JSON 输出
        return self._parse_memo(response.content)

    def _parse_memo(self, content: str) -> MarketContextMemo:
        import json, re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return MarketContextMemo(**data)
        # 降级：返回空 memo
        return MarketContextMemo(
            date=today_str(),
            northbound=None,
            macro_signals=[],
            hot_themes=[],
            historical_insights=[],
            suggested_islands=["momentum"],
            market_regime="sideways",
            raw_summary="MarketAnalyst 解析失败，使用空上下文",
        )
```

---

### LiteratureMiner

**职责**：从 FactorPool 检索各 Island 的历史优秀因子和常见失败模式，为 Researcher 提供参考。

**工具（MCP）**：复用现有 `chromadb_server.py` 的全部 4 个工具：
- `get_island_best_factors`
- `get_similar_failures`
- `get_factor_leaderboard`
- `get_global_statistics`

```python
# src/agents/literature_miner.py

class LiteratureMiner:
    """
    不需要 LLM，直接调用 FactorPool API 生成结构化摘要。
    """
    def __init__(self, factor_pool: FactorPool):
        self.pool = factor_pool

    async def retrieve_insights(
        self,
        active_islands: list[str],
    ) -> list[HistoricalInsight]:
        insights = []
        for island in active_islands:
            top = self.pool.get_island_best_factors(island=island, limit=3)
            failures = self.pool.get_common_failure_modes(island=island, limit=5)

            if not top:
                # 该 Island 尚无历史数据
                insights.append(HistoricalInsight(
                    island=island,
                    best_factor_formula="（无历史记录）",
                    best_sharpe=0.0,
                    common_failure_modes=[],
                    suggested_directions=["从基础动量因子开始探索"],
                ))
                continue

            best = top[0]
            insights.append(HistoricalInsight(
                island=island,
                best_factor_formula=best["formula"],
                best_sharpe=best["sharpe"],
                common_failure_modes=[f["failure_mode"] for f in failures],
                suggested_directions=self._infer_directions(top, failures),
            ))

        return insights

    def _infer_directions(self, top_factors, failure_modes) -> list[str]:
        """
        基于历史最优因子和失败模式，推断本轮建议方向。
        规则：
        - 如果 high_turnover 是常见失败 → 建议增大时间窗口
        - 如果 low_ic 是常见失败 → 建议换信号类型
        - 如果历史最优 Sharpe > 3.0 → 建议在此方向深化
        """
        suggestions = []
        failure_types = [f["failure_mode"] for f in failure_modes]

        if "high_turnover" in failure_types:
            suggestions.append("增大时间窗口参数（如 Mean(x,5) → Mean(x,20)）")
        if "low_ic" in failure_types:
            suggestions.append("尝试换用不同类型的信号（量价/资金流/情绪等）")
        if top_factors and top_factors[0].get("sharpe", 0) > 3.0:
            suggestions.append(f"在已有最优因子基础上组合变体：{top_factors[0]['formula'][:60]}")
        if not suggestions:
            suggestions.append("当前方向进展正常，继续探索")

        return suggestions[:3]
```

---

## 2. 降级策略

Stage 1 是辅助上下文，不是必需的。如果 MCP 调用失败或超时：

```python
# Orchestrator 中的 market_context_node 降级逻辑
try:
    memo = await analyst.analyze()
except Exception as e:
    logger.warning(f"MarketAnalyst 失败，使用空上下文：{e}")
    memo = MarketContextMemo(
        date=today_str(),
        northbound=None,
        macro_signals=[],
        hot_themes=[],
        historical_insights=await miner.retrieve_insights(ACTIVE_ISLANDS),  # FactorPool 查询不依赖外网，通常可用
        suggested_islands=ACTIVE_ISLANDS,
        market_regime="unknown",
        raw_summary="市场数据获取失败，仅使用历史 FactorPool 上下文",
    )
```

---

## 3. 测试要求

新建 `tests/test_market_context.py`：

```python
def test_market_analyst_empty_fallback():
    """MCP 工具全部失败时应返回合法的空 MarketContextMemo"""

def test_literature_miner_empty_pool():
    """FactorPool 为空时应返回提示性 HistoricalInsight，不报错"""

def test_literature_miner_direction_inference():
    """high_turnover 失败模式应推断出增大时间窗口的建议"""
```
