# Docs Guide

这份目录是项目文档的统一入口。后续实现、审阅和协作，默认先从这里开始，而不是直接猜哪篇文档还有效。

## Start Here

1. `docs/overview/README.md`
   - 先理解 `overview` 的职责和阅读顺序。
2. `docs/overview/project-snapshot.md`
   - 如果你只想用一个文件快速理解项目，先读这个。
3. `docs/overview/architecture-overview.md`
   - 当前系统总览；每个一级模块都映射到 `docs/design/`。
4. `docs/design/README.md`
   - 有效设计文档清单和阅读顺序。
5. `docs/overview/spec-execution-audit.md`
   - 判断设计和实现是否一致，先看这里。
6. `docs/design/test-pipeline.md`
   - 测试分层、命令、前置依赖和 merge gate 的统一设计。
7. `docs/plans/current_implementation_plan.md`
   - 当前主线执行计划。

## Directory Map

- `docs/overview/`
  - 项目全貌、当前状态和阅读顺序。
- `docs/design/`
  - 当前有效的设计展开层；`overview` 中的 part 都应在这里展开。
- `docs/plans/`
  - 当前任务、实现计划和工程债。
- `docs/research/`
  - 背景讨论与历史分析。默认不再承载当前真相或参考索引。
- `docs/reference/`
  - 相对稳定的外部知识、论文索引和数据管线参考资料。
- `docs/archive/`
  - 已过时、被替代或仅保留历史价值的文档。默认不直接指导新开发。
- `docs/specs/`
  - 兼容入口；不再承载当前设计真相。

## Rules

- 需要理解项目时，先看 `docs/overview/README.md` 和 `docs/overview/architecture-overview.md`。
- 需要展开某个模块时，再进入 `docs/design/` 对应文档。
- 当设计与代码不一致时，以 `docs/overview/spec-execution-audit.md` 的结论为准，先修设计路径，再做实现。
- `docs/archive/` 中的内容只用于追溯历史决策，不应再被当作当前架构的依据。
