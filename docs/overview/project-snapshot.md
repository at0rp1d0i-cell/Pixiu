# Project Snapshot

这是“用一个文件看懂整个项目”的入口。

## 1. 项目定义

Pixiu 当前应当同时用两句话理解：

- 对外：一个专属于 LLM 的金融研究团队
- 对内：一个面向中国市场的 `alpha research OS`

它的目标不是先做成投顾外壳，而是先形成一套可持续生成、筛选、执行、淘汰和沉淀 alpha hypotheses 的研究基础设施。

## 2. 现在做到哪里了

### 已有主干

- `src/schemas/`
  - 核心 schema 已基本成型
- `src/core/orchestrator.py`
  - 主编排图已存在
- `src/execution/`
  - Stage 4 确定性执行主路径已接入主链
- `src/agents/judgment.py`
  - Stage 5 deterministic MVP 已存在
- `src/control_plane/`
  - 最小 `state_store` 已出现
- `tests/`
  - 默认 `smoke/unit` 与本地 `integration` 入口已可用

### 当前最大缺口

- Stage 2 还没有真正成为 `Hypothesis Expansion Engine`
- richer contracts 仍处于新旧字段双轨期
- 控制平面还只是 MVP
- 产品层仍停留在 CLI/API 最小可见实现
- live / e2e 仍未形成稳定闭环

## 3. 当前最重要的架构判断

目前项目最关键的修正是：

> 不扩大 `execution power`，扩大 `hypothesis space`。

这意味着：

- Stage 2 承担更多探索能力
- Stage 3/4/5 承担更硬的收缩、执行和裁决
- 下游只消费结构化、可审计对象

## 4. 文档体系

- `docs/overview/`
  - 项目是什么、当前到哪、应该先读什么
- `docs/design/`
  - `overview` 中每个 part 的展开设计
- `docs/plans/`
  - 会变化的执行计划和工程债
- `docs/research/`
  - 历史讨论和背景分析
- `docs/reference/`
  - 稳定外部参考资料
- `docs/archive/`
  - 历史文档和旧规格

## 5. 推荐阅读顺序

1. `architecture-overview.md`
2. `spec-execution-audit.md`
3. `../design/README.md`
4. `../design/authority-model.md`
5. `../design/stage-2-hypothesis-expansion.md`
6. `../design/stage-45-golden-path.md`
7. `../design/test-pipeline.md`

## 6. 目标用户和验证方向

当前更合理的早期验证目标，不是“谁愿意立刻付费”，而是：

- 几个陌生但技术强的早期用户
- 每周反复回来用它做研究

因此产品的第一价值应该是：

- 帮用户持续推进研究工作流
- 而不是每天输出一句投资建议

## 7. 当前优先级

1. 重构文档体系，保证 `overview -> design` 映射准确
2. 将 Stage 2 从“并行假设生成”升级为 `Hypothesis Expansion Engine`
3. 继续收紧 `BacktestReport / CriticVerdict / FactorPoolRecord`
4. 扩展控制平面到更稳定的数据面
5. 最后再补 live / e2e 和更完整的产品壳
