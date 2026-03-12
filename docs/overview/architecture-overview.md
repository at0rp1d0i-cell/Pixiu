# Pixiu Architecture Overview

> 版本：2.1
> 角色：项目级总览，不承载细节实现

## 1. Pixiu 是什么

对外叙事上，Pixiu 仍然可以被描述为一个“专属于 LLM 的金融研究团队”。

但在系统第一性上，它更准确的定义是：

> 一个面向中国市场的 `alpha research OS`，负责持续生成、收缩、执行、淘汰并沉淀 alpha hypotheses。

这两个说法并不冲突：

- “LLM 金融团队”回答产品感知
- `alpha research OS` 回答架构边界

Pixiu 的核心产物不是直接的投资建议，而是：

- 可执行的 research objects
- 可回放的 evaluation artifacts
- 可沉淀的 failure constraints

## 2. 当前关键修正

当前最重要的架构修正不是“继续增强执行层智能”，而是：

> 不扩大 `execution power`，扩大 `hypothesis space`。

这意味着：

- 上游允许更强探索
- 中游必须严格收缩
- 下游只输出可审计对象

因此 Stage 2 不再只是“并行生成几个候选公式”，而应被视为 `Hypothesis Expansion Engine`。

对应设计见：

- `../design/authority-model.md`
- `../design/stage-2-hypothesis-expansion.md`

## 3. 系统结构

Pixiu 当前可以用 5 个平面来理解：

| Plane | 作用 | Design Links |
|---|---|---|
| Cognitive Plane | 市场扫描、假设扩展、解释与归纳 | `../design/authority-model.md`, `../design/stage-1-market-context.md`, `../design/stage-2-hypothesis-expansion.md` |
| Deterministic Control Plane | 编排、状态、恢复、审批事件 | `../design/orchestrator.md`, `../design/control-plane.md` |
| Execution Sandbox Plane | 过滤、执行、回测真值 | `../design/stage-3-prefilter.md`, `../design/stage-4-execution.md`, `../design/stage-45-golden-path.md` |
| Artifact & Knowledge Plane | schema、FactorPool、failure constraints、报告对象 | `../design/interface-contracts.md`, `../design/factor-pool.md`, `../design/stage-5-judgment.md` |
| Product Access Plane | CLI、API、Dashboard、用户操作面 | `../design/terminal-dashboard.md`, `../design/test-pipeline.md` |

## 4. 五阶段主链

| Stage | 角色 | 目标 | 主要输出 | Design Links |
|---|---|---|---|---|
| Stage 1 | 宽扫描 | 建立市场上下文和历史提示 | `MarketContextMemo` | `../design/stage-1-market-context.md` |
| Stage 2 | Hypothesis Expansion | 系统性扩张研究假设空间 | 当前为 `FactorResearchNote`，并逐步收敛到 `Hypothesis/StrategySpec` | `../design/stage-2-hypothesis-expansion.md`, `../design/interface-contracts.md` |
| Stage 3 | 前置过滤 | 在昂贵回测前做硬 gate | `FilterReport` / approved notes | `../design/stage-3-prefilter.md`, `../design/interface-contracts.md` |
| Stage 4 | 确定性执行 | 运行可 replay 的执行路径 | 当前为 `BacktestReport`，目标拆为 `BacktestRun + EvaluationReport` | `../design/stage-4-execution.md`, `../design/stage-45-golden-path.md`, `../design/interface-contracts.md` |
| Stage 5 | 结构化判断 | 产出 verdict、沉淀失败约束、形成报告对象 | `CriticVerdict`, `CIOReport` | `../design/stage-5-judgment.md`, `../design/stage-45-golden-path.md` |

## 5. 当前设计地图

如果你想把 overview 中的每个 part 展开阅读，按下面的映射走：

- 权限边界
  - `../design/authority-model.md`
- 接口对象
  - `../design/interface-contracts.md`
- 主编排与控制面
  - `../design/orchestrator.md`
  - `../design/control-plane.md`
- Stage 1-5
  - `../design/stage-1-market-context.md`
  - `../design/stage-2-hypothesis-expansion.md`
  - `../design/stage-3-prefilter.md`
  - `../design/stage-4-execution.md`
  - `../design/stage-5-judgment.md`
  - `../design/stage-45-golden-path.md`
- 数据与知识层
  - `../design/factor-pool.md`
  - `../design/data-sources.md`
- 产品层
  - `../design/terminal-dashboard.md`
  - `../design/test-pipeline.md`
- 组织与扩展层
  - `../design/agent-team.md`
  - `../design/reflection-system.md`
  - `../design/oos-and-generalization.md`
  - `../design/system-bootstrap.md`
  - `../design/commercialization-principles.md`

## 6. 产品定位与早期用户

Pixiu 不应先把自己定义成“直接给投资建议的系统”。

更合理的当前定位是：

- 对外：专属于 LLM 的金融研究团队
- 对内：面向中国市场的 alpha research infrastructure

第一批目标用户也不应是泛投资用户，而应是：

- 陌生但技术强的早期研究用户
- 会写代码
- 懂研究流程
- 希望每周反复使用同一研究系统

这会反过来约束产品设计：

- 核心价值是 repeated research workflow use
- 不是一次性的“推荐哪只票”

## 7. 当前实现状态

截至当前工作树：

- Stage 4→5 最小闭环已存在
- `state_store` 已经出现，控制平面不再完全依赖 graph 内部状态
- richer contracts 已开始进入运行时
- 但 Stage 2 仍然弱于新主张，尚未真正长成 `Hypothesis Expansion Engine`

因此当前主任务不是继续扩展执行层“智能”，而是：

1. 继续收紧 Stage 4/5 的对象边界
2. 把 Stage 2 的探索能力做实
3. 保持 `overview -> design` 的映射始终准确

## 8. 阅读顺序

1. 本文
2. `project-snapshot.md`
3. `spec-execution-audit.md`
4. `../design/README.md`
5. `../design/authority-model.md`
6. `../design/stage-2-hypothesis-expansion.md`
7. `../design/stage-45-golden-path.md`
