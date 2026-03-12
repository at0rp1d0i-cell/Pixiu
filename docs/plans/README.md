# Plans Guide

`docs/plans/` 用来放“会变化的执行文档”，而不是长期架构真相。

## 适合放在这里的文件

- `current_implementation_plan.md`
  - 当前主线实现计划
- `agent_team_operating_model.md`
  - root / worker / reviewer / explorer 的协作规则和时间盒
- `2026-03-09-interface-readiness-audit.md`
  - 正式启动 MVP 前的外部接口与环境变量审计基线
- `engineering-debt.md`
  - 当前已知工程债清单
- 仍在指导当前工作的临时专题计划
  - 例如尚未完成的收口计划或准备清单

## 已归档

以下类型的文档已经移到 `docs/archive/plans/`：

- 已完成的设计稿
- 已完成的 implementation plan
- 失效的 `current_tasks` 类清单
- 只用于追溯历史决策过程的计划文档

## 不适合放在这里的内容

- 长期架构设计
- interface contract
- 稳定的测试规范

这些应该留在 `docs/design/` 或 `docs/overview/`。

## 约定

- `task.md` / `implementation_plan.md` 不建议直接放仓库根目录。
- 推荐统一收纳在 `docs/plans/`，并使用带语义的文件名。
- 当计划完成或失效时，应移动到 `docs/archive/plans/` 或删除，而不是长期堆积。
- `docs/plans/` 中的文档应该少而硬；如果只是背景说明，优先进入 `docs/research/` 或 `docs/reference/`。
