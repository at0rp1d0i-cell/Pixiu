# Spec Execution Audit

Purpose: Record which design docs are active truth, which are partially implemented, and where code and docs still drift.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-20

建立“哪些设计能直接指导当前实现”的统一判断口径。

## 状态定义

- `active`
  - 当前主设计，可直接指导开发。
- `implemented/partial`
  - 代码主干已落地，但仍有缺口或兼容层。
- `planned`
  - 设计存在，但实现尚未成体系。
- `exploratory`
  - 前瞻设计，不阻塞当前主线。
- `archive`
  - 历史文档，不再作为当前入口。

## 审计矩阵

| Design | Status | 结论 |
|---|---|---|
| `03_architecture-overview.md` | active | 当前系统总览入口 |
| `10_authority-model.md` | active | 权限边界主设计，明确“扩大 hypothesis space，不扩大 execution power” |
| `11_interface-contracts.md` | implemented | 已明确 canonical objects 与 transitional objects，但代码主干仍主要消费兼容对象；Stage I/O TypedDicts 已建立（src/schemas/stage_io.py），12个节点返回类型全部收紧为 partial update，{**state} 扩散已消除 |
| `12_orchestrator.md` | implemented/partial | 主图已存在，且已开始写入最小 control-plane state；主图已拆分为包（src/core/orchestrator/），graph.py/nodes/**/_context.py 分离；当前审批链已切到 `report -> human_gate` + control-plane 决策轮询 |
| `13_control-plane.md` | implemented/partial | 最小 `state_store` 已落地，但稳定读模型和审计面仍未完全收口 |
| `20_stage-1-market-context.md` | implemented/partial | Stage 1 已进入主干 |
| `21_stage-2-hypothesis-expansion.md` | implemented/partial | 四个活跃子空间（FACTOR_ALGEBRA / SYMBOLIC_MUTATION / CROSS_MARKET / NARRATIVE_MINING）与 regime 基础设施层已进入主干；ConstraintChecker/RegimeFilter/SynthesisAgent/SymbolicMutator/RegimeDetector 已落地，SubspaceScheduler Thompson Sampling 完整；但 AlphaResearcher 仍为纯 LLM 调用，Stage 2 对 MCP/RSS 的主动消费路径尚未收口 |
| `22_stage-3-prefilter.md` | implemented/partial | 主过滤链已实现，Filter D (ConstraintChecker) + Filter E (RegimeFilter) 已完成，invalid_regimes 检查已对接；Validator 已开始消费 runtime capability manifest 与算子签名检查 |
| `23_stage-4-execution.md` | implemented/partial | 已收敛到 `src/execution/` 主路径，report contract 仍未完全收口 |
| `24_stage-5-judgment.md` | implemented/partial | canonical runtime 收敛到 `src/agents/judgment/` 包，FailureMode enum 9 种完全对齐，CriticVerdict.regime_at_judgment 字段已添加；`execution_succeeded` 已进入 report/pool 语义层，但仍有旧 `passed` 兼容字段需要继续收口 |
| `25_stage-45-golden-path.md` | active | 当前 Stage 4→5 收口入口 |
| `14_factor-pool.md` | implemented | richer metadata 写回已进入主干，FactorPoolRecord.subspace_origin 已加入，register_factor() 已支持 note 参数，Stage 5 judgment_node 已传入 note，subspace_origin 已进入主路径写回；register() 废弃方法已彻底删除（零调用者），硬编码阈值全部迁移到 THRESHOLDS 单例 |
| `15_data-sources.md` | implemented/partial | 价量 + `roe` + `daily_basic` 扩展字段已进入 runtime capability；其余数据源继续分层推进 |
| `../futures/terminal-dashboard.md` | planned/partial | 已移出 active design 层；CLI/API 最小实现已有，但更完整的 Dashboard 仍未开始 |
| `30_agent-team.md` | active | Agent 角色与边界已拆出 |
| `../futures/reflection-system.md` | planned | 已移出 active design 层；尚未进入主运行时 |
| `../futures/oos-and-generalization.md` | planned | 已移出 active design 层；属于验证层前瞻 |
| `../futures/system-bootstrap.md` | planned | 已移出 active design 层；依赖更完整控制平面 |
| `../futures/commercialization-principles.md` | exploratory | 已移出 active design 层；属于商业边界前瞻 |
| `16_test-pipeline.md` | active | 默认 pytest 入口已可用；当前 smoke/unit 基线为 527 passed，CLI smoke 与 approval 注入口径已补；但 marker 分层、全局状态隔离和 contract test 仍在 Test Pipeline Refactor 中收口 |
| `../plans/engineering-debt.md` | active | 当前工程债清单 |
| `../archive/specs/island_scheduler_spec.md` | archive | 已退出主入口 |
| `../archive/specs/skills_architecture_spec.md` | archive | 已退出主入口 |

## 关键结论

### 1. 当前主风险不是“没有 runtime”，而是“边界仍在漂移”

Stage 4→5 的最小闭环已经出现，控制平面也已有最小雏形。当前更大的问题是：

- richer contracts 仍有兼容层
- AlphaResearcher 仍缺 MCP / tool calling 能力，新数据源尚不能被 Stage 2 主动消费
- 产品层与控制平面还未完全对齐
- canonical object set 刚完成设计层收口，但运行时尚未正式迁移到 `Hypothesis / StrategySpec / FailureConstraint`
- canonical test entry 已存在，CLI / approval 的 smoke 路径已补齐；但测试分层、marker 体系和全局状态隔离仍有漂移，真实链路仍需 live / e2e 校验

### 2. Stage 2 已经成为新的架构重点

随着 authority model 收口，原本散落在执行层和 agent theatre 里的“聪明感”必须回到上游。

因此当前最该补的不是再给执行层加智能，而是把 `21_stage-2-hypothesis-expansion.md` 和 `11_interface-contracts.md` 对应的对象边界真正做实。

### 3. 文档入口已经改为 `overview + design`

当前默认入口应固定为：

1. `docs/README.md`
2. `docs/overview/01_project-snapshot.md`
3. `docs/overview/02_codebase-map.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/04_current-state.md`
6. `docs/overview/05_spec-execution-audit.md`
7. `docs/design/README.md`

### 4. 测试规格已经建立，但测试基础设施仍需重构

本地 `smoke/unit` 和 `integration` 已经可用，但仍有三类缺口：

- `live / e2e / CI` 还没有完全收口
- marker 与文档现实存在过渡兼容层
- orchestrator 全局状态、审批链 contract、FactorPool 写路径还需要更强测试护栏

## 推荐执行顺序

1. ✅ 保持 `overview -> design` 映射准确。
2. ✅ 已完成：Stage 2 的结构化 subspace runtime 已进入主干（四个活跃子空间 + regime 基础设施层）。
3. ✅ 已完成：Phase 3A 完成 richer contract 收紧（CriticVerdict.failure_mode/regime_at_judgment/decision，FactorPoolRecord.subspace_origin，_diagnose_failure() 返回类型统一）。
4. ✅ 已完成：Phase 3 模块化收口（orchestrator/judgment 包拆分，Stage I/O TypedDicts，{**state} 扩散消除，测试42→20文件/405通过，THRESHOLDS 单例统一，register() 废弃删除）
5. 扩展控制平面，直到 CLI/API 的数据面稳定。
6. 数据源扩展（NARRATIVE_MINING + regime 特征量）与 Researcher 工具化升级，之后再清理兼容层。
7. 最后推进 Dashboard、MiroFish 协议层和真实环境闭环。
