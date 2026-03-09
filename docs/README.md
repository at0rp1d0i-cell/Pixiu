# Docs Guide

这份目录是项目文档的统一入口。后续实现、审阅和协作，默认先从这里开始，而不是直接凭文件名猜测哪篇文档还有效。

## Start Here

1. `docs/PROJECT_SNAPSHOT.md`
   - 如果你只想用一个文件快速理解项目，先读这个。
2. `docs/specs/README.md`
   - 当前有效规格的阅读顺序和状态说明。
3. `docs/specs/v2_architecture_overview.md`
   - Pixiu v2 的架构总览，当前主规格入口。
4. `docs/specs/v2_stage45_golden_path.md`
   - 当前 Stage 4→5 唯一收口路径，先看最小闭环和验收边界。
5. `docs/specs/v2_spec_execution_audit.md`
   - 规格和实现的一致性审计；判断某篇规格是否还能直接指导开发时，先看这里。
6. `docs/specs/v2_test_pipeline.md`
   - 测试分层、命令、前置依赖和 merge gate 的统一规格。
7. `docs/plans/current_implementation_plan.md`
   - 当前主线执行计划。

## Directory Map

- `docs/specs/`
  - 当前有效的实现规格和状态文档。只有这里的 `active` 文档可以直接指导开发。
- `docs/plans/`
  - 当前任务和实现计划，适合放 `task` / `implementation_plan` 一类文件。
- `docs/research/`
  - 讨论记录、阶段报告、历史分析。可用于理解来龙去脉，但不是单一事实来源。
- `docs/reference/`
  - 相对稳定的外部知识和数据管线参考资料，作为背景材料使用。
- `docs/archive/`
  - 已过时、被替代或仅保留历史价值的文档。默认不直接指导新开发。

## Rules

- 需要实现功能时，先看 `docs/specs/README.md`，再看对应规格。
- 如果只想快速理解项目，先看 `docs/PROJECT_SNAPSHOT.md`。
- 当规格与代码不一致时，以 `docs/specs/v2_spec_execution_audit.md` 的结论为准，先修规格路径，再做实现。
- `docs/archive/` 中的内容只用于追溯历史决策，不应再被当作当前架构的依据。
