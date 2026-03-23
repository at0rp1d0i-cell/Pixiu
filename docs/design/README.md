# Design Guide

`docs/design/` 是 Pixiu 当前有效设计的展开层。默认先读 `docs/overview/`，再进入这里。

这里的每篇文档都应当对应 `docs/overview/03_architecture-overview.md` 中的某个 part。

## Core Reading Order

1. `10_authority-model.md`
   - 运行时权限边界，回答 “LLM 应该掌什么权”。
2. `11_interface-contracts.md`
   - 核心 schema 与对象边界。
3. `12_orchestrator.md`
   - 主编排图和节点职责。
4. `25_stage-45-golden-path.md`
   - 当前最小闭环和验收标准。
5. `16_test-pipeline.md`
   - 测试分层和默认验证入口。

## Design Inventory

- Core system
  - `10_authority-model.md`
  - `11_interface-contracts.md`
  - `12_orchestrator.md`
  - `13_control-plane.md`
  - `14_factor-pool.md`
  - `15_data-sources.md`
  - `16_test-pipeline.md`
- Stage designs
  - `20_stage-1-market-context.md`
  - `21_stage-2-hypothesis-expansion.md`
  - `22_stage-3-prefilter.md`
  - `23_stage-4-execution.md`
  - `24_stage-5-judgment.md`
  - `25_stage-45-golden-path.md`
- Product and organization
  - `30_agent-team.md`

未来方向已经开始从这里分流到 `docs/futures/`，避免“当前有效设计”和“未来路线”混在同一层。

## Rules

- 编号只在 `design/` 目录内用于局部阅读顺序，不代表跨目录全局顺序。
- `design` 文档可以展开实现细节，但必须保持单一主题。
- `design` 负责描述当前有效设计，不负责承担大段迁移背景、实施日志或审计结论。
- 代码与设计的偏差，应优先记录到 `docs/overview/05_spec-execution-audit.md`，而不是继续堆在 design 正文里。
- 未被 `overview` 引用、且不再指导当前实现的文档，应移动到 `docs/archive/`。
- 工程债、执行计划、阶段任务单不放在这里，统一放到 `docs/plans/`。
- 尚未进入当前运行时、但值得保留的前瞻设计，应优先移动到 `docs/futures/`。
