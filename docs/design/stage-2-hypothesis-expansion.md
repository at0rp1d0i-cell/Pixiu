# Pixiu v2 Stage 2: Hypothesis Expansion Engine

> 版本：2.1
> 角色：扩大 hypothesis space，并将探索结果压缩成可进入 Stage 3/4 的结构化研究对象
> 前置依赖：`authority-model.md`、`interface-contracts.md`、`stage-1-market-context.md`

---

## 1. 角色定义

Stage 2 不再只是“并行生成几个候选因子公式”。

它的真正职责是：

> 在不扩大 execution power 的前提下，系统性扩大 hypothesis space，并把探索结果压缩成可审计、可过滤、可执行的研究对象。

这一步是 Pixiu 当前 authority model 收权后的主要补偿层。原本散落在执行层和 agent theatre 里的“聪明感”，应该回收到这里。

## 2. 设计目标

- 保留 LLM 的创造力
- 不把创造力下放到执行真值层
- 让假设扩展变成有子空间、有算子、有边界的系统过程
- 为 Stage 3 / Stage 4 提供强类型输入，而不是自然语言请求

## 3. 输入

Stage 2 读取的输入不应只是一段 prompt 背景，而应是受约束的研究上下文：

- `MarketContextMemo`
- `HistoricalInsight`
- `FailureConstraint` 摘要
- 当前 Island 的研究方向与优先级
- 当前启用的数据原语集合

当前运行时里，这些输入主要通过：

- `MarketContextMemo`
- `FactorPool` 摘要
- `last_verdict`

间接传入 `AlphaResearcher`。

## 4. 五个探索子空间

### 4.1 Factor Algebra Search

不是随意拼公式，而是围绕受约束的原语空间做搜索。

第一版原语可分成：

- price-volume primitives
- fundamental primitives
- event-derived primitives
- temporal transforms
- cross-sectional operators
- regime switches

目标是让“发现公式”逐步从自由文本联想，过渡为可解释的算子组合搜索。

### 4.2 Symbolic Factor Mutation

把“改进旧想法”显式化，而不是完全依赖 prompt 即兴发挥。

典型 mutation operator：

- add / remove operator
- swap horizon
- change normalization
- alter interaction term
- impose monotonicity or stability prior

这一步的意义是让“迭代”可以被记录、比较和复用。

### 4.3 Cross-Market Pattern Mining

迁移的不是现成公式，而是市场机制骨架。

目标对象包括：

- market mechanism analogy
- transmission path
- cross-market regime similarity

这使 Stage 2 不只是从 A 股自身历史里兜圈子，而是能吸收跨市场启发，再压缩回 A 股可执行假设。

### 4.4 Economic Narrative Mining

从政策、产业链、公告、预期偏差等叙事材料中抽取结构化机制。

典型输出应是：

- candidate mechanism
- latent driver hypothesis
- event-to-factor mapping

这里的 LLM 价值很高，但输出仍必须落在研究对象上，而不是直接形成交易建议。

### 4.5 Regime-Conditional Factors

很多因子不是“始终有效”，而是只在某些 regime 下有效。

因此 Stage 2 应开始表达：

- factor + applicable regime
- factor + invalid regime
- factor + switching-rule hypothesis

这会直接影响 Stage 3 的 gate 设计，以及 Stage 4/5 对失效模式的判断。

## 5. 输出对象

### 当前运行时输出

当前代码主干仍以 `FactorResearchNote` 作为 Stage 2 的主要输出对象。

它承担的作用是：

- 记录 hypothesis 与 economic intuition
- 承载 `proposed_formula` / `final_formula`
- 承载 `exploration_questions`
- 作为 Stage 3 / Stage 4 的临时桥接对象

### 目标对象模型

从设计上，Stage 2 应逐步靠拢两层对象：

- `Hypothesis`
  - 负责表达市场机制、适用 regime、失效前提和启发来源
- `StrategySpec`
  - 负责表达可执行因子语义、可用字段、参数化配置和执行约束

也就是说：

- `Hypothesis` 回答 “为什么这件事值得测”
- `StrategySpec` 回答 “到底测什么”

### Runtime bridge

在当前运行时里，`FactorResearchNote` 仍是进入 Stage 3 / Stage 4 的桥接对象。

但设计约束已经固定：

- Stage 2 的收敛方向是 `Hypothesis -> StrategySpec`
- 不允许继续输出自由文本执行请求
- 新增能力应优先落到子空间、算子和对象上，而不是继续堆 prompt 描述

## 6. 与 Stage 4a / Stage 4b 的关系

Stage 2 只负责提出：

- 值得进一步探索的问题
- 值得正式执行的候选对象

不负责：

- 决定如何重试执行
- 在执行时修脚本
- 在回测后临场改语义

### `exploration_questions`

当前 `exploration_questions` 是 Stage 2 与 Stage 4a 的桥。

它们的职责应该进一步收敛为：

- 明确问题
- 明确需要的字段
- 明确建议的分析类型

而不是把 Stage 4a 变成通用“让 AI 去随便看看”的口子。

### `final_formula`

进入 Stage 4b 的唯一公式字段必须是：

- `final_formula`

这条规则保持不变。Stage 2 可以探索，但进入确定性执行时只能交付最终表达式。

## 7. 当前运行时组件

### `AlphaResearcher`

当前 MVP 运行时仍由 `AlphaResearcher` 负责单个 Island 的批量生成。

它目前已做到：

- Island 级并行
- 批量生成 `FactorResearchNote`
- 支持 `exploration_questions`
- 接收历史反馈做局部改进

但它还没有显式体现五个探索子空间，也没有将 mutation / regime / cross-market 变成稳定对象。

### `SynthesisAgent`

`SynthesisAgent` 当前仍停留在弱关联检查层。

它未来更有价值的职责应是：

- 去重
- 识别潜在 family
- 提出 hypothesis merge / split
- 输出更结构化的组合启发

## 8. 下一步设计要求

Stage 2 后续不应只继续“让 prompt 更聪明”，而应补这三类设计：

1. exploration subspace registry
2. mutation operator vocabulary
3. `Hypothesis / StrategySpec` 的正式 schema

如果这三者不补，Stage 2 会继续停留在“更会说的 note generator”，而不是一个真正的 `Hypothesis Expansion Engine`。

当前实现偏差，请查看 `../overview/spec-execution-audit.md`。
