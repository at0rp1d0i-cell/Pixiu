<!-- SKILL:MARKET_ANALYST_CONTEXT_FRAMING -->

# MarketAnalyst 上下文构建规范

> Type B — 永久注入。指导 MarketAnalyst 从 MCP 工具数据生成结构化 MarketContextMemo。

---

## 1. Regime 判定标准

从价量数据提炼 regime 信号时，使用以下判定框架：

### 趋势型（trending_up / trending_down）
- 沪深300 20日均线方向一致（斜率 > 0 或 < 0）
- 近 10 个交易日中 ≥ 7 日收盘价在 20 日均线同侧
- 成交额 10 日均值相对 60 日均值放大 > 20%

### 震荡型（range_bound）
- 沪深300 近 20 日最高与最低价差 / 均价 < 5%
- 20 日均线斜率绝对值 < 0.1%
- 多空信号矛盾（如量能放大但价格不突破）

### 高波动（high_volatility）
- 近 10 日已实现波动率 > 近 60 日波动率的 1.5 倍
- 单日涨跌幅 > 2% 的天数 ≥ 3（近 10 日）
- 涨跌停家数异常（单日 > 50 家）

---

## 2. 融资融券到 market_sentiment 的映射

| 信号 | sentiment 判定 |
|------|---------------|
| 融资余额连续 5 日上升 + 融资买入额 > 近 20 日均值 1.2x | bullish |
| 融资余额连续 5 日下降 + 融券余额上升 | bearish |
| 融资融券余额均平稳 | neutral |
| 融资暴增但股价滞涨 | cautious（潜在见顶） |

---

## 3. 新闻 / 公告归类标准

### policy_signal（政策信号）
- 央行货币政策操作（MLF / LPR / 降准降息）
- 证监会 / 交易所规则变更
- 国务院经济会议定调

### sector_rotation（行业轮动）
- 行业 ETF 资金净流入 / 流出排名变化
- 板块领涨 / 领跌切换（近 5 日 vs 近 20 日）
- 产业政策定向扶持（如新能源补贴、半导体国产替代）

### event_driven（事件驱动）
- 财报季集中发布（1/4/7/10 月）
- 大股东增减持公告
- 重大资产重组 / 并购
- 外部冲击（地缘、贸易摩擦、汇率异动）

---

## 4. MarketContextMemo 字段填写优先级

1. **market_regime**（必填）— 使用上述判定标准，不可留空
2. **raw_summary**（必填）— 200 字以内的今日市场概要
3. **suggested_islands**（必填）— 根据 regime 和板块轮动建议 2-4 个 island
4. **key_signals**（推荐）— 提取 3-5 个具体信号点

### suggested_islands 推荐逻辑

| Regime | 优先推荐 Island |
|--------|----------------|
| trending_up | momentum, northbound |
| trending_down | volatility, sentiment |
| range_bound | valuation, volume |
| high_volatility | volatility, sentiment, momentum |

---

*最后更新：2026-03-19*
