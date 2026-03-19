# Pixiu v2 数据层规格
Purpose: Describe the current Pixiu data layers, what is actually available today, and where future expansion belongs.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.1
> 前置依赖：`11_interface-contracts.md`

---

## 1. Design Goal

Pixiu 的数据层要同时满足两件事：

- 给 Stage 1/2 足够丰富的上下文，扩大 hypothesis space
- 不把未经 point-in-time 处理的上下文信号直接塞回回测层

因此这里最重要的不是“接多少源”，而是区分清楚：

- 哪些数据已经进入当前运行时
- 哪些数据只是 Agent 上下文
- 哪些数据仍属于未来扩展路线

## 2. Data Layers

### Layer 1: 回测直接读取层

用途：

- Qlib 回测直接消费
- 需要稳定、结构化、可 point-in-time 对齐

当前主路径：

- `data/qlib_bin/`
- 由现有数据下载与格式化流程产出

当前稳定字段：

```text
$open, $high, $low, $close, $volume, $factor, $amount
```

### Layer 2: Agent 上下文层

用途：

- Stage 1 和部分上游认知层消费
- 影响假设生成方向，但默认不直接进入回测公式

当前主路径：

- AKShare MCP
- cross-market MCP
- `MarketContextMemo`

### Layer 3: 扩展结构化字段层

用途：

- 未来将基本面等字段 point-in-time 对齐后写入回测层

当前状态：

- 部分 staging 已存在
- `fina_indicator` / `daily_basic` → Qlib bins 正在收口
- 运行时字段可用性不再只看设计文档，而要看本地 `qlib_bin/features/**` 的真实覆盖率

### Layer 4: 新闻/叙事搜索层

用途：

- 为 Stage 1/2 提供新闻、公告、叙事上下文

当前状态：

- 属于未来扩展
- 不应被误解为当前稳定运行时能力

## 3. Current Runtime Truth

### 3.1 当前已经成立的事实

- 回测层仍以价量字段为主
- Stage 1 可以消费 MCP 数据源形成 `MarketContextMemo`
- Stage 2 当前主要通过 `MarketContextMemo` 间接消费新增数据
- `AlphaResearcher` 还没有直接的 MCP / tool access

### 3.2 当前最重要的约束

- 所有进入回测层的数据都必须满足 point-in-time 对齐
- Agent 上下文层信号默认不直接进入回测公式
- 数据源扩展优先服务 Stage 1/2，不应把“智能”推回执行层
- Stage 2/3 的字段白名单应派生自本地 feature store 的真实能力，而不是手写在 prompt/skills 中

## 4. Coverage Snapshot

| Island | 当前可依赖数据 | 备注 |
|---|---|---|
| momentum | 价量完整 | 当前最稳定 |
| volatility | 价量完整 | 当前最稳定 |
| volume | 价量完整 | 当前最稳定 |
| northbound | 价量代理 | 更丰富特征仍待补 |
| valuation | 价格均值回归代理 | 基本面入库后会明显增强 |
| sentiment / narrative | 上下文有限 | 新闻、公告、叙事数据仍待扩展 |

## 5. Future Work Boundary

以下内容不再放在 active design 层里，而是进入 futures：

- AKShare MCP 进一步扩展
- Tushare 基本面入库
- 新闻/搜索工具扩展
- `.env` 扩展模板
- 数据源扩展实施顺序

对应文档：

- `docs/futures/data-source-expansion-roadmap.md`

如果你要实际准备本地数据，而不是只看设计边界：

- `docs/reference/data-download-guide.md`
