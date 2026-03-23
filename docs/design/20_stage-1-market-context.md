# Pixiu v2 Stage 1：市场上下文层规格
Purpose: Define the Stage 1 market-context boundary, its two-layer execution model, and the signals that are allowed to influence downstream stages.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-22

> 版本：2.1
> 创建：2026-03-07
> 前置依赖：`11_interface-contracts.md`
> 文件位置：`src/agents/market_analyst.py`、`src/core/orchestrator/nodes/stage1.py`

---

## 1. 职责

Stage 1 的职责不是“尽可能多抓市场信息”，而是：

- 为当前轮生成可消费的 `MarketContextMemo`
- 提供足以支持 regime 判断和探索方向选择的市场级上下文
- 在不拖垮实验有效性的前提下，为下游提供可追溯的上下文输入

Stage 1 是上下文层，不是大而全的资讯抓取层。

---

## 2. 双层模型

Stage 1 采用两层执行模型：

### Blocking Core Context

当前轮必须拿到的最小上下文集合。

要求：

- 稳定、低延迟、市场级
- 只包含当前轮真的需要的 regime / 风险偏好信号
- 失败会直接影响实验有效性

当前推荐的 blocking core 范围：

- 交易日 / 日期真相
- 指数级技术态势，用于 regime 判断
- 市场级资金或风险偏好代理
  - `moneyflow_hsgt` 这类北向聚合摘要
  - `margin` 聚合摘要这类杠杆风险偏好代理

### Async Enrichment Context

不阻塞当前轮的补充上下文。

特点：

- best-effort
- 信息密度可以更高，但不能卡住主链
- 失败只记黄灯，不改变当前轮是否有效的判断

典型 enrichment：

- 热点题材
- 新闻 / 公告摘要
- 更长链条的宏观补充
- 板块或叙事层扩展说明

---

## 3. 当前轮与下一轮的边界

Blocking core 只服务当前轮。

Async enrichment 的结果：

- 不做同轮 best-effort 拼接
- 不在 blocking deadline 之后强行并回当前轮 memo
- 只允许进入日志、缓存或下一轮上下文

这条边界的目标是保持实验统计干净，避免“同样一轮”因为补充信息回来的时间不同而变成不可比较。

---

## 4. 数据源原则

### 4.1 稳定性优先于信息密度

Stage 1 默认策略是：

- 宁可信息少，也不要默认走脆弱或慢接口
- 宁可少数高质量聚合信号，也不要把大量原始数据直接塞给 Stage 1

### 4.2 工具必须显式 allowlist

Stage 1 不允许把 MCP 返回的全量工具直接暴露给 `MarketAnalyst`。

原因：

- 默认全量工具会把 slow / fragile / semantically drifted 的接口带入主链
- 这会把 Stage 1 timeout 从偶发问题变成系统性问题

因此，blocking core 和 enrichment 必须分别有自己的 allowlist。

### 4.3 Tushare Pro 作为结构化真值优先源

对 Stage 1 的市场级结构化信号，优先级应为：

1. Tushare Pro 这类稳定、可回放的结构化源
2. 本地 materialized / readiness 已确认可用的数据资产
3. AKShare 等更适合探索或补位的数据源

AKShare 仍然可以存在，但默认角色更接近：

- enrichment
- backup
- 快速探索

而不是 blocking core 的唯一真值来源。

---

## 5. Timeout 与降级语义

### 5.1 `single` / 调试模式

允许降级，但必须显式记录。

可接受的行为：

- 输出最小可解析 memo
- 记录 timeout / degraded 状态
- 允许开发者继续看下游链路是否通

### 5.2 `evolve` / 实验模式

Blocking core timeout 或缺失，不应再被视为“可比较的绿灯样本”。

要求：

- blocking core 失败应触发显式红灯
- 不再静默带空上下文继续积累实验统计
- rerun 前应允许使用显式 reset 工具清理无效运行痕迹

### 5.3 同日 memo 复用

同日复用只允许发生在：

- 先前 memo 来自成功的 blocking core
- 先前 memo 没有被标记为 degraded / timed out

不允许：

- 把 round 0 的空或降级 memo 静默复用到后续轮次

---

## 6. Agent 角色

### MarketAnalyst

`MarketAnalyst` 的主职责是生成 blocking core memo。

它可以：

- 调用 blocking-core allowlist 工具
- 输出结构化 `MarketContextMemo`
- 触发或调度 enrichment

它不应：

- 默认等待长链条补充信息
- 依赖全量热点/新闻/宏观抓取才算完成
- 把 enrichment 结果在 deadline 之后硬塞回当前轮

### LiteratureMiner

`LiteratureMiner` 负责补充本地历史上下文：

- 岛屿历史优秀因子
- 常见失败模式
- 方向性参考

它的特点是：

- 不依赖外网
- 可以作为 Stage 1 的稳定本地补充
- 但不能替代 blocking core 的市场真值

---

## 7. 实现收口要求

在当前主干上，Stage 1 后续实现应按这个顺序收口：

1. 建立 blocking core / enrichment 分层
2. 给 `MarketAnalyst` 建立默认工具 allowlist
3. 把市场级资金面真值切到更稳定的结构化来源
4. 把慢且脆弱的接口移出 blocking 主路径
5. 让 timeout 结果进入显式 experiment validity 语义

---

## 8. 测试要求

至少应覆盖以下场景：

- blocking core timeout 在实验模式下触发显式无效状态
- enrichment 失败不阻塞当前轮
- degraded memo 不会被同日静默复用
- Stage 1 allowlist 不会把 fragile 工具带入 blocking 主路径
- LiteratureMiner 在无历史数据时仍返回合法结构
