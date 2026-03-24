# 2026-03-24 A-Share Validation Protocol V1 Design

## Status

Proposed

## Why Now

Pixiu 当前主线已经从“实验是否能跑”推进到“实验结果是否可信”。

现有 runtime 已经有两条基础防线：

- `Stage 3` 对明显未来数据引用做 hard gate
- `Stage 4` 用 `T` 日信号配 `T+1` 收益，避免同日循环测量

但这还不够。当前更大的风险不是直接 future leakage，而是：

- 单一回测窗内高吞吐试错带来的 `IS selection bias`
- 大量候选带来的 `multiple testing / false discovery`
- A 股真实交易制度尚未进入正式验证协议
- 非 PIT 字段未来若进入正式回测路径，会带来“发布日期幽灵”

因此，Pixiu 现在最该补的不是更复杂的 `CPCV/purged CV`，而是：

- `强制 OOS promote 协议`
- `A 股可交易性约束`
- `PIT 边界`

## Design Goal

Validation Protocol V1 只回答一个问题：

`什么样的研究对象，才有资格从 candidate 进入正式通过池。`

V1 不追求一次性解决全部统计偏差。它先把当前高吞吐实验系统从“只看 IS 回测”提升到“有正式 promote 协议的研究系统”。

## Non-Goals

V1 暂不做：

- `purged CV / embargo / CPCV`
- DSR / Harvey-Liu haircut 作为最终裁决器
- 全市场复杂交易冲击模型
- 公告/财报类字段的完整 PIT 数据工程
- 跨所有子空间的一次性验证框架重写

这些属于后续 `v2/v3`。

## Core Decision

### 1. Promote 语义改变

当前 Pixiu 不应继续默认：

`IS pass -> promote`

V1 改为：

- `IS pass -> candidate`
- `OOS pass -> promote`

也就是说，任何没有经过 OOS 的候选，不进入正式通过池。

### 2. Validation split

每个候选必须至少经历两个窗：

- `discovery / calibration window`
- `holdout OOS window`

V1 推荐默认：

- discovery: 5-8 年滚动历史
- OOS: discovery 之后连续 12 个月

### 3. Walk-forward first

V1 不做传统 k-fold，而做最小 `walk-forward`：

- `discovery -> next-year OOS`
- 多个滚动起点重复

这比复杂 CV 更符合 Pixiu 当前公式发现主线。

## A-Share Execution Realism

V1 必须把 A 股执行约束正式写进验证协议：

- `T+1`
- `涨跌停`
- `停牌`
- `ST / 风险警示 / 退市整理`
- `survivorship bias`
- `历史指数成分股`

### Required reporting fields

至少在 Stage 4/5 报告中记录：

- 因涨跌停无法成交的比例
- 因停牌无法调仓的比例
- universe 覆盖率
- 可成交覆盖率

V1 的目标不是先做到完美执行仿真，而是让报告显式暴露这些风险，而不是继续假装它们不存在。

## PIT Boundary

V1 对字段做三层分级。

### Layer A: Stage 1 enrichment only

这类字段可以进入研究上下文，但默认不能直接进入正式 promote 回测路径：

- 热点榜 / 人气榜 / 题材热度
- 抓取型情绪数据
- 新闻/公告语义摘要
- 北向/主题/板块类非 PIT 审计字段

### Layer B: Stage 2 research-safe candidates

这类字段可以进入 hypothesis space，但仍需区分是否允许进入 Stage 4 正式回测：

- 日频价量字段
- 已知逐日可得的技术代理
- 已完成点时一致性确认的市场级资金面代理

### Layer C: Stage 4 formal-backtest forbidden until PIT

以下字段在未完成 PIT / 发布日期审计前，禁止进入正式 promote 路径：

- 财报类字段
- 公告发布日期敏感字段
- 任何“报告期存在，但市场当日是否已知不明确”的字段
- 任何抓取站点日后补录、口径漂移明显的数据

## A-Share Field And Signal Layering Audit

参考 `myhhub/stock` 的价值不在于接代码，而在于它提供了一张很实用的 A 股字段面地图。

Pixiu 需要单独产出一份 `A 股字段与信号分层审计`，把现有和候选字段映射到：

- `Stage 1 enrichment only`
- `Stage 2 research-safe candidates`
- `Stage 4 formal-backtest forbidden until PIT`

这份审计的目标是：

- 避免 enrichment 数据偷偷滑进正式验证
- 为后续 `mechanism -> proxy -> formula` 建立可用字段边界
- 避免因字段口径不明而引入 future-data ghost

### Immediate candidates from current system

优先审计：

- 价量基础字段
- 北向/资金流代理
- 板块/题材热度
- 基本面扩展字段
- 公告/新闻类结构化代理

## Runtime Surface Changes

### Stage 4

需要新增最小验证对象或字段，至少表达：

- `discovery_start`
- `discovery_end`
- `oos_start`
- `oos_end`
- `oos_metrics`
- `is_oos_passed`
- `is_oos_degradation`

### Stage 5

Judgment / pool promotion 语义需要改成：

- `IS only -> candidate`
- `IS + OOS pass -> promote`
- `OOS fail / degradation large -> archive or observe`

### Factor pool

正式池与候选池的语义必须分开。

最小上可以先不拆物理库，但逻辑上至少要分：

- `candidate`
- `promoted`

## Metrics To Record

V1 每轮实验至少记录：

- tested candidates count
- delivered to Stage 4 count
- IS passed count
- OOS passed count
- IS/OOS degradation
- family-level crowding / repeated family discovery

这几项是后续 DSR、multiple-testing 控制、family reward 的基础。

## Interaction With Current Stage 2 Mainline

Validation V1 不替代当前 `Stage 2` 收敛工作，但会改变“什么结果值得继续优化”的标准。

当前主线顺序应为：

1. 继续收 `factor_algebra` collapse
2. 收 `cross_market / narrative_mining` grounding
3. 同时落地 Validation Protocol V1

否则即使 Stage 2 生成更好，系统仍可能在不可信的验证协议上积累“假资产”。

## V2 / V3 Evolution

### V2

- 正式 `OOSReport`
- Stage 5 联合使用 `IS + OOS + degradation`
- 按 market regime 分层 OOS
- family-level occupancy / diversity reward

### V3

- `purged CV / embargo / CPCV`
- DSR / Harvey-Liu haircut
- PIT 审计表与发布日期校验
- 更真实的交易成本与冲击模型

## Recommended Implementation Order

1. 定义 `candidate vs promote` 语义
2. 给 Stage 4/5 增加最小 OOS 字段
3. 先落最小 walk-forward
4. 输出 `A 股字段与信号分层审计`
5. 再决定是否扩大到更复杂 CV

## Acceptance Criteria

Validation Protocol V1 落地后，应满足：

- 没有 OOS 的对象不能正式 promote
- A 股执行约束在报告中显式可见
- 非 PIT 字段不能默认进入正式 promote 回测
- Pixiu 能回答“这个因子为何被 promote，而不是只是 IS 偶然好看”
