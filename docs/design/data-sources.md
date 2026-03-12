# Pixiu v2 数据层规格

> 版本：2.0
> 创建：2026-03-08
> 前置依赖：`interface-contracts.md`

---

## 1. 设计原则

### 1.1 数据分层

```
Layer 1: 价格/成交量（Qlib bin，回测引擎直接读取）
Layer 2: 实时市场信号（AKShare MCP，Agent 上下文）
Layer 3: 基本面字段（Tushare → Qlib bin 扩展，可选）
Layer 4: 情绪/新闻（Tavily / AKShare 研报，Agent 上下文）
```

- **Layer 1/3** 写入 `data/qlib_bin/`，供 Qlib 回测引擎读取
- **Layer 2/4** 通过 MCP Server 工具调用，仅供 Agent 生成假设时使用，不进入回测公式（除非扩展 Layer 3）
- **防前视偏差原则**：所有数据对齐必须使用 point-in-time 口径（财报发布日，而非报告期末）

### 1.2 当前可用字段（Qlib 回测层）

```
$open, $high, $low, $close, $volume, $factor
$amount（由 format_to_qlib.py 生成）
```

### 1.3 扩展字段（路线B，Tushare 接入后）

```
$pe_ttm, $pb, $ps_ttm     ← 估值
$roe_ttm, $roa_ttm         ← 盈利质量
$revenue_yoy, $profit_yoy  ← 成长
$turnover_rate             ← 换手率（日线，用于 volume island）
$float_mv                  ← 流通市值（规模因子）
$analyst_count             ← 券商覆盖数（关注度代理）
```

---

## 2. 任务 A：AKShare MCP Server 扩展（无需申请，直接执行）

### 文件位置：`mcp_servers/akshare_server.py`

在现有 7 个工具基础上，新增以下工具（追加到文件末尾，不修改现有工具）：

---

### 工具 8：个股财务摘要

```python
@app.tool()
async def get_stock_financial_summary(symbol: str) -> str:
    """获取个股最新财务摘要（TTM口径）。

    Args:
        symbol: 股票代码，如 '000001'。

    返回字段：股票代码、总资产、净资产、营业收入、净利润、
    摊薄净资产收益率(ROE)、市盈率(PE-TTM)、市净率(PB)、
    每股收益(EPS)、营收同比增速、净利润同比增速。
    用途：基本面 valuation island 的核心输入，估计因子经济逻辑。
    注意：数据约有1个季度的滞后（财报发布延迟）。
    """
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按年度")
        if df is None or df.empty:
            return json.dumps({"error": f"No financial data for {symbol}"}, ensure_ascii=False)
        # 取最近2条记录
        result = df.head(2).to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_stock_financial_summary failed for %s: %s", symbol, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
```

---

### 工具 9：宏观经济指标

```python
@app.tool()
async def get_macro_indicators() -> str:
    """获取中国主要宏观经济指标最新值。

    返回内容：
    - 制造业PMI（最近6个月）
    - M2货币供应量同比（最近3个月）
    - CPI同比（最近3个月）

    用途：Stage 1 MarketAnalyst 判断宏观 regime，
    辅助 valuation island 判断估值扩张/收缩周期。
    """
    try:
        result = {}

        # 制造业PMI
        try:
            pmi_df = ak.macro_china_pmi_yearly()
            result["pmi_manufacturing"] = pmi_df.tail(6).to_dict(orient="records")
        except Exception as e:
            result["pmi_manufacturing"] = {"error": str(e)}

        # M2
        try:
            m2_df = ak.macro_china_m2_yearly()
            result["m2_yoy"] = m2_df.tail(3).to_dict(orient="records")
        except Exception as e:
            result["m2_yoy"] = {"error": str(e)}

        # CPI
        try:
            cpi_df = ak.macro_china_cpi_yearly()
            result["cpi_yoy"] = cpi_df.tail(3).to_dict(orient="records")
        except Exception as e:
            result["cpi_yoy"] = {"error": str(e)}

        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_macro_indicators failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
```

---

### 工具 10：融资融券数据

```python
@app.tool()
async def get_margin_trading_summary(days: int = 10) -> str:
    """获取全市场融资融券汇总数据（最近N个交易日）。

    Args:
        days: 返回最近多少个交易日，默认 10，最大 30。

    返回字段：日期、融资余额、融资买入额、融券余量、
    融券卖出量、融资融券余额。
    用途：判断市场杠杆水平和情绪；高融资余额 + 下跌 = 踩踏信号，
    构建情绪/动量 Island 的杠杆风险因子。
    """
    try:
        days = min(max(days, 1), 30)
        df = ak.stock_margin_account_info()
        if df is None or df.empty:
            return json.dumps({"error": "No margin data available"}, ensure_ascii=False)
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_margin_trading_summary failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
```

---

### 注意事项

- `ak.stock_financial_abstract_ths()` 的 `indicator` 参数在不同版本 AKShare 可能不同，若报错尝试去掉该参数
- 宏观数据接口名称在不同 AKShare 版本可能有变化（`macro_china_pmi_yearly` vs `macro_china_pmi_manufacturing`），调用前用 `dir(ak)` 检查可用接口
- 工具 8-10 全部对 `MarketAnalyst` 开放，不对 `AlphaResearcher` 直接开放（Researcher 通过 MarketContextMemo 间接获得宏观信号）

---

## 3. 任务 B：Tushare Pro 接入（路线 B，需有 Token 后执行）

### 3.1 申请方式

1. 访问 https://tushare.pro 注册账号
2. 实名认证后获得免费积分（约 2000 积分）
3. 将 Token 写入 `.env`：`TUSHARE_TOKEN=your_token_here`

### 3.2 新增文件：`src/data_pipeline/fetch_fundamentals.py`

**职责**：从 Tushare 拉取个股财务数据，对齐到日线，扩展 Qlib bin 字段。

```python
"""
从 Tushare Pro 获取基本面数据并对齐到日线频率。
输出：data/parquet_staging/{SYMBOL}_fundamentals.parquet
注意：使用 point-in-time 对齐（公告日 ann_date，而非报告期 period）
"""
import tushare as ts
import pandas as pd
import os

TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

# 目标字段（Qlib 扩展字段名）
FUNDAMENTAL_FIELDS = [
    "pe_ttm",       # 市盈率 TTM
    "pb",           # 市净率
    "ps_ttm",       # 市销率 TTM
    "roe",          # 净资产收益率
    "revenue_yoy",  # 营收同比
    "profit_yoy",   # 净利润同比
    "turnover_rate",# 换手率
    "float_mv",     # 流通市值（对数化后用）
]
```

**对齐逻辑**（关键，防前视）：
1. 财报数据按 `ann_date`（公告日）对齐，而非 `end_date`（报告期末）
2. 用 `forward-fill` 将季度数据填充到日线（直到下一次公告日才更新）
3. 与 `data/parquet_staging/{SYMBOL}.parquet` 合并，输出 `{SYMBOL}_full.parquet`
4. `format_to_qlib.py` 修改为读取 `_full.parquet`（若存在）

### 3.3 修改：`knowledge/skills/constraints/qlib_formula_syntax.md`

接入后，在合法字段列表末尾追加：

```markdown
## 扩展基本面字段（需 Tushare 接入后方可使用）
- $pe_ttm       ← 市盈率 TTM（注意：停牌/亏损时为 NaN，使用时加 IsNan 保护）
- $pb           ← 市净率（注意：PB < 0 表示资不抵债，需过滤）
- $roe          ← 净资产收益率 TTM（季度对齐，非日线高频）
- $revenue_yoy  ← 营收同比增速（%，季度对齐）
- $profit_yoy   ← 净利润同比增速（%，季度对齐，注意低基数效应）
- $turnover_rate← 换手率（%，日线频率）
- $float_mv     ← 流通市值（元，建议取对数：Log($float_mv + 1)）
```

---

## 4. 任务 C：新闻情绪管线修复（路线 B+，可选）

**现状**：`src/data_pipeline/news_sentiment_spider.py` 有硬编码代理和 API Key（见 `../plans/engineering-debt.md` C1/H3 条目），RSS 爬虫逻辑不完整。

**替代方案**：用 Tavily 替换。

### 申请方式
访问 https://app.tavily.com 注册，获得 API Key，写入 `.env`：
```
TAVILY_API_KEY=tvly-your_key_here
```

### 新增 MCP 工具（追加到 `akshare_server.py` 或新建 `tavily_server.py`）

```python
@app.tool()
async def search_market_news(query: str, max_results: int = 5) -> str:
    """用 Tavily 搜索最新财经新闻。

    Args:
        query: 搜索词，如 '沪深300 资金流入' 或 '新能源 政策'。
        max_results: 返回条数，默认 5，最大 10。

    返回字段：标题、URL、摘要、发布时间、内容片段。
    用途：MarketAnalyst 获取实时新闻上下文；
    替代 news_sentiment_spider.py 的 RSS 功能。
    """
    import httpx
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if not tavily_key:
        return json.dumps({"error": "TAVILY_API_KEY not set"}, ensure_ascii=False)

    try:
        max_results = min(max(max_results, 1), 10)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            simplified = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content", "")[:300],
                    "published_date": r.get("published_date"),
                }
                for r in results
            ]
            return json.dumps(simplified, ensure_ascii=False)
    except Exception as e:
        logger.error("search_market_news failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
```

**同时删除** `src/data_pipeline/news_sentiment_spider.py`（该文件含硬编码凭证，已在 `../plans/engineering-debt.md` C1 标记）。

---

## 5. 数据充分性总结

| Island | 路线A（纯价量） | 路线B（+Tushare） |
|--------|--------------|-----------------|
| momentum | ✅ 完整 | ✅ 完整 |
| volatility | ✅ 完整 | ✅ 完整 |
| volume | ✅ 完整 | ✅ 完整 |
| northbound | ⚠️ 价量代理 | ⚠️ 价量代理（北向持仓无日线公开数据） |
| valuation | ⚠️ 价格均值回归代理 | ✅ PE/PB/ROE 完整 |
| sentiment | ⚠️ 研报频率代理 | ✅ +Tavily 新闻 |

**执行建议**：优先完成任务 A（无需任何申请，30分钟内完成），任务 B/C 在 Tushare Token 到位后执行。

---

## 6. `.env` 模板追加

在现有 `.env` 末尾补充以下配置项：

```bash
# ── 数据源 ─────────────────────────────────
TUSHARE_TOKEN=""          # Tushare Pro token（任务B必须）
TAVILY_API_KEY=""         # Tavily 新闻搜索（任务C可选）
```

---

## 7. 实施顺序

1. **任务 A**（立即执行）：在 `akshare_server.py` 末尾追加工具 8-10
2. **任务 C**（有 Tavily Key 后）：追加 `search_market_news` 工具，删除 `news_sentiment_spider.py`
3. **任务 B**（有 Tushare Token 后）：新建 `fetch_fundamentals.py`，修改 `format_to_qlib.py`，更新 Skills 文档
