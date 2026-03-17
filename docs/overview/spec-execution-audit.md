# Spec Execution Audit

> 创建：2026-03-09 | 更新时间：2026-03-17
> 说明：建立”哪些设计能直接指导当前实现”的统一判断口径。

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
| `architecture-overview.md` | active | 当前系统总览入口 |
| `authority-model.md` | active | 权限边界主设计，明确“扩大 hypothesis space，不扩大 execution power” |
| `interface-contracts.md` | implemented/partial | 已明确 canonical objects 与 transitional objects，但代码主干仍主要消费兼容对象 |
| `orchestrator.md` | implemented/partial | 主图已存在，且已开始写入最小 control-plane state |
| `control-plane.md` | implemented/partial | 最小 `state_store` 已落地，但稳定读模型和审计面仍未完全收口 |
| `stage-1-market-context.md` | implemented/partial | Stage 1 已进入主干 |
| `stage-2-hypothesis-expansion.md` | implemented | 五子空间已全部实现：ConstraintChecker/RegimeFilter/SynthesisAgent/SymbolicMutator/RegimeDetector，SubspaceScheduler Thompson Sampling 完整，327 smoke/unit tests 通过 |
| `stage-3-prefilter.md` | implemented/partial | 主过滤链已实现，Filter D (ConstraintChecker) + Filter E (RegimeFilter) 已完成，invalid_regimes 检查已对接 |
| `stage-4-execution.md` | implemented/partial | 已收敛到 `src/execution/` 主路径，report contract 仍未完全收口 |
| `stage-5-judgment.md` | implemented/partial | canonical runtime 已收敛到 `src/agents/judgment.py`，FailureMode enum 9 种完全对齐，CriticVerdict.regime_at_judgment 字段已添加，`critic.py / factor_pool_writer.py / cio_report_renderer.py` 仅保留兼容职责 |
| `stage-45-golden-path.md` | active | 当前 Stage 4→5 收口入口 |
| `factor-pool.md` | implemented/partial | richer metadata 写回已完成，FactorPoolRecord.subspace_origin 已加入，register_factor() 传入 note 参数并写入溯源信息 |
| `data-sources.md` | planned/partial | 免费数据主干已存在，扩展数据源尚未收口 |
| `terminal-dashboard.md` | planned/partial | CLI/API 最小实现已有，Dashboard 未开始 |
| `agent-team.md` | active | Agent 角色与边界已拆出 |
| `reflection-system.md` | planned | 尚未进入主运行时 |
| `oos-and-generalization.md` | planned | 验证层前瞻 |
| `system-bootstrap.md` | planned | 冷启动与断点设计，依赖更完整控制平面 |
| `commercialization-principles.md` | exploratory | 商业边界前瞻，不阻塞当前工程 |
| `test-pipeline.md` | active | 默认 pytest 入口已可用 |
| `../plans/engineering-debt.md` | active | 当前工程债清单 |
| `../archive/specs/island_scheduler_spec.md` | archive | 已退出主入口 |
| `../archive/specs/skills_architecture_spec.md` | archive | 已退出主入口 |

## 关键结论

### 1. 当前主风险不是“没有 runtime”，而是“边界仍在漂移”

Stage 4→5 的最小闭环已经出现，控制平面也已有最小雏形。当前更大的问题是：

- richer contracts 仍有兼容层
- Stage 2 仍弱于最新主张
- 产品层与控制平面还未完全对齐
- canonical object set 刚完成设计层收口，但运行时尚未正式迁移到 `Hypothesis / StrategySpec / FailureConstraint`

### 2. Stage 2 已经成为新的架构重点

随着 authority model 收口，原本散落在执行层和 agent theatre 里的“聪明感”必须回到上游。

因此当前最该补的不是再给执行层加智能，而是把 `stage-2-hypothesis-expansion.md` 和 `interface-contracts.md` 对应的对象边界真正做实。

### 3. 文档入口已经改为 `overview + design`

当前默认入口应固定为：

1. `docs/README.md`
2. `docs/overview/README.md`
3. `docs/overview/architecture-overview.md`
4. `docs/design/README.md`
5. `docs/design/stage-45-golden-path.md`
6. `docs/design/test-pipeline.md`

### 4. 测试规格已经建立，但真实环境闭环仍未完成

本地 `smoke/unit` 和 `integration` 已经可用，但 `live / e2e / CI` 还没有完全收口。

## 推荐执行顺序

1. ✅ 保持 `overview -> design` 映射准确。
2. ✅ 已完成：Stage 2 升级为 `Hypothesis Expansion Engine`（Phase 2 完成，327 tests 通过）。
3. ✅ 已完成：Phase 3A 完成 richer contract 收紧（CriticVerdict.failure_mode/regime_at_judgment/decision，FactorPoolRecord.subspace_origin，_diagnose_failure() 返回类型统一）。
4. 扩展控制平面，直到 CLI/API 的数据面稳定。
5. 数据源扩展（NARRATIVE_MINING + REGIME_CONDITIONAL 特征量）与代码清理（归档兼容层）。
6. 最后推进 Dashboard、MiroFish 协议层和真实环境闭环。
