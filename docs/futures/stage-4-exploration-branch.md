# Stage 4 Exploration Branch

Purpose: Preserve the optional ExplorationAgent branch and related expansion notes without mixing them into the canonical Stage 4 execution doc.
Status: planned
Audience: both
Canonical: no
Owner: core docs
Last Reviewed: 2026-03-18

这篇文档保存 Stage 4 的探索分支说明。它不是当前 Stage 4 -> 5 golden path 的主入口。

## 1. 为什么移到这里

当前 canonical Stage 4 已经收敛为：

- `FactorResearchNote.final_formula`
- `Coder`
- `DockerRunner`
- `BacktestReport`

如果把 `ExplorationAgent`、脚本细节、FAQ 和旁支讨论继续放在主文档最前面，读者很容易误判 Stage 4 的当前真相。

## 2. ExplorationAgent 的定位

`ExplorationAgent` 当前仍在代码主干中，职责是：

- 消费 `exploration_questions`
- 生成临时 EDA Python 脚本
- 在沙箱中执行
- 返回 `ExplorationResult`

它适合回答的问题包括：

- 需要先做简单 EDA 才能缩小公式空间
- 需要验证一个机制描述是否和数据大体一致
- 需要把 Stage 2 的探索问题压成更清晰的 refinement 信号

它不应承担的职责：

- 代替 `Coder` 生成正式回测结果
- 把执行层变成自由代码代理
- 绕开 `BacktestReport` 直接进入 Stage 5

## 3. 如果以后继续增强

后续如果重新强化这一支，应保持三条硬约束：

- 探索分支永远不能替代 deterministic backtest
- 产出对象必须继续是结构化 `ExplorationResult`
- 沙箱边界必须和 `DockerRunner` 一样明确

## 4. 与主文档的关系

当前主文档是：

- `../design/23_stage-4-execution.md`

当前最小闭环入口是：

- `../design/25_stage-45-golden-path.md`
