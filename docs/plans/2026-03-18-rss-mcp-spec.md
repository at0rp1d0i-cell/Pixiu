# RSS MCP Server 规格文档

Status: active
Owner: coordinator
Last Reviewed: 2026-03-18

> 版本：v1.0 | 日期：2026-03-18 | 状态：待实现

---

## 0. 前置条件与依赖

### Phase 1（当前可实现）
RSS server 本体 + Stage 1 MarketAnalyst 消费。
具体改动：在 `src/agents/market_analyst.py` 的 `MultiServerMCPClient` 配置中注册 `rss_server.py`。

### Phase 2（需 Researcher 架构升级后）
Stage 2 NARRATIVE_MINING 直接消费 RSS 工具，需要将 `AlphaResearcher`
从纯 LLM prompt 生成器升级为支持 MCP 工具调用的 ReAct agent。
当前 `src/agents/researcher.py` 使用 `llm.ainvoke()`，无 tool binding，不支持工具调用。
Stage 2 消费路径标注为：`planned`（依赖 Researcher 架构升级）

---

## 1. 定位与目标

### 1.1 定位

RSS MCP Server 是一个**轻量级、无状态的信息拉取工具集**，不是独立的持久化服务。它与现有 MCP 服务器并列，文件位置为 `mcp_servers/rss_server.py`。

在数据分层体系中，RSS/新闻属于 **Layer 4（Agent 上下文）**：仅注入 LLM prompt，不进入回测公式，不写入 Factor Pool。

### 1.2 与现有工具的互补关系

| 工具 | 类型 | 触发方式 | 适用场景 |
|------|------|----------|----------|
| Tavily（已有） | 主动语义搜索 | Agent 按需查询特定问题 | 已知议题的深度调研 |
| **RSS MCP（本文）** | 被动实时推送 | Agent 获取当前时间窗口内的最新动态 | 未知议题的市场扫描、政策监控 |
| Jina Reader（已有，cross_market_server） | 全文提取 | 按 URL 抓取 | 已有链接的内容补全 |

### 1.3 目标

当前直接目标有两个：

1. 为 Stage 1 的 `MarketAnalyst` 提供监管/政策/公告/财经新闻的当日上下文
2. 为未来 Stage 2 的工具化 Researcher 预留统一 RSS / 公告接口

需要明确的当前架构事实：

- `MarketAnalyst` 已有 `MultiServerMCPClient + bind_tools + tool_calls` 完整链路，可直接消费 MCP 工具
- `AlphaResearcher` 仍是纯 `llm.ainvoke()` 调用，没有 tool binding，也没有 ReAct 循环
- 因此“Stage 2 Researcher 按需调用 RSS 工具”是目标态，不是当前可立即落地路径

Stage 1 可直接复用 `fetch_rss_feed` 获取当日宏观动态，写入 `MarketContextMemo.raw_summary`；Stage 2 现阶段只能通过 `MarketContextMemo` 间接受益。

---

## 2. 候选数据源清单（实现前必须验证）

以下 6 个来源是当前候选集，不应视为“已验证可用的固定源”。

除新浪 JSON Roll API 的接口形态相对明确外，其余 5 个源都必须先做连通性/解析验证，再决定是否纳入默认内置源。

### 2.1 公告类（最高优先级）

| ID | 来源 | Feed URL | 类型 | 说明 |
|----|------|----------|------|------|
| `sse` | 上交所 | `http://www.sse.com.cn/disclosure/listedinfo/announcement/rss.xml` | Atom/RSS | 上市公司公告（信息披露） |
| `szse` | 深交所 | `http://www.szse.cn/api/disc/info/discInfoRss.xml` | RSS | 上市公司信息披露公告 |

> **待验证**：上述两个 feed URL 为官方披露接口，但可能需要在国内网络环境下访问，或受反爬限制。备选方案：通过 AKShare 的 `stock_notice_report` / `stock_gssy_report_em` 接口获取公告列表（已在 `akshare_server.py` 中有工程基础）。

### 2.2 监管类

| ID | 来源 | Feed URL | 类型 | 说明 |
|----|------|----------|------|------|
| `csrc` | 证监会 | `http://www.csrc.gov.cn/csrc/c101954/rss.xml` | RSS | 监管政策、行政处罚、规则制定 |
| `pboc` | 中国人民银行 | `http://www.pbc.gov.cn/rss/index.xml` | RSS | 货币政策、利率公告、公开市场操作 |

> **待验证**：CSRC 和 PBOC 的 RSS 地址在官方网站改版后可能已变更。备选方案：
> - CSRC：抓取 `https://www.csrc.gov.cn/csrc/c101954/common_list.shtml` 页面解析新闻列表
> - PBOC：`http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/index.html` 页面解析

### 2.3 财经媒体类

| ID | 来源 | Feed URL | 类型 | 说明 |
|----|------|----------|------|------|
| `sina` | 新浪财经 | `https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1&r=0.1` | JSON API（RSS 替代） | 财经要闻，实时更新 |
| `eastmoney` | 东方财富 | `https://rss.eastmoney.com/rss/news/2.xml` | RSS | 市场动态、个股资讯 |

> **说明**：新浪财经原 RSS（`rss.sina.com.cn`）已于 2023 年下线，上表使用其 JSON Roll API 作为等效替代，feedparser 无法解析，需在 `fetch_rss_feed` 中对 `sina` 单独处理。备选方案：`https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=1686` （另一财经频道）

**实现前验证要求**：在开始编码前，运行以下验证脚本确认可用源数量：
```python
import feedparser, httpx
SOURCES = SOURCE_MAP
for name, config in SOURCES.items():
    try:
        r = httpx.get(config["url"], timeout=10.0)
        if config.get("parser") == "json_sina":
            payload = r.json()
            count = len(payload.get("result", {}).get("data", []))
        else:
            parsed = feedparser.parse(r.text)
            count = len(parsed.entries)
        print(f"✅ {name}: {count} 条目")
    except Exception as e:
        print(f"❌ {name}: {e}")
```
如果可用源少于 3 个，重新评估实现价值后再继续。

---

## 3. 工具接口规格

### 3.1 工具 1：`fetch_rss_feed`

```python
@app.tool()
async def fetch_rss_feed(
    sources: list[str] | None = None,  # 指定来源 ID 子集，如 ["csrc", "pboc"]，None 表示全部
    max_items: int = 20,               # 每个源最多返回条目数
    since_hours: int = 24,             # 只返回最近 N 小时的条目
) -> str:
    """获取 A 股主要信息源的最新条目。

    返回各源最新条目，每条包含：标题、摘要（截断至 500 字）、链接、发布时间、来源 ID。
    单个 feed 失败不影响其他 feed，降级返回已成功获取的条目。
    """
```

**返回格式（JSON 字符串）：**

```json
{
  "fetched_at": "2026-03-18T10:00:00+08:00",
  "since_hours": 24,
  "total_items": 15,
  "sources_ok": ["csrc", "pboc", "eastmoney"],
  "sources_failed": ["sse"],
  "items": [
    {
      "source": "csrc",
      "title": "证监会发布XX规定",
      "summary": "摘要内容，最多500字...",
      "url": "http://www.csrc.gov.cn/...",
      "published_at": "2026-03-18T09:30:00+08:00"
    }
  ]
}
```

### 3.2 工具 2：`fetch_announcement`

```python
@app.tool()
async def fetch_announcement(
    symbol: str,          # 股票代码，如 "000001"（6位）
    max_items: int = 5,
) -> str:
    """获取指定股票的最新公告。

    fetch_announcement 使用 AKShare 的 stock_notice_report 接口（而非 RSS 过滤），
    直接按股票代码查询公告。交易所 RSS feed 是全量披露流，不支持按股票代码过滤。
    实现时调用：ak.stock_notice_report(symbol=symbol) 并截取最新 max_items 条。
    """
```

**返回格式（JSON 字符串）：**

```json
{
  "symbol": "000001",
  "exchange": "SZSE",
  "fetched_at": "2026-03-18T10:00:00+08:00",
  "items": [
    {
      "title": "平安银行关于XX的公告",
      "url": "http://www.szse.cn/...",
      "published_at": "2026-03-18T08:00:00+08:00"
    }
  ],
  "note": ""
}
```

### 3.3 工具 3：`fetch_full_article`

```python
@app.tool()
async def fetch_full_article(url: str) -> str:
    """用 Jina Reader 抓取文章全文，用于 RSS 摘要不足时补全内容。

    通过 https://r.jina.ai/{url} 获取 Markdown 格式全文，截断至 3000 字。
    无需 API key。适合在 NARRATIVE_MINING 子空间中对高价值条目做深度阅读。
    """
```

**返回格式（JSON 字符串）：**

```json
{
  "url": "https://original-article-url",
  "jina_url": "https://r.jina.ai/https://original-article-url",
  "content": "文章全文（Markdown），最多3000字...",
  "truncated": false
}
```

---

## 4. 实现要点

### 4.1 依赖

- 解析库：`feedparser`（标准 Python RSS/Atom 解析库，无其他新依赖）
- HTTP 客户端：`httpx`（项目已有，`cross_market_server.py` 中使用）
- 全文补全：Jina Reader API（`https://r.jina.ai/{url}`，无需 API key，与 `cross_market_server.py` 的做法一致）

### 4.2 去重

进程内用 `_seen_ids: set[str]` 缓存已返回的 entry id（使用 `feedparser` 的 `entry.id` 字段，回退到 `entry.link`）。同一进程生命周期内同一条目不重复返回。

### 4.3 时间过滤

`since_hours` 过滤逻辑：
1. 优先使用 `entry.published_parsed`（UTC struct_time）
2. 回退到 `entry.updated_parsed`
3. 若时间字段缺失，默认保留该条目（宁可多返回）

### 4.4 错误处理

```
单个 feed 失败（网络超时、解析错误）:
  → 记录 logger.warning，将该源 ID 加入 sources_failed
  → 继续处理其余 feed
  → 最终返回结构中 sources_failed 列出所有失败源
```

网络请求超时统一设置为 `timeout=10.0` 秒（与 `cross_market_server.py` 保持一致）。

### 4.5 字符限制

| 字段 | 限制 |
|------|------|
| 单条目 summary | 500 字（中文字符计） |
| fetch_full_article 全文 | 3000 字 |

### 4.6 新浪财经特殊处理

新浪财经使用 JSON Roll API，非标准 RSS，需单独解析：

```python
# sina 源特殊处理（伪代码）
resp = await client.get(SOURCES["sina"]["url"])
data = resp.json()
items = data["result"]["data"]
# 字段映射：title → title, intro → summary, url → url, ctime → published_at
```

---

## 5. 在 Pipeline 中的消费位置

| Stage | 消费者 | 工具 | 注入位置 | 状态 |
|-------|--------|------|----------|------|
| Stage 1 — Market Context | `MarketAnalyst` | `fetch_rss_feed(sources=["csrc","pboc","eastmoney"], since_hours=24)` | `MarketContextMemo.raw_summary` | 当前可直连 |
| Stage 2 — NARRATIVE_MINING | `AlphaResearcher` 工具化版本（planned） | `fetch_rss_feed` + `fetch_announcement(symbol)` | 叙事种子与 hypothesis context | planned（待 Researcher 升级后启用） |

**当前阶段**：Stage 1 MarketAnalyst 通过 `MultiServerMCPClient` 消费 RSS 工具，内容经 `MarketContextMemo` 间接影响 Stage 2。

**Stage 2 直连路径**：planned（待 Researcher 升级后启用）。升级完成后，Stage 2 再按需直连 RSS / 公告工具；RSS 内容仍只服务于当次 hypothesis 生成，不写入 Factor Pool，不参与回测。

---

## 6. 依赖与配置

### 6.1 新增依赖

```toml
# pyproject.toml
feedparser = ">=6.0"
```

无其他新依赖。`httpx` 已存在于项目依赖中。

### 6.2 无需配置项

- 无需 API key
- 无需环境变量
- 无需外部服务

### 6.3 文件位置

```
mcp_servers/
  rss_server.py       ← 新增，本规格的实现目标
  akshare_server.py   ← 已有
  chromadb_server.py  ← 已有
  cross_market_server.py ← 已有
```

服务器启动方式（与其他 MCP 服务器一致）：

```bash
python mcp_servers/rss_server.py
```

---

## 7. 测试规格

测试文件：`tests/test_rss_server.py`，标记 `@pytest.mark.unit`。

### 7.1 Smoke Test：返回格式验证

```python
@pytest.mark.unit
async def test_fetch_rss_feed_format(mock_feedparser):
    """mock feedparser，验证 fetch_rss_feed 返回 JSON 且包含必要字段"""
    result = json.loads(await fetch_rss_feed(sources=["csrc"], max_items=5, since_hours=24))
    assert "items" in result
    assert "sources_ok" in result
    assert "sources_failed" in result
    assert "fetched_at" in result
    for item in result["items"]:
        assert {"source", "title", "url", "published_at"}.issubset(item.keys())
```

### 7.2 时间过滤边界测试

```python
@pytest.mark.unit
async def test_since_hours_filter(mock_feedparser_with_old_entry):
    """since_hours=1 时，超过1小时的条目不应出现在结果中"""
    result = json.loads(await fetch_rss_feed(sources=["csrc"], max_items=10, since_hours=1))
    assert all(
        is_within_hours(item["published_at"], hours=1)
        for item in result["items"]
    )
```

### 7.3 单源失败不影响其他源

```python
@pytest.mark.unit
async def test_single_source_failure_isolation(mock_feedparser_sse_fails):
    """SSE feed 超时时，其他源正常返回，sources_failed 包含 'sse'"""
    result = json.loads(await fetch_rss_feed(sources=["sse", "csrc"], max_items=5, since_hours=24))
    assert "sse" in result["sources_failed"]
    assert "csrc" in result["sources_ok"]
    assert len(result["items"]) > 0
```

### 7.4 fetch_full_article 截断测试

```python
@pytest.mark.unit
async def test_fetch_full_article_truncation(mock_httpx_jina):
    """全文超过3000字时，content 被截断，truncated 为 True"""
    result = json.loads(await fetch_full_article("https://example.com/article"))
    assert len(result["content"]) <= 3000
    assert result["truncated"] is True
```

---

## 附录：数据源 URL 汇总

| ID | 名称 | URL | 状态 |
|----|------|-----|------|
| `sse` | 上交所 | `http://www.sse.com.cn/disclosure/listedinfo/announcement/rss.xml` | 待验证 |
| `szse` | 深交所 | `http://www.szse.cn/api/disc/info/discInfoRss.xml` | 待验证 |
| `csrc` | 证监会 | `http://www.csrc.gov.cn/csrc/c101954/rss.xml` | 待验证 |
| `pboc` | 央行 | `http://www.pbc.gov.cn/rss/index.xml` | 待验证 |
| `sina` | 新浪财经 | `https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1` | 可用（JSON API） |
| `eastmoney` | 东方财富 | `https://rss.eastmoney.com/rss/news/2.xml` | 待验证 |

> 实现时建议在启动时（或首次调用时）做一次 HEAD 请求验证各源可达性，不可达的源记入日志但不报错。
