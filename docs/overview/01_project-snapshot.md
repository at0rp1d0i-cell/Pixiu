# Project Snapshot

Purpose: Give the shortest trustworthy definition of Pixiu, its current posture, and what a new reader should understand first.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

## 1. What Pixiu Is

Pixiu 应当同时用两句话理解：

- 对外：一个专属于 LLM 的金融研究团队
- 对内：一个面向 A 股市场的 `alpha research OS`

它的目标不是先做投顾外壳，而是先形成一套可持续生成、筛选、执行、淘汰和沉淀 alpha hypotheses 的研究基础设施。

## 2. What Pixiu Is Not

- 不是“每天给一条投资建议”的产品
- 不是把执行层越做越聪明的自动交易壳
- 不是只会吐自由文本结论的研究助手

Pixiu 的核心产物是 research objects、evaluation artifacts 和 failure constraints。

## 3. What Exists Today

当前已经有主干的部分：

- `src/schemas/`：核心 schema 与 Stage I/O 合约
- `src/core/orchestrator/`：12 节点主编排图
- `src/execution/`：Stage 4 确定性执行主路径
- `src/agents/judgment/`：Stage 5 判断层包
- `src/control_plane/state_store.py`：最小控制平面存储
- `tests/`：默认 `smoke/unit` 与本地 `integration` 入口

## 4. Biggest Current Gaps

- Stage 2 仍缺主动 MCP/tool access
- 数据源扩展还没真正进入 Stage 2 主消费路径
- 控制平面仍是 MVP，不是稳定读模型
- `subspace_origin` 写回仍未完全端到端收口
- 产品层仍以 CLI/API 最小形态为主

## 5. Core Architectural Judgment

当前最重要的架构判断是：

> 不扩大 `execution power`，扩大 `hypothesis space`。

这意味着：

- Stage 2 承担更多探索能力
- Stage 3/4/5 承担更硬的收缩、执行和裁决
- 下游只消费结构化、可审计对象

## 6. Best Next Reads

1. `02_codebase-map.md`
2. `03_architecture-overview.md`
3. `04_current-state.md`
4. `05_spec-execution-audit.md`
5. `../design/README.md`
