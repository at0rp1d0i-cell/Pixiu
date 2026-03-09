# Specs Guide

`docs/specs/` 只保留当前 Pixiu v2 的有效规格入口。一次性实施单、旧阶段任务单和被新规格吸收的文档已经移到 `docs/specs/archive/`。

## Reading Order

1. `v2_architecture_overview.md`
   - 主架构总览，先确认系统边界、阶段划分和产品形态。
2. `v2_interface_contracts.md`
   - 所有核心 schema 和 Agent 间接口契约。
3. `v2_orchestrator.md`
   - 编排层、节点顺序和中断点设计。
4. `v2_stage45_golden_path.md`
   - 当前 Stage 4→5 的唯一收口规格，先看最小闭环和验收边界。
5. `v2_stage1_market_context.md` → `v2_stage5_judgment.md`
   - 分阶段规格。
6. `v2_factorpool.md`
   - 持久化和检索层规格。
7. `v2_terminal_dashboard.md`
   - CLI/API/Dashboard 产品层规格。
8. `v2_agent_team.md`
   - Agent 团队、职责边界和 Skills 关系。
9. `v2_reflection_system.md`
   - 跨轮反思、元反思与永久 Skills 的分层设计。
10. `v2_oos_and_generalization.md`
   - LLM 偏差防御、OOS 边界和泛化验证。
11. `v2_system_bootstrap.md`
   - 冷启动、断点和启动节奏设计。
12. `v2_commercialization_principles.md`
   - 影响架构边界的商业化原则。
13. `v2_test_pipeline.md`
   - 测试规范和验证口径。
14. `v2_spec_execution_audit.md`
   - 规格执行情况审计和漂移说明。
15. `v2_misc_todos.md`
   - 已知工程债和收尾事项。

## Status Index

| Spec | Status | Notes |
|---|---|---|
| `v2_architecture_overview.md` | active | 当前架构主入口 |
| `v2_interface_contracts.md` | active | schema 已基本成型 |
| `v2_orchestrator.md` | partial | 主图已落地，Stage 4/5 有漂移 |
| `v2_stage45_golden_path.md` | active | Stage 4→5 当前唯一收口入口 |
| `v2_stage1_market_context.md` | partial | 代码和测试已出现 |
| `v2_stage2_hypothesis_generation.md` | partial | batch generation 已落地，Synthesis 未完成 |
| `v2_stage3_prefilter.md` | implemented/partial | 核心过滤链路已实现 |
| `v2_stage4_execution.md` | drift | execution 层和 orchestrator 接口分叉 |
| `v2_stage5_judgment.md` | drift | schema 在，运行时实现缺失 |
| `v2_factorpool.md` | partial | v2 API 已补，collection/schema 仍有差异 |
| `v2_terminal_dashboard.md` | partial | CLI/API 已有最小实现，Dashboard 未开始 |
| `v2_agent_team.md` | active | Agent 边界、角色分组和 Skills 关系入口 |
| `v2_reflection_system.md` | planned | 已从 overview 拆出，尚未进入运行时 |
| `v2_oos_and_generalization.md` | planned | 验证层前瞻设计 |
| `v2_system_bootstrap.md` | planned | 启动和断点节奏设计 |
| `v2_commercialization_principles.md` | exploratory | 商业化边界前瞻，不阻塞当前工程 |
| `v2_data_sources.md` | planned/partial | 数据源扩展尚未收口 |
| `v2_test_pipeline.md` | active | 新增，作为后续 CI 和测试治理入口 |
| `v2_spec_execution_audit.md` | active | 规格执行现状基线 |
| `v2_misc_todos.md` | active | 工程债清单 |

## Archive

以下文档已移至 `docs/specs/archive/`：

- `island_scheduler_spec.md`
- `skills_architecture_spec.md`

这些文档仍有历史价值，但不再作为当前主规格入口。
