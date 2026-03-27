# Current Implementation Plan

Status: active
Owner: coordinator
Last Reviewed: 2026-03-27

> 更新时间：2026-03-27
> 来源：2026-03-27 Stage 1 live closure runtime evidence、最新 `controlled single` / `doctor` / `preflight` / live test 结果、`docs/overview/05_spec-execution-audit.md`

---

## 目标

把 Pixiu 从“局部快实验健康，但全量主线仍失真”的状态，推进到“内部可持续进化的研究管线”：

- `fast_feedback` 和 `controlled single` 都能提供可信信号
- `Stage 1 live` 不再因 env / tool discovery 失真直接 degraded
- `Stage 2` 不再主要浪费在 novelty/robustness/value-density 低质候选
- `candidate -> promote` 进入真实 validation runtime
- 主线真相由 canonical docs、resolved profile、artifact 一致描述

---

## 当前运行真相

### Fast Feedback

当前 `fast_feedback` 已经足够做工程验证：

- `Stage 2/3` 局部面已基本收敛
- 主要问题已切到 `approved -> low_sharpe`
- 适合验证 contract、diagnostics、retry、family steering、provider 切换

但它仍然是 experiment-only shortcut：

- `frozen/cached` context
- narrowed family surface
- quota override
- isolated namespace / artifact-only persistence

**结论：**
`fast_feedback` 只能证明局部 engineering loop 健康，不能证明全管线健康。

### Controlled Single

当前 `controlled single` 仍不健康。

最新主线证据：
- `Stage 1 live closure` 已完成
- `Stage 2: 48 -> 5`
- `Stage 3: 5 -> 4`
- `Stage 5: low_sharpe x4`

因此当前主线不是“继续微调 fast_feedback”，而是把快实验学到的收敛手段外推到真实搜索面。

---

## 当前健康标准

只有同时满足下面 4 条，才可称为“相对健康、可持续进化的内部管线”：

1. `default/controlled` 下的 `Stage 1 live` 连续稳定，不再因 env truth / tool discovery 直接 degraded
2. `controlled single` 的主拒绝不再由大规模 `novelty/alignment/validator` 主导
3. `candidate -> promote` 有真实 validation runtime，不再只是 schema/语义层正确
4. `fast_feedback` 与 `controlled single` 的 profile 边界清楚，不再互相污染健康判断

---

## 主线执行顺序

### Phase 1: Truth Reset（当前最高优先级）

- [x] 更新 `docs/overview/05_spec-execution-audit.md`
- [x] 更新本计划，重写当前主线优先级
- [ ] 更新 `docs/overview/06_runtime-concessions.md` 中已经过时的 removal trigger / rationale
- [ ] 明确 `default / fast_feedback / controlled / long_run` 的 profile matrix
- [ ] 明确 canonical docs 中哪些内容仍指向 `docs/project/` / 旧入口，并收口为当前 truth hierarchy

**Done when**
- canonical docs 的优先级不再误导开发者
- 快实验与全量主线的边界有统一口径

### Phase 2: Stage 1 Live Closure

- [x] 对齐 `pixiu run` 与 `doctor/preflight` 的 env truth
- [x] 在真实 `pixiu run` 环境下验证：
  - `TUSHARE_TOKEN` 可见
  - blocking tools 可 discover
  - `get_moneyflow_hsgt`
  - `get_margin_data`
- [x] 收口 Stage 1 blocking tool discovery policy，避免“发现阶段过脆”
- [x] 用当前 blocking-core 真相重写 live integration test，不再测旧 AKShare/old northbound path

**Done when**
- controlled `single` 下 `Stage 1` 不再因为 env/tool discovery 直接 degraded

### Phase 3: Controlled-Run Stage 2 Closure

- [ ] 收 `Stage 2` JSON / output robustness
- [ ] 把 `factor_gene / anti-collapse / family steering` 从 fast-feedback 面外推到 controlled run 面
- [ ] 对 `approved -> low_sharpe` 做 family / subspace 聚合分析
- [ ] 优先处理：
  - controlled-run `novelty waste`
  - `approved but low_sharpe`
  - 输出稳定性
- [ ] 不再继续主要投入在 Stage 3 prompt 微调

**Done when**
- controlled `single` 不再主要死在 `novelty/alignment/validator`
- `Stage 2` 送进回测的候选更少但更值钱

### Phase 4: Validation Closure

- [ ] 把 `candidate -> promote` 变成真实 runtime，而不是仅靠字段/语义
- [ ] 补最小可用的 OOS promote 路径
- [ ] 继续补：
  - walk-forward
  - PIT 边界
  - A 股执行约束
    - 涨跌停
    - 停牌
    - ST
    - 历史成分股
    - survivorship
- [ ] 补 `risk/judgment` 的解释能力，让它能解释“为什么 low_sharpe”

**Done when**
- `promote` 不再是语义壳，而是经过真实 validation 的结果

### Phase 5: Throughput and Cost Optimization

- [ ] 先按当前 `llm_usage` / artifact 数据做 per-stage rollup
- [ ] 优化 `Stage 2 hypothesis_gen`
- [ ] 只在 value density 与 validation 收口后，再评估是否优化 `Stage 4 backtest`
- [ ] 接入真实 pricing layer，补齐 `estimated_cost_usd`

**Done when**
- 性能优化建立在“更少垃圾候选”之上，而不是更快地产生垃圾候选

---

## 明确后置的方向

以下方向当前**不是**主线最高优先级：

- `Stage 2` 直接接 RSS / MCP / 更广数据面
- MiroFish Go/No-Go
- Dashboard / 更广产品层
- 完整多 provider adapter
- 更广 narrative / cross-market surface 扩展

这些方向要在 `Stage 1 live + controlled Stage 2 + validation closure` 之后再继续推进。

---

## 可并行分支

在不碰 schema truth 和主线程架构判断的前提下，可以并行拆成下面几条分支：

1. `Stage 1 live closure`
2. `controlled-run Stage 2 robustness + value density`
3. `validation runtime closure`

不应外包给分支的内容：

- 主线优先级改写
- canonical docs 口径统一
- `spec-execution-audit` 更新
- 跨模块架构取舍

---

## 已完成的基础，不再作为主线争论点

下面这些基础已经进入主线，不需要再重复当成“下一步重点”：

- `fast_feedback` harness/profile
- FormulaSketch Lite
- factor gene / anti-collapse / family steering 的最小主干
- `candidate -> promote` 语义层
- `llm_usage` 的 stage/round metadata
- `Stage 4` 最小 discovery/OOS split

接下来要解决的是：**把这些基础从局部成功，推进到全量主线成功。**
