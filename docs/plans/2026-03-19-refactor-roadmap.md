# Refactor Roadmap

Status: active
Owner: coordinator
Last Reviewed: 2026-03-19

Purpose: Define the next three standalone architecture refactors, their ordering, and their dependency boundaries.

---

## Why Separate Epics

Pixiu 当前的技术债已经不适合用一个“大一统重构”处理。真正的风险不在于某个热点文件过长，而在于多个热点同时跨越：

- 数据能力边界
- FactorPool 读写职责
- orchestrator 包运行时边界

如果三块一起改，会同时影响：

- Stage 2/3 生成与过滤契约
- Stage 5 写回路径
- CLI / API / graph / control plane

这会让回归范围过宽，也会让实验窗口被长时间冻结。

因此推荐拆成三条可独立推进的 epic。

---

## Recommended Sequence

### Epic A — Data Capability Platform

先做。

原因：

- 当前最直接影响实验质量
- 刚好衔接 `daily_basic` 下载完成后的能力收口
- 可在不触碰主 graph 语义的前提下显著减少 token 浪费

### Epic B — FactorPool Boundary

第二个做。

原因：

- 当前是最大的维护热点
- 但作用域比 orchestrator 更局部
- 适合在数据能力清晰后，再收口写入与查询契约

### Epic C — Orchestrator Boundary

最后做。

原因：

- 改动面最广
- 牵涉 CLI / API / graph / control plane / tests
- 应该建立在前两个 epic 已经收口的数据与存储边界上

---

## Dependency Rules

- Epic A 不依赖 Epic B/C
- Epic B 依赖 Epic A 的 capability truth 已稳定
- Epic C 不必须等待 Epic B 完全结束，但推荐在 Epic B 主写回边界收口后进行

---

## Shared Non-Goals

以下内容不应在这轮三 epic 里顺手扩张：

- 不重做产品层 UI
- 不引入新的 memory stack（如 mem0 / GraphRAG runtime）
- 不扩大 execution layer 智能性
- 不把 Stage 3 hard gate 改成更“聪明”的软判断
- 不在 orchestrator 重构时改变 Stage 1-5 业务语义

---

## Acceptance Gates

### Gate 1: Data Capability Platform complete

- 下载、staging、normalize、runtime capability 暴露有单一真相源
- Stage 2/3/skills 不再各自维护字段可用性

### Gate 2: FactorPool Boundary complete

- `pool.py` 不再同时承担 bootstrap / write / archive / constraint / query 全部职责
- Stage 5 写回路径唯一化

### Gate 3: Orchestrator Boundary complete

- `src/core/orchestrator/__init__.py` 不再承载多角色混合职责
- CLI / API 对 runtime config / run context / graph factory 的依赖更显式

---

## Deliverables

本路线图配套 3 份独立设计文档：

- `docs/plans/2026-03-19-data-capability-platform-refactor-design.md`
- `docs/plans/2026-03-19-factor-pool-boundary-refactor-design.md`
- `docs/plans/2026-03-19-orchestrator-boundary-refactor-design.md`
