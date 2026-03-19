# Plans Guide

`docs/plans/` 用来放“会变化的执行文档”，而不是长期架构真相。

## 适合放在这里的文件

- `current_implementation_plan.md`
  - 当前主线实现计划
- `engineering-debt.md`
  - 当前已知工程债清单
- `2026-03-18-phase4-experiment-plan.md`
  - 当前 Phase 4B 受控实验计划
- `2026-03-18-mirofish-integration-analysis.md`
  - 当前 MiroFish Go/No-Go 决策参考（更像决策备忘，不是实施计划）
- `2026-03-19-data-capability-alignment-design.md`
  - 当前数据能力收口设计
- `2026-03-19-data-capability-alignment-implementation.md`
  - 当前数据能力收口实施计划
- `2026-03-19-refactor-roadmap.md`
  - 三个独立 architecture epic 的总路线图
- `2026-03-19-data-capability-platform-refactor-design.md`
  - 数据能力平台化重构设计
- `2026-03-19-factor-pool-boundary-refactor-design.md`
  - FactorPool 边界拆分设计
- `2026-03-19-orchestrator-boundary-refactor-design.md`
  - orchestrator 包边界重构设计
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

最近已归档的例子：

- `2026-03-18-docs-reorganization-design.md`
- `2026-03-18-docs-reorganization-implementation-plan.md`
- `2026-03-19-experiment-round-observability-implementation.md`
- `agent_team_operating_model.md`
- `2026-03-18-rss-mcp-spec.md`
- `2026-03-19-multi-agent-skills-expansion-design.md`
- `2026-03-19-skills-expansion-implementation.md`
- `2026-03-19-tushare-p1-expansion-implementation.md`

## 不适合放在这里的内容

- 长期架构设计
- interface contract
- 稳定的测试规范
- 长期协作规则

这些应该留在 `docs/design/`、`docs/overview/` 或仓库根部的 `AGENTS.md`。

## 约定

- `task.md` / `implementation_plan.md` 不建议直接放仓库根目录。
- 推荐统一收纳在 `docs/plans/`，并使用带语义的文件名。
- 当计划完成或失效时，应移动到 `docs/archive/plans/` 或删除，而不是长期堆积。
- `docs/plans/` 中的文档应该少而硬；如果只是背景说明，优先进入 `docs/futures/`、`docs/research/` 或 `docs/reference/`。
