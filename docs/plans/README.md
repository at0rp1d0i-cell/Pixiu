# Plans Guide

`docs/plans/` 用来放“会变化的执行文档”，而不是长期架构真相。

## 适合放在这里的文件

- `current_implementation_plan.md`
  - 当前主线实现计划
- `2026-03-18-docs-reorganization-design.md`
  - 当前文档整编设计
- `2026-03-18-docs-reorganization-implementation-plan.md`
  - 当前文档整编实施计划
- `agent_team_operating_model.md`
  - root / worker / reviewer / explorer 的协作规则和时间盒
- `engineering-debt.md`
  - 当前已知工程债清单
- `2026-03-18-rss-mcp-spec.md`
  - 当前 RSS / MCP 扩展规格
- `2026-03-18-phase4-experiment-plan.md`
  - 当前 Phase 4B 受控实验计划
- `2026-03-18-mirofish-integration-analysis.md`
  - 当前 MiroFish Go/No-Go 决策参考
- 仍在指导当前工作的临时专题计划
  - 例如尚未完成的收口计划或准备清单

## 已归档

以下类型的文档已经移到 `docs/archive/plans/`：

- 已完成的设计稿
- 已完成的 implementation plan
- 已被后续重构吸收的阶段计划
- 只剩历史价值的审计基线
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
- `docs/plans/` 中的文档应该少而硬；如果只是背景说明，优先进入 `docs/futures/`、`docs/research/` 或 `docs/reference/`。
