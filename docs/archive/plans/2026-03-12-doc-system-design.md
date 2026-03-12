# Doc System Redesign

> 日期：2026-03-12
> 主题：将当前混合的 `docs/specs/ + docs/root + archive` 体系收敛为 `overview + design + archive`

## 目标

建立一套更稳定的文档层级：

- `overview`
  - 项目整体概述、当前状态、阅读顺序
- `design`
  - 对 `overview` 中每个 part 的展开设计
- `archive`
  - 历史文档、旧规格、AI 工作底稿、已退出主入口的材料

## 核心约束

1. `overview` 中出现的一级模块，必须能在 `design` 中找到对应文档。
2. `design` 中仍然有效的文档，必须被某个 `overview` 文档引用。
3. 不再让 `research / archive / 旧 specs` 参与默认阅读顺序。
4. `plans` 只描述执行计划和工程债，不再承载架构真相。

## 目标结构

```text
docs/
  README.md
  overview/
    README.md
    project-snapshot.md
    architecture-overview.md
    spec-execution-audit.md
  design/
    README.md
    authority-model.md
    interface-contracts.md
    orchestrator.md
    stage-1-market-context.md
    stage-2-hypothesis-expansion.md
    stage-3-prefilter.md
    stage-4-execution.md
    stage-5-judgment.md
    stage-45-golden-path.md
    factor-pool.md
    data-sources.md
    terminal-dashboard.md
    agent-team.md
    reflection-system.md
    oos-and-generalization.md
    system-bootstrap.md
    commercialization-principles.md
    test-pipeline.md
  plans/
  reference/
  research/
  archive/
```

## 本轮范围

- 迁移当前活跃主规格到 `overview/` 和 `design/`
- 重写主入口和阅读顺序
- 将 `Stage 2` 从“并行假设生成”重述为 “Hypothesis Expansion Engine”
- 将 `docs/specs/archive/` 并入 `docs/archive/specs/`
- 将 `v2_misc_todos.md` 迁入 `docs/plans/engineering-debt.md`

## 不在本轮完成

- 全量重写每篇设计文档
- 全部代码注释和测试注释的路径统一
- 基于新结构再做一轮架构实现

## 验收标准

1. `docs/README.md` 只给出新的主入口。
2. `overview` 文档中的核心 part 都能跳到 `design`。
3. `docs/specs/` 不再承载当前设计真相，只保留兼容入口。
4. 主入口不再默认引导用户进入 `archive`、`research` 或旧路径。
