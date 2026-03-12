# Design Guide

`docs/design/` 是 Pixiu 当前有效设计的展开层。这里的每篇文档都应当对应 `docs/overview/architecture-overview.md` 中的某个 part。

## Core Reading Order

1. `authority-model.md`
   - 运行时权限边界，回答 “LLM 应该掌什么权”。
2. `interface-contracts.md`
   - 核心 schema 与对象边界。
3. `orchestrator.md`
   - 主编排图和节点职责。
4. `stage-45-golden-path.md`
   - 当前最小闭环和验收标准。
5. `test-pipeline.md`
   - 测试分层和默认验证入口。

## Design Inventory

- Core system
  - `authority-model.md`
  - `interface-contracts.md`
  - `orchestrator.md`
  - `control-plane.md`
  - `factor-pool.md`
  - `data-sources.md`
  - `test-pipeline.md`
- Stage designs
  - `stage-1-market-context.md`
  - `stage-2-hypothesis-expansion.md`
  - `stage-3-prefilter.md`
  - `stage-4-execution.md`
  - `stage-5-judgment.md`
  - `stage-45-golden-path.md`
- Product and organization
  - `terminal-dashboard.md`
  - `agent-team.md`
- Forward-looking extensions
  - `reflection-system.md`
  - `oos-and-generalization.md`
  - `system-bootstrap.md`
  - `commercialization-principles.md`

## Rules

- `design` 文档可以展开实现细节，但必须保持单一主题。
- `design` 负责描述当前有效设计，不负责承担大段迁移背景、实施日志或审计结论。
- 代码与设计的偏差，应优先记录到 `docs/overview/spec-execution-audit.md`，而不是继续堆在 design 正文里。
- 未被 `overview` 引用、且不再指导当前实现的文档，应移动到 `docs/archive/`。
- 工程债、执行计划、阶段任务单不放在这里，统一放到 `docs/plans/`。
