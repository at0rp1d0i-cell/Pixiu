# FormulaSketch Lite v1 Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-23
Purpose: Define FormulaSketch Lite v1 as a controlled Stage 2 contraction layer that reduces low-level formula waste in the dirtiest subspace before broader Stage 2 search improvements.

Source checked:

- Qlib official operator/API docs: `Rank(feature, N)`, `Quantile(feature, N, qscore)`
- local `qlib 0.9.7` runtime behavior via `uv run python` introspection

---

## Why Now

最新受控实验已经给出足够清楚的信号：

- `factor_algebra` 是当前最脏的 Stage 2 子空间
- 它同时在制造：
  - `validator` 废料
  - `novelty` 废料

这说明当前问题已经不是单纯的 prompt 漂移，而是：

> LLM 仍然在自由书写公式字符串，导致低级错误和重复 family 都在上游被不断制造出来。

继续只靠本地 pre-screen 和 Stage 3 gate，会让系统持续处于：

- 先生成废料
- 再过滤废料
- 再 retry

这不是收敛，而只是止血。

因此这轮需要引入第一块真正的“构造性约束”：

`FormulaSketch Lite v1`

---

## Goal

这轮的目标不是做完整公式 DSL，也不是重写整个 Stage 2。

这轮只做一件事：

> 让 `factor_algebra` 的一部分低级错误变成“尽量构造不出来”，同时保持当前 Stage 2/3/4 外部 contract 不变。

必须达到的结果：

1. `factor_algebra` 不再完全依赖自由公式字符串生成
2. 第一版直接压掉最常见的低级 waste，尤其是自由 `Div` 和不受控归一化
3. Stage 3 hard gate 不放松
4. `FactorResearchNote` 当前 schema 不改
5. 其余子空间先不被拖入大范围迁移

---

## Non-Goals

这轮不做：

- 不做 schema-level `FormulaSketch`
- 不做 AST-first formula generation
- 不改 `ResearchNote` / `Hypothesis` / `StrategySpec` contract
- 不覆盖所有 Stage 2 子空间
- 不解决 family-level anti-collapse
- 不替代 Stage 3 validator

---

## Chosen Shape

采用：

> `internal recipe -> deterministic renderer -> proposed_formula`

而不是：

- prompt-only 继续自由写公式
- schema-level sketch 对外扩散
- 完整 AST/DSL 一次到位

原因：

- 当前主线优先级是恢复实验收敛，不是再次大动 schema
- `factor_algebra` 是最适合先做结构化收缩的子空间
- 当前 [research_note.py](/home/torpedo/Workspace/ML/Pixiu/src/schemas/research_note.py) 对外 contract 仍以 `proposed_formula / final_formula` 为真相
- 当前 [mutation.py](/home/torpedo/Workspace/ML/Pixiu/src/hypothesis/mutation.py) 的 AST 能力不足以直接承担 Stage 2 全量公式生成

所以 v1 只在内部引入 sketch，不把它暴露成新的外部 schema。

---

## Scope

### In Scope

- `factor_algebra`
- `AlphaResearcher` 内部 recipe 生成
- deterministic renderer
- 当前 Stage 2 本地 pre-screen 之前的上游约束

### Out of Scope

- `cross_market`
- `narrative_mining`
- `symbolic_mutation`
- Stage 3 gate 规则
- Stage 4/5 对象边界
- family memory / anti-collapse memory

---

## Core Idea

当前自由生成路径是：

`LLM -> proposed_formula string -> local prescreen -> Stage 3`

v1 收成：

`LLM -> FormulaRecipe -> deterministic renderer -> proposed_formula string -> local prescreen -> Stage 3`

关键区别：

- LLM 不再直接对最终公式字符串拥有完全自由
- renderer 只允许有限且已批准的组合方式
- `proposed_formula` 仍然是当前运行时 contract

也就是说：

> v1 替代的是“公式字符串自由书写”这部分自由度，而不是 hypothesis 生成本身。

---

## Minimal Recipe

第一版 recipe 不做 AST，只做足够强的“配方式”结构。

建议最小字段：

- `base_field`
  - 主字段，如 `$close`、`$volume`、`$vwap`
- `lookback_short`
  - 短窗口，来自有限桶
- `lookback_long`
  - 长窗口，来自有限桶
- `transform_family`
  - 允许的模式族，如：
    - `mean_spread`
    - `ratio_momentum`
    - `volatility_state`
    - `volume_confirmation`
- `interaction_mode`
  - `none | mul | sub`
- `normalization`
  - `none | rank | quantile`
- `secondary_field`
  - 可选，用于量价确认等模式

第一版不暴露：

- 任意 operator 树
- 任意嵌套
- 任意 `Div`
- 任意二元算子自由拼接

---

## Renderer Rules

renderer 负责把 recipe 渲染成合法公式。

第一版只允许固定模板，不允许自由组合：

### 模板族

1. `mean_spread`
- `Mean(base, short) - Mean(base, long)`

2. `ratio_momentum`
- `Mean(base, short) / Mean(base, long) - 1`
- 只允许当 denominator 模板已知稳定时使用

3. `volatility_state`
- `Std(base, short) - Std(base, long)`

4. `volume_confirmation`
- `Mul(Mean(price_base, short) - Mean(price_base, long), Mean(volume_base, short) - Mean(volume_base, long))`

### Normalization

只允许：

- `Rank(expr, N)`
- `Quantile(expr, N, qscore)`

禁止：

- `Zscore`
- `MinMax`
- `Neutralize`
- `Demean`

### Div Policy

第一版策略：

> 不允许自由 `Div`

只允许 renderer 输出少量白名单模板内部已批准的比值形式。

原因：

- 当前实验 telemetry 已经证明 `Div` 是高频 waste source
- 在 family memory 和更丰富 math-safe builder 进来前，先把这类自由度收掉最划算

---

## Allowed Freedom

v1 明确保留这些自由度：

- hypothesis 文本
- economic intuition
- regime 声明
- risk factors
- island 级方向选择
- `factor_algebra` 内部机制方向选择

v1 明确收掉这些自由度：

- 任意 operator 拼接
- 任意 arity
- 任意窗口数值
- 任意 `Div`
- 任意 normalization 写法

---

## Why Not AST Now

AST-first 是正确长期方向，但这轮不做，原因有三：

1. 当前 [mutation.py](/home/torpedo/Workspace/ML/Pixiu/src/hypothesis/mutation.py) 的 parser/runtime 主要服务符号变异，不足以直接承载全量 Stage 2 生成
2. 当前主线需要的是受控收缩，而不是再次打开一轮大基础设施建设
3. recipe/renderer 能更快把最主要的 waste 先打掉

因此：

`AST-first formula generation` 是明确保留的重基建方向，但不是 v1。

---

## Why Not Schema-level Sketch Now

schema-level `FormulaSketch` 同样是正确长期方向，但这轮不做：

1. 当前 [research_note.py](/home/torpedo/Workspace/ML/Pixiu/src/schemas/research_note.py) 仍以 `proposed_formula / final_formula` 为主运行时真相
2. 若这轮直接改 schema，会连带 Stage 3/4/5、logger、artifacts 一起动
3. 当前目标是尽快提高实验收敛，不是做一次大范围 schema 迁移

因此：

`schema-level FormulaSketch` 也是明确保留的重基建方向，但不是 v1。

---

## Explicitly Deferred Foundations

下面两项不是被否决，而是这轮明确延期：

### DEF-003: AST-first formula generation

- 用更强的语法树表达 Stage 2 公式生成
- 目标：彻底收掉自由字符串书写

### DEF-004: schema-level FormulaSketch

- 在 `ResearchNote` / `Hypothesis` / `StrategySpec` 周边正式承载 sketch 对象
- 目标：让 sketch 成为可审计、可测试、可跨 stage 流通的一等对象

这两项都应同步进入 runtime concessions ledger。

---

## Expected Effect

如果 v1 做对，最直接的实验信号应该是：

- `factor_algebra` 的 `validator` 废料下降
- `factor_algebra` 的 `novelty` 废料也有所下降
- Stage 2 本地 retry 次数下降
- Stage 3 剩余问题更集中在更高层的 `alignment` 或 family-level collapse

也就是说：

> v1 不要求“立刻变聪明”，但要求“先别再犯这么多低级错误”。

---

## Acceptance

完成标准：

1. `factor_algebra` 不再完全走自由公式字符串生成
2. 第一版 renderer 已限制到有限模板和有限 normalization
3. 自由 `Div` 已从 v1 中被收掉
4. 外部 schema 和 Stage 3 hard gate 不变
5. 实验工件能显示 `factor_algebra` 的 `validator` waste 有明显下降
