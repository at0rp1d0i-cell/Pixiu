# Plans Guide

`docs/plans/` 用来放“会变化的执行文档”，而不是长期架构真相。

## 适合放在这里的文件

- `current_implementation_plan.md`
  - 当前主线实现计划
- `current_tasks.md`
  - 可执行任务清单
- 临时专题计划
  - 例如 `stage4_convergence_plan.md`

## 不适合放在这里的内容

- 长期架构设计
- interface contract
- 稳定的测试规范

这些应该留在 `docs/specs/`。

## 约定

- `task.md` / `implementation_plan.md` 不建议直接放仓库根目录。
- 推荐统一收纳在 `docs/plans/`，并使用带语义的文件名。
- 当计划完成或失效时，应移动到 `docs/archive/` 或删除，而不是长期堆积。
