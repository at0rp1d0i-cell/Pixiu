# Pixiu v2 规格执行审计

> 创建：2026-03-09
> 目的：建立“规格是否已落地”的统一判断口径，作为后续整理、实现和拆分任务的基线。

---

## 状态定义

- `active`
  - 当前主规格，能直接指导开发。
- `implemented/partial`
  - 主干已经落地，但仍有缺口或兼容层。
- `drift`
  - 规格和实现发生分叉，继续执行前必须先收敛路径。
- `planned`
  - 规格存在，但实现尚不成体系。
- `archive`
  - 历史文档，不再作为当前开发入口。

---

## 审计矩阵

| Spec | Status | 结论 |
|---|---|---|
| `v2_architecture_overview.md` | active | 当前主规格入口，系统目标和阶段划分清晰 |
| `v2_interface_contracts.md` | implemented/partial | `src/schemas/` 基本齐全，`AgentState` 等核心模型已落地 |
| `v2_orchestrator.md` | implemented/partial | 12 节点骨架存在，但 Stage 4/5 接口已漂移 |
| `v2_stage45_golden_path.md` | active | 当前 Stage 4→5 收口入口，定义最小闭环和验收边界 |
| `v2_stage1_market_context.md` | implemented/partial | MarketAnalyst / LiteratureMiner 已进入代码主干 |
| `v2_stage2_hypothesis_generation.md` | implemented/partial | batch generation 已有；Synthesis 仍未完成 |
| `v2_stage3_prefilter.md` | implemented/partial | Validator / Novelty / Alignment 主链路已实现并有测试 |
| `v2_stage4_execution.md` | drift | execution 子系统已建，但 orchestrator 仍调用旧 coder 接口 |
| `v2_stage5_judgment.md` | drift | judgment schema 已建，运行时实现缺失，orchestrator 已提前耦合 |
| `v2_factorpool.md` | implemented/partial | v2 API 已补，但 collection 命名和 schema 仍有兼容痕迹 |
| `v2_terminal_dashboard.md` | planned/partial | CLI/API 有最小实现，Dashboard 和 state persistence 未开始 |
| `v2_agent_team.md` | active | Agent 团队与职责边界已从 overview 中拆出 |
| `v2_reflection_system.md` | planned | 架构前瞻，尚未进入主运行时 |
| `v2_oos_and_generalization.md` | planned | 验证层前瞻规格，未进入主链路 |
| `v2_system_bootstrap.md` | planned | 冷启动与断点设计，依赖控制平面 |
| `v2_commercialization_principles.md` | exploratory | 架构边界前瞻，不是当前阻塞项 |
| `v2_data_sources.md` | planned/partial | 免费数据源主干已有，宏观/基本面/新闻扩展未收口 |
| `v2_misc_todos.md` | active | 当前工程债清单，应保留在主规格层 |
| `archive/island_scheduler_spec.md` | archive | 已被 v2 orchestrator / architecture 规格吸收 |
| `archive/skills_architecture_spec.md` | archive | 已被当前 knowledge/skills + loader 实现吸收 |

---

## 关键结论

### 1. Schema 层比运行时更接近 v2

`src/schemas/` 已经基本覆盖 v2 契约，说明项目的“数据结构设计”先于“运行时收敛”。这很好，但也意味着目前最大问题不是 schema 缺失，而是 orchestrator 仍在调用旧路径。

### 2. Stage 4 和 Stage 5 是当前最大的漂移源

- Stage 4 规格要求以 `src/execution/` 取代旧 `src/agents/coder.py`。
- 当前 `src/execution/` 已存在，但 `src/core/orchestrator.py` 仍在调用旧的 `generate_backtest_code` / `run_backtest` 路径。
- Stage 5 规格要求 `src/agents/judgment.py` 承载 `Critic / RiskAuditor / PortfolioManager / ReportWriter`。
- 当前 schema 已有，但运行时模块缺失，`orchestrator` 已经产生无效导入点。
- 因此当前应以 `v2_stage45_golden_path.md` 作为收口主规格，而不是直接按完整 Stage 5 目标形态推进。

### 3. 产品层是“最小可见实现”，不是完整闭环

CLI 和 API 已经能展示 FactorPool 摘要，但还不是完整的 `CIOReport`、持久化状态管理和 Dashboard 数据面。产品层规格目前应视为 `planned/partial`，不能误判为“已交付”。

### 4. 文档体系此前缺少单一入口

旧设计稿、研究讨论、AI 工作底稿和当前 v2 规格混放在一起，导致阅读成本高、真假难辨。本次整理后，默认入口应固定为：

1. `docs/README.md`
2. `docs/specs/README.md`
3. `docs/specs/v2_architecture_overview.md`
4. `docs/specs/v2_stage45_golden_path.md`
5. `docs/specs/v2_test_pipeline.md`

### 5. 测试是缺失的横切面规格

仓库中已经有测试文件，但没有统一的测试分层、前置依赖、命令入口和 merge gate 口径。测试管线必须上升为规格，否则后续每个阶段都会重复出现“代码写了、测试方式不统一、CI 无法定义”的问题。

---

## 推荐执行顺序

1. 冻结文档入口和状态矩阵。
2. 冻结测试管线规格。
3. 以 `v2_stage45_golden_path.md` 冻结 Stage 4→5 最小闭环。
4. 收敛 Stage 4 的唯一执行路径。
5. 落 Stage 5 deterministic MVP，再决定是否继续扩展完整 judgment stack。
6. 再推进 Dashboard 和数据源扩展。
