# Pixiu Architecture Overview

Purpose: Explain Pixiu's system boundary, five-stage structure, and major design planes without diving into implementation detail.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-23

## 1. First-principles Definition

Pixiu 的第一性定义是：

> 一个面向 A 股市场的 `alpha research OS`，负责持续生成、收缩、执行、淘汰并沉淀 alpha hypotheses。

产品和架构的语言分层如下：

- 系统本体：`alpha research OS`
- 对内运行隐喻：`LLM-native quant research team`
- 对外产品隐喻：`A 股 alpha 私人农场（前台收机会，后台跑研究）`

在系统边界上，它首先是研究基础设施，而不是投顾壳。

## 2. Architecture Direction

当前最重要的架构判断不是“继续增强执行层智能”，而是：

> 不扩大 `execution power`，扩大 `hypothesis space`。

因此：

- 上游允许更强探索
- 中游必须严格收缩
- 下游只消费结构化、可审计对象

Stage 2 的地位因此明显上升，它不再只是“多生成几个候选”，而是 `Hypothesis Expansion Engine`。

## 3. Five Planes

| Plane | 作用 | 当前对应 |
|---|---|---|
| Cognitive Plane | 市场扫描、假设扩展、解释与归纳 | Stage 1-2 agents |
| Deterministic Control Plane | 编排、状态、恢复、审批事件 | orchestrator + control plane |
| Execution Sandbox Plane | 过滤、执行、回测真值 | Stage 3-4 |
| Artifact & Knowledge Plane | schema、FactorPool、failure constraints、报告对象 | schemas + factor pool + Stage 5 |
| Product Access Plane | 当前用户入口 | CLI/API 最小形态 |

## 4. Five-stage Mainline

| Stage | 角色 | 当前主要输出 |
|---|---|---|
| Stage 1 | 宽扫描 | `MarketContextMemo` |
| Stage 2 | Hypothesis Expansion | `FactorResearchNote`，并逐步收敛到 `Hypothesis/StrategySpec` |
| Stage 3 | Prefilter | `FilterReport` / approved notes |
| Stage 4 | Deterministic Execution | `BacktestReport` |
| Stage 5 | Judgment | `CriticVerdict`, `CIOReport` |

## 5. Design Map

如果你想从系统总览继续往下钻，按这个映射读：

- 权限边界：
  - `../design/10_authority-model.md`
- 对象边界：
  - `../design/11_interface-contracts.md`
- 编排与控制面：
  - `../design/12_orchestrator.md`
  - `../design/13_control-plane.md`
- Stage 设计：
  - `../design/20_stage-1-market-context.md`
  - `../design/21_stage-2-hypothesis-expansion.md`
  - `../design/22_stage-3-prefilter.md`
  - `../design/23_stage-4-execution.md`
  - `../design/24_stage-5-judgment.md`
  - `../design/25_stage-45-golden-path.md`
- 知识层：
  - `../design/14_factor-pool.md`
  - `../design/15_data-sources.md`
- 测试与组织：
  - `../design/16_test-pipeline.md`
  - `../design/30_agent-team.md`

## 6. Current Shape of the System

截至当前工作树：

- Stage 4→5 最小闭环已存在
- `state_store` 已出现，控制平面不再完全依赖 graph 内部状态
- richer contracts 已大体进入运行时
- Stage 2 的子空间运行时已经进入主干
- 但 `AlphaResearcher` 仍是纯 LLM 调用，尚不能直接消费 RSS / MCP 新数据源
- `subspace_origin` 已进入主路径写回，但 richer metadata 仍在继续收口

## 7. Best Next Reads

1. `04_current-state.md`
2. `05_spec-execution-audit.md`
3. `../design/README.md`
4. `../design/10_authority-model.md`
5. `../design/21_stage-2-hypothesis-expansion.md`
6. `../design/25_stage-45-golden-path.md`
