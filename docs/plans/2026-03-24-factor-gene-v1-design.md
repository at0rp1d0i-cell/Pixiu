# Factor Gene v1 Design

**Date:** 2026-03-24  
**Status:** Approved for implementation

## Goal

为 Pixiu 定义一层最小的 `factor gene` 表示，用来支撑：

- `family-level novelty`
- `anti-collapse memory`
- 后续多样性控制与搜索分布引导

这轮只收 `v1`，但文档同时明确 `v2 / v3 / 理想形态`，避免后续再次把短期 patch 误当长期架构。

## Why Now

截至 2026-03-24，`factor_algebra` 的主问题已经从低级 recipe 错误切换成了 `novelty collapse`：

- 字段和窗口等低级 contract 已经在持续收口
- 但系统仍然会围绕相同公式骨架、相同机制模板不断打转
- 当前 novelty 主要还是 token-level/Jaccard 风格的事后拦截

这说明 Pixiu 当前还缺一层更稳定的“家族表示”：

> 系统需要知道哪些候选属于同一家族，哪些只是同一家族里的窗口微调，哪些才是真正的新方向。

如果没有这层表示，系统即使能跑，也很难真正持续进化。

## Relationship to FormulaSketch

`FormulaSketch Lite v1` 解决的是：

- 如何减少低级公式 waste
- 如何把部分错误变成 “impossible-by-construction”

`factor gene` 解决的是：

- 如何判断 family / variant
- 如何减少 collapse
- 如何让经验真正改变搜索分布

两者关系是：

- `FormulaSketch` 负责**受控生成**
- `factor gene` 负责**结构表示与多样性控制**

这两层不应混写成一个系统。

## External Signals

这个方向和近期公式因子研究的主流趋势是一致的：

- Qlib 官方把 formulaic alpha 定义成结构化表达对象，而不是纯文本提示词
- AlphaGen 更强调 alpha pool 与协同搜索，而不是单个最佳因子
- AlphaForge、AlphaFlows、AlphaSAGE 等后续工作都在往：
  - 结构表示
  - 多样性控制
  - mode collapse 抑制
  - collection-level optimization
  这几个方向推进

对 Pixiu 的直接启发是：

- novelty 不该只看公式字符串
- 搜索目标不该只是单个 candidate 的通过率
- family / mechanism / variant 的表示层应该提前进入系统

## Evolution Path

### v1

只覆盖 `factor_algebra`，从 deterministic `formula_recipe` 直接导出 gene。

目标：

- 给 `factor_algebra` 增加一层稳定、可重复的 family/variant 表示
- 不改 schema 主干
- 先服务 novelty 与 anti-collapse

### v2

扩展到多子空间，但仍然保持“子空间内局部基因提取”：

- `cross_market`
- `narrative_mining`
- `symbolic_mutation`

新增内容：

- `mechanism tag`
- `proxy tag`
- `regime tag`
- subspace-specific gene extractor

目标：

- 让不同子空间有各自可解释的 gene，而不是强行共用一套抽象 ontology

### v3

引入更强的结构表示：

- AST-first / graph-like gene
- structure-aware novelty
- family neighborhood / structural distance

目标：

- 不再依赖字符串近似
- 把“相似度”提升到结构层

### Ideal Form

Pixiu 最终维护的是一个 `genotype-phenotype archive`：

- `genotype`
  - mechanism
  - proxy
  - structure
  - regime
  - family
- `phenotype`
  - formula
  - backtest
  - risk
  - cost
  - portfolio contribution

搜索、collapse 控制、family memory 主要发生在 genotype 空间；组合和评判主要发生在 phenotype 空间。

## Chosen Now: Factor Gene v1

这轮只做 `factor_algebra` 的最小 gene。

### Scope

In scope:

- `factor_algebra`
- deterministic gene extraction from `formula_recipe`
- family-level novelty / anti-collapse 的消费接口设计

Out of scope:

- schema-level gene object
- 全子空间统一 ontology
- LLM 生成 gene
- genetic programming / RL / archive policy

## Core Shape

`gene v1` 分两层：

### 1. family_gene

用于回答：

> 这是不是同一家族？

建议字段：

- `subspace`
- `transform_family`
- `base_field`
- `secondary_field`
- `interaction_mode`
- `normalization_kind`

### 2. variant_gene

用于回答：

> 这是不是同一家族里的小变体？

建议字段：

- `lookback_short`
- `lookback_long`
- `normalization_window`
- `quantile_qscore`

约束：

- `variant_gene` 只承载数值调节项
- 不重复承载：
  - `base_field`
  - `secondary_field`
  - `transform_family`
  - `interaction_mode`
  - `normalization_kind`

这些字段已经属于 `family_gene`，不应在 `variant_gene` 中再次出现。

## Why Two Layers

只用 `variant_gene` 太细：

- `5/20` 和 `10/30` 会被过早看成完全不同

只用 `family_gene` 太粗：

- 合理探索会被一刀切成“重复”

两层结构更适合当前 Pixiu：

- `family_gene` 控 family
- `variant_gene` 控微调

## Proposed Semantics

### Duplicate

当 `family_gene + variant_gene` 都相同：

- 直接视为 duplicate

### Near-duplicate / collapse

当 `family_gene` 相同，但 `variant_gene` 只是窗口或 `qscore` 小改：

- 视为 collapse 候选

### New direction

当 `family_gene` 发生变化：

- 视为真正的新方向候选

## Deterministic Extraction

`v1` 的关键原则：

> gene 必须从 `formula_recipe` 直接导出，而不是再让 LLM 总结一次。

原因：

- recipe 已经是 deterministic object
- 这层应该稳定、可测试、可回放
- 不能把 collapse 判断又变回 prompt 依赖

## Canonical Representation

`gene v1` 不应只存成一个字符串，也不应只存成一个结构化对象。

推荐采用双表示：

### 1. Structured gene object

作为真相层，用于：

- artifact
- 调试
- 文档与审计
- 后续 richer gene 扩展

示例：

```json
{
  "subspace": "factor_algebra",
  "transform_family": "volatility_state",
  "base_field": "$close",
  "secondary_field": null,
  "interaction_mode": "none",
  "normalization_kind": "quantile"
}
```

### 2. Canonical key

作为索引层，用于：

- 检索
- 去重
- 快速比较
- 后续 hash 派生

示例：

```text
factor_algebra|volatility_state|$close|null|none|quantile
```

### Rule

> `structured object = source of truth`
> `canonical key = retrieval / comparison key`

后续如需 hash，应由 canonical key 派生，而不是反过来把 hash 当真相。

## Example

给定 recipe：

```json
{
  "base_field": "$close",
  "lookback_short": 5,
  "lookback_long": 30,
  "transform_family": "volatility_state",
  "interaction_mode": "none",
  "normalization": "quantile",
  "normalization_window": 20,
  "quantile_qscore": 0.8
}
```

可导出：

- `family_gene`
  - `subspace=factor_algebra`
  - `transform_family=volatility_state`
  - `base_field=$close`
  - `secondary_field=null`
  - `interaction_mode=none`
  - `normalization_kind=quantile`
- `variant_gene`
  - `lookback_short=5`
  - `lookback_long=30`
  - `normalization_window=20`
  - `quantile_qscore=0.8`
- `family_gene_key`
  - `factor_algebra|volatility_state|$close|null|none|quantile`
- `variant_gene_key`
  - `5|30|20|0.8`

## First Consumers

`v1` 不直接改整个架构，先服务两个点：

### 1. family-level novelty

替代一部分 token-level novelty：

- 先判断 gene family
- 再判断 variant 是否只是小改

### 2. anti-collapse memory

对 `factor_algebra` 记录：

- 哪些 `family_gene` 已经过饱和
- 哪些 `variant_gene` 只是重复微调

然后把这些信息回喂给 Stage 2。

## Gene Retrieval

`factor gene` 进入主线后，不应只服务 novelty gate，也应该成为因子库的一条检索轴。

建议把后续检索面分成两类：

### 1. phenotype retrieval

用于回答：

- 哪些因子 Sharpe 更高
- 哪些因子在某个 regime 下通过率更高
- 哪些因子已经进入 pool / portfolio

典型条件：

- formula
- backtest metrics
- risk
- regime
- cost

### 2. gene retrieval

用于回答：

- 有没有完全相同的家族/变体
- 某个 family 已经长出了哪些变体
- 哪些 family 已经过饱和
- 哪些 gene 邻域还比较空

典型条件：

- `family_gene`
- `variant_gene`
- family saturation
- collapse history

结论：

> 因子库后续应同时支持 phenotype retrieval 和 gene retrieval，而不是只保留公式字符串与回测指标。

`v1` 不会替换现有检索，只会先把 gene 作为并行索引引入。

## Research-Layer Reflection

当前研究层并不是完全单轮：

- `AlphaResearcher.generate_batch()` 有一次主生成
- 若本地预筛全灭，最多一次 bounded retry

但这仍然是很浅的立即反思。

这在吞吐上是合理的，但也带来一个限制：

- 对 `factor_algebra`，它只够修正一部分低级错误
- 对 `cross_market / narrative_mining`，它对“机制翻译”往往不够深

因此后续不建议把 Stage 2 改成开放式多轮 agent 对话，而建议：

> 保留短主路径，但给关键子空间增加 bounded micro-reflection。

建议路线：

- `factor_algebra`
  - recipe 生成
  - 本地自检
  - 一次有针对性的修正
- `cross_market / narrative_mining`
  - 先产 `mechanism -> proxy`
  - 再产公式
- `symbolic_mutation`
  - 保持短路径

这层与 `gene` 的关系是：

- gene 用来告诉系统“你在重复什么”
- micro-reflection 用来让系统在当轮立刻修正“为什么又重复了”

## Current Weights and Future Diversity Weights

当前子空间已经不是平均发力。

代码主干里已经有 `SubspaceScheduler`：

- 冷启动固定权重：
  - `factor_algebra = 0.33`
  - `narrative_mining = 0.25`
  - `symbolic_mutation = 0.25`
  - `cross_market = 0.17`
- 之后切换到 Thompson Sampling

这说明当前系统已经有：

- `quota weights`
- `minimum quota`
- `warm-start adaptive weights`

但当前权重只作用在：

- 子空间配额分配
- 任务数量控制

还没有作用在：

- family diversity
- collapse pressure
- gene neighborhood exploration

后续演化方向应是：

### 当前

`quota weight`

### 下一阶段

`quota weight + family saturation penalty`

### 更后阶段

`quota weight + diversity reward + gene-space exploration policy`

也就是说，未来不是取消当前调度器，而是在它上面叠加 gene/diversity 信号。

## Cross-Island Combination Boundary

当前 Pixiu 已经有两层“跨 island”能力，但它们不是同一件事：

### 1. Cross-island family overlap detection

这是 Stage 2b `SynthesisAgent` 当前已经部分具备的能力：

- 去重
- family 聚类
- 跨 island merge suggestion

这层回答的是：

> 不同 island 的候选之间，是否存在重复、家族重叠或互补关系？

它目前仍停留在 `insight / suggestion` 层。

### 2. Cross-island portfolio combination

这是 Stage 5 `PortfolioManager` 当前已经具备的能力：

- 多个通过因子可以同时进入 portfolio
- portfolio 本身可以天然覆盖多个 islands

这层回答的是：

> 多个 islands 的已通过因子，能否一起形成最小组合配置？

它是组合层，不是新因子生成层。

### 3. Cross-island composite factor

这是当前**尚未实现**、但后续可以进入路线图的一层：

- 把来自不同 islands 的机制、proxy 或结构组合成一个新的 research object
- 不再只是“建议这两个 note 可以合并”，而是生成一个新的 composite hypothesis/spec

这层回答的是：

> 多个 islands 的互补机制，是否值得压缩成一个新的复合因子对象？

当前主干还没有这层 materialization。

## Why Gene Matters for Cross-Island Work

如果后续要做真正的 cross-island combination，不能只靠 island 名字。

原因：

- 同一个 family 可能分散在不同 islands
- 同一个 island 里也可能有完全不同的 mechanisms

因此更稳定的判断轴应该是：

- `family_gene`
- 未来 richer 的 `mechanism/proxy/regime` gene

结论：

> `island` 不是 gene v1 的一部分，但 cross-island combination 未来会是 gene 的重要消费场景。

## Near-Term Rule

在 `gene v1` 阶段，Pixiu 先只做：

- 跨 island family overlap 的识别
- 通过 gene 避免把相同 family 因为 island 名字不同而误当作“新方向”

这轮不做：

- composite factor materialization
- cross-island merge 直接生成新 note
- portfolio 层之外的跨 island 结构性组合优化

这些应留给 `v2/v3` 之后的 richer gene / mechanism 表示。

## Bottleneck Validation After Pipeline Stabilizes

README 当前有一个很强的工作假设：

> LLM systems are bottlenecked by backtest execution time.

这个假设对长期形态可能成立，但在当前实验阶段，真实瓶颈未必已经落在 Stage 4。

截至 2026-03-24，真实 controlled/single run 显示：

- Stage 1 reliability 仍可能提前降级
- Stage 2/3 的 waste 仍可能在 Stage 4 之前吞掉大量候选
- Stage 4 的回测耗时很重，但不一定是当前唯一瓶颈

因此，等实验管线稳定后，必须单独做一次瓶颈验证，而不能继续沿用 README 假设做优化优先级。

建议验证维度：

- stage timing
- token / latency
- Stage 2 generated → delivered 漏斗
- Stage 3 approved / filtered 比例
- Stage 4 succeeded / failed / timeout
- family collapse rate

目标不是只回答“最慢的是哪一步”，而是回答：

> 当前限制系统积累经验的主瓶颈，到底是 Stage 1 reliability、Stage 2 collapse、Stage 3 gate、还是 Stage 4 backtest execution。

这个验证结论应在实验平台稳定后进入独立文档，而不是继续停留在 README 假设层。

## Explicitly Deferred

### Deferred for v2

- `mechanism/proxy/regime` gene
- multi-subspace gene extractor
- family memory 的长期持久化策略

### Deferred for v3

- AST-first gene
- graph-level structure distance
- structure-aware novelty

### Deferred beyond v3

- genotype-phenotype archive
- quality-diversity archive
- RL / evolutionary search directly over gene space

## Verification Plan

`v1` 进入实现时，至少验证：

1. gene extraction unit tests
   - 同 recipe → 同 gene
   - family 变更 → family_gene 变
   - 仅窗口变更 → family_gene 不变，variant_gene 变
2. novelty behavior tests
   - exact duplicate 被拦
   - same family small tweak 被标记为 collapse
3. controlled run evidence
   - `factor_algebra` novelty waste 降低
   - Stage 2 delivered candidates 更少绕已知家族打转

## Open Decision for Next Step

当前最需要确认的是：

> `family_gene` 的字段集是否就是 v1 的最终最小集，还是需要再加入一项更轻的 `mechanism_tag`。

建议先不加。

原因：

- 当前 `factor_algebra` 的 mechanism 已经体现在 `transform_family`
- 过早再加抽象标签，只会把 v1 做重
- 真正 richer 的 `mechanism/proxy/regime` 应放到 v2
