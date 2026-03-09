# Archive Guide

这里存放历史文档、草稿、被新规格替代的实施单，以及 AI 工作底稿。

## Archive Layout

- `legacy/`
  - 早期架构设计和路线图草稿，已被 Pixiu v2 规格替代。
- `docs4ai/`
  - AI 工作底稿和一次性实现材料，保留供追溯，不作为当前开发入口。
- `../specs/archive/`
  - 旧规格或已被吸收的实施文档，例如早期 `island_scheduler` / `skills_architecture`。

## What Is Already Archived

- 早期总体设计稿：`legacy/`
- 旧 AI 工作底稿：`docs4ai/`
- 被主规格吸收的专题规格：`docs/specs/archive/`

## Usage Rules

- 仅在需要追溯历史决策、旧实现背景或早期实验结论时查阅。
- 不要直接依据 archive 中的文档新增功能或修改主流程。
- 如果 archive 文档中的信息仍然重要，应先提升到 `docs/specs/` 或 `docs/reference/`，而不是继续在 archive 中引用。
