# Data Source Expansion Roadmap
Purpose: Hold future-facing data expansion routes that are not part of the current active data-layer truth.
Status: planned
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

## 1. Scope

本文承接的是 `docs/design/15_data-sources.md` 不再保留在 active design 层中的内容：

- AKShare MCP 扩展
- Tushare Pro 基本面接入
- 新闻/搜索工具扩展
- `.env` 扩展模板
- 实施顺序建议

这些内容仍然重要，但属于未来实施路线，而不是当前运行时真相。

## 2. AKShare MCP 扩展方向

值得保留的扩展方向：

- 个股财务摘要
- 宏观经济指标
- 融资融券数据

这些工具更适合作为 `MarketAnalyst` 的可用数据面，而不是当前 `AlphaResearcher` 的直接能力前提。

## 3. Tushare 基本面接入

当前代码库里还没有 `src/data_pipeline/fetch_fundamentals.py`。

如果未来接入 Tushare，建议：

- 以独立基本面采集模块落地
- 按公告日 point-in-time 对齐
- 与现有 `parquet_staging` 数据合并
- 在 `format_to_qlib.py` 中读取扩展后的 full parquet

推荐扩展字段：

- `$pe_ttm`
- `$pb`
- `$ps_ttm`
- `$roe`
- `$revenue_yoy`
- `$profit_yoy`
- `$turnover_rate`
- `$float_mv`

## 4. 新闻/搜索工具扩展

旧 `news_sentiment_spider.py` 路线已经退出当前代码库。

如果未来补新闻搜索能力，建议直接走 MCP / search tool 路线，而不是恢复旧脚本。

保留方向：

- Tavily 搜索工具
- 公告/政策/财经新闻统一搜索接口
- Stage 1 消费优先，Stage 2 直连在 Researcher 工具化之后再开放

## 5. Environment and Order

未来如果推进这些路线，可考虑补充：

```bash
TUSHARE_TOKEN=""
TAVILY_API_KEY=""
```

建议顺序：

1. 先做 AKShare MCP 扩展
2. 再做搜索/新闻工具
3. 最后做 Tushare 基本面入库
