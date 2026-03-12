# Pixiu v2 Authority Model

> 版本：2.0
> 创建：2026-03-10
> 优先级：**P0 — 运行时权限边界规格**
> 关联规格：`.../overview/architecture-overview.md`、`stage-45-golden-path.md`、`interface-contracts.md`

---

## 1. 纠偏结论

Pixiu 的主要问题不是“方向错误”，而是“权限分配错误”。

- 五阶段漏斗方向正确
- LLM-native research 方向正确
- 需要纠偏的是：AI 被赋予了过多执行真值权限

核心原则：

> LLM 负责扩大 hypothesis space，不负责扩大 execution power。

---

## 2. 架构宪法（Authority Constitution v0.1）

1. LLM 只负责认知，不负责执行真值。
2. Stage 3→4 边界必须是强类型对象（schema-gated），不能是自由文本指令。
3. Stage 4 必须是 deterministic sandbox，支持 replay。
4. AI 不能同时担任“生成者”和“最终评估裁判”。
5. Stage 5 只沉淀结构化研究资产，不沉淀叙事型 memory。
6. 每次运行必须能追溯数据、代码、参数、prompt、日志和 lineage。
7. A 股交易约束必须进入 execution semantics，而不是注释。
8. 失败经验必须被转化为硬约束（failure constraints）。

---

## 3. 权限分层

### 3.1 Cognitive Plane（LLM）

职责：

- Stage 1 市场扫描和信号归纳
- Stage 2 假设生成、变异、解释
- Stage 5 报告表达与失败归纳

边界：

- 输出必须是 `schema` 对象
- 不允许直接控制执行重试和系统路由

### 3.2 Deterministic Control Plane

职责：

- workflow 执行
- 超时、重试、恢复、终止
- replay 与 event history

边界：

- 不依赖 LLM 动态决策执行流
- 人工审批动作应以结构化事件写入控制平面

### 3.3 Execution Sandbox Plane

职责：

- Stage 3 deterministic gates
- Stage 4 计算与回测语义

边界：

- 仅接受强类型 `StrategySpec/ExecutableFactor`
- 禁止在执行阶段临场让 LLM 修脚本/改语义

### 3.4 Artifact & Lineage Plane

职责：

- run / metrics / artifacts 记录
- 数据与模型产物版本
- lineage 绑定

边界：

- 结果必须可回放、可审计

### 3.5 Knowledge Plane

职责：

- 结构化 `research objects`
- success patterns
- failure constraints

边界：

- 向量记忆和自然语言总结不能替代结构化对象

---

## 4. Stage 边界硬化要求

### 4.1 Stage 2 输出

必须输出强类型对象，不允许“自然语言执行请求”直接进入 Stage 4。

推荐最小对象：

- `Hypothesis`
- `StrategySpec` / `ExecutableFactor`

### 4.2 Stage 3 Gate

必须引入 deterministic gate v0：

1. schema / data validity
2. quick quality panel
3. statistical anti-overfitting gate（如 DSR/PBO/多重检验口径）

### 4.3 Stage 4

收敛成唯一 replay 路径：

`StrategySpec -> sandbox execute -> BacktestRun -> EvaluationReport -> artifact save -> lineage bind`

### 4.4 Stage 5

以 Failure Memory Engine 为主，而不是“反思散文”：

- economic invalidity
- runtime error
- high correlation redundancy
- high PBO / low DSR
- unstable regime
- excessive turnover / low capacity

---

## 5. Red Flags（必须避免）

1. 把多 agent 辩论当成可复现基础设施
2. 让开放式 agent framework 直接掌控核心执行
3. 把 narrative memory 当作知识沉淀
4. 忽略统计防作弊，导致噪声赢家系统性放大

---

## 6. 对当前 Pixiu 的执行含义

### 当前必须推进

1. 冻结 6 个核心对象并补齐消费路径：
   - `Hypothesis`
   - `StrategySpec/ExecutableFactor`
   - `FilterReport`
   - `BacktestRun`
   - `EvaluationReport`
   - `FailureConstraint`
2. 把 LangGraph 从“全局掌权编排器”降级为“认知图表达层”。
3. 把 Stage 4 deterministic 路径变成唯一真值来源。
4. 把 Stage 5 改造成结构化 Failure Memory Engine。

### 当前明确不做

1. 不继续扩展 AI 在执行层的即时修复权限
2. 不以更复杂的 agent theatre 替代 deterministic 控制面
3. 不以 memory 文本总结替代结构化研究对象

---

## 7. 与“提升 AI 能力”的关系

本规格不是限制 AI，而是重新分配 AI 权限。

应扩展的是：

- factor algebra search
- symbolic factor mutation
- cross-market pattern mining
- economic narrative mining
- regime-conditional factor discovery

不应扩展的是：

- execution control power
- evaluator final authority

---

## 8. 当前状态（2026-03-10）

`implemented/partial`

- Stage 4/5 最小闭环已存在
- control-plane 最小 `state_store` 已存在
- richer contract 已开始进入主干
- 但 authority model 还未完全收口（仍存在新旧字段双轨、认知层与执行层边界未完全硬化）
