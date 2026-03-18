# Stage 2 Runtime Expansion Notes

Purpose: Preserve Stage 2 runtime expansion directions that are useful for future implementation work but should not remain inside the canonical Stage 2 design doc.
Status: planned
Audience: both
Canonical: no
Owner: core docs
Last Reviewed: 2026-03-18

这篇文档承接的是 Stage 2 的前瞻实现笔记。当前主文档只保留当前有效设计，这里才讨论下一步如何把 Stage 2 继续做深。

## 1. 为什么移到这里

`21_stage-2-hypothesis-expansion.md` 的主价值是回答：

- Stage 2 为什么存在
- 当前有哪些活跃子空间
- 当前输入输出如何收敛
- 当前主干里的 Researcher / Synthesis / regime 基础设施是什么状态

更细的原语注册表、符号变异细节和更丰富的 regime 消费路径，适合保留，但不适合继续挤在 canonical 主文档里。

## 2. Factor Algebra 的下一步

当前主干里已经有：

- `SubspaceRegistry`
- `build_subspace_context`
- `FACTOR_ALGEBRA` 子空间

仍值得继续推进的方向包括：

- 更正式的 primitive registry
- 原语分类和可用性开关
- 更明确的组合约束
- 将 failure constraints 直接作用到原语搜索空间

## 3. Symbolic Mutation 的下一步

当前主干里已经有：

- `SymbolicMutator`
- 五种 `MutationOperator`
- `SYMBOLIC_MUTATION` 的纯符号快速路径

下一步更值得做的是：

- 把 mutation trace 更稳定地沉淀到研究对象里
- 缩短从 seed formula 到 candidate note 的桥接路径
- 让 mutation 结果和 Stage 3 的失败模式形成更直接反馈闭环

## 4. Regime 基础设施的下一步

当前已经落地的部分包括：

- `RegimeDetector`
- `RegimeFilter`
- `applicable_regimes / invalid_regimes`

未来更应该继续扩的是：

- richer regime feature set
- 在 Stage 2 prompt / tool context 里的更直接消费
- 与 narrative / cross-market 子空间的更清晰交汇

这不意味着恢复独立的 `REGIME_CONDITIONAL` 子空间，而是把 regime 当成基础设施层继续做实。

## 5. 与主文档的关系

当前有效设计仍以：

- `../design/21_stage-2-hypothesis-expansion.md`
- `../overview/05_spec-execution-audit.md`

为准。
