# Archive Guide

这里存放历史文档、草稿、被新规格替代的实施单，以及 AI 工作底稿。

## Archive Layout

- `legacy/`
  - 早期架构设计和路线图草稿，已被 Pixiu v2 规格替代。
- `docs4ai/`
  - AI 工作底稿和一次性实现材料，保留供追溯，不作为当前开发入口。
- `reports/`
  - 一次性实施总结、重构报告和阶段性交付说明。
- `specs/`
  - 已退出主入口的旧规格，例如早期 `island_scheduler` / `skills_architecture`。
- `plans/`
  - 已完成或失效的设计稿、implementation plan 和旧任务清单。
- `research/`
  - 已退出主入口的阶段实验报告和历史研究记录。

## What Is Already Archived

- 早期总体设计稿：`legacy/`
- 旧 AI 工作底稿：`docs4ai/`
- 一次性实施总结与重构报告：`reports/`
- 被主设计吸收的专题规格：`specs/`
- 已完成或失效的计划材料：`plans/`
- 历史实验与阶段研究报告：`research/`

## Usage Rules

- 仅在需要追溯历史决策、旧实现背景或早期实验结论时查阅。
- 不要直接依据 archive 中的文档新增功能或修改主流程。
- 如果 archive 文档中的信息仍然重要，应先提升到 `docs/design/`、`docs/overview/` 或 `docs/reference/`，而不是继续在 archive 中引用。
