# Spec Execution Audit

Purpose: Record which design docs are active truth, which are partially implemented, and where code and docs still drift.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-27

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
| `12_orchestrator.md` | implemented/partial | 主图已存在，且已开始写入最小 control-plane state；主图已拆分为包（src/core/orchestrator/），当前已引入 `config.py / runtime.py / control_plane.py`，并保留 package-root compatibility facade；审批链已切到 `report -> human_gate` + control-plane 决策轮询 |
| `13_control-plane.md` | implemented/partial | 最小 `state_store` 已落地，但当前运行真相仍更多存在于 round artifact；control plane 读面明显落后于 harness/profile/artifact 真相 |
| `20_stage-1-market-context.md` | implemented/partial | Stage 1 已进入 `blocking core prefetch + async enrichment` 主干；当前 `pixiu run` / `doctor` / `preflight` / live tests 已对齐到同一套 layered env truth，当前已知 Tushare blocking-core 路径不再在 controlled single 入口直接 degraded |
| `21_stage-2-hypothesis-expansion.md` | implemented/partial | FormulaSketch Lite、factor gene、anti-collapse、grounding claim 已进入主干；`fast_feedback` 局部面已收敛，但 controlled run 仍存在大规模 `novelty/alignment/validator` waste，且 `approved -> low_sharpe` 显示 value density 仍不足 |
| `22_stage-3-prefilter.md` | implemented/partial | 主过滤链已实现，且当前不再是主瓶颈；Stage 3 现在更多是在暴露上游 Stage 2 contract/value-density 问题，而不是自己卡主链 |
| `23_stage-4-execution.md` | implemented/partial | 已收敛到 `src/execution/` 主路径，并有最小 discovery/OOS split；但 validation runtime 仍是 MVP，walk-forward/PIT/A 股执行约束还未闭环 |
| `24_stage-5-judgment.md` | implemented/partial | canonical runtime 收敛到 `src/agents/judgment/` 包，`candidate -> promote` 语义已进入主线；当前 Stage 5 主要在忠实暴露 `low_sharpe`，但 risk/judgment 诊断仍偏薄，尚不能充分解释价值不足的根因 |
| `25_stage-45-golden-path.md` | active | 当前 Stage 4→5 收口入口 |
| `14_factor-pool.md` | implemented/partial | richer metadata 写回已进入主干，FactorPoolRecord.subspace_origin 已加入，register_factor() 已支持 note 参数，Stage 5 judgment_node 已传入 note，subspace_origin 已进入主路径写回；register() 废弃方法已彻底删除（零调用者），硬编码阈值全部迁移到 THRESHOLDS 单例；当前已抽出 `storage.py / factor_writer.py / queries.py / similarity.py / constraint_store.py`，`pool.py` 正在收口为 façade |
| `15_data-sources.md` | implemented/partial | 价量 + `roe` + `daily_basic` 扩展字段已进入 runtime capability；下一步更重要的是把 `moneyflow_hsgt` / `margin` 这类结构化聚合信号收口为 Stage 1 blocking core 真值，而不是继续依赖漂移的在线替代接口 |
| `../futures/35_cli-and-dashboard.md` | planned/partial | 已移出 active design 层；CLI/API 最小实现已有，但更完整的 Dashboard 仍未开始 |
| `30_agent-team.md` | active | Agent 角色与边界已拆出 |
| `../futures/reflection-system.md` | planned | 已移出 active design 层；尚未进入主运行时 |
| `../futures/oos-and-generalization.md` | planned | 已移出 active design 层；属于验证层前瞻 |
| `../futures/system-bootstrap.md` | planned | 已移出 active design 层；依赖更完整控制平面 |
| `../futures/commercialization-principles.md` | exploratory | 已移出 active design 层；属于商业边界前瞻 |
| `16_test-pipeline.md` | active | 默认 pytest 入口已可用，但当前项目健康已明显依赖 `doctor/preflight/harness/artifact` 证据，而不只是 pytest；测试规格需要继续从“pytest 基线”升级到“runtime evidence 基线” |
| `../plans/engineering-debt.md` | active | 当前工程债清单 |
| `../archive/specs/island_scheduler_spec.md` | archive | 已退出主入口 |
| `../archive/specs/skills_architecture_spec.md` | archive | 已退出主入口 |

这份审计文档只处理“设计与实现是否对齐”。

对于当前主线里**被明确接受**的运行时让步、实验特判、MVP 简化和延期实现，请改看 [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)。

## 关键结论

### 1. 当前不是“跑不起来”，而是“局部健康、整体主线失真”

最新 runtime 证据已经把系统切成两部分：

- `fast_feedback`
  - 已足够做工程验证
  - `Stage 2/3` 局部面基本健康
  - 当前主问题是 `approved -> low_sharpe`
- `controlled single`
  - `Stage 1 live closure` 已落地
  - 但整体仍不健康
  - `Stage 2` 仍有大规模 `novelty/alignment/validator` waste
  - `Stage 5` 仍以 `low_sharpe` 为主死因

因此当前主风险不是“没有 runtime”，而是：

- `fast_feedback` 容易被误判成全管线健康
- `default/controlled` 仍携带 experiment concession
- settings / harness / artifact / control plane 的真相分层还不够清楚

### 2. 当前主瓶颈已经从 gate/contract 漂到 live truth、value density 和 validation

当前最重要的三件事是：

- 维持 `Stage 1 live closure`，不要让 env truth / blocking-core 路径再次漂移
- controlled-run `Stage 2` 的 novelty waste、JSON robustness 和 `approved -> low_sharpe` value density
- `candidate -> promote` 的 validation runtime closure

这意味着旧优先级已经失效：

- 现在不该把“Stage 2 直连更多数据源”排在最前
- 也不该继续把主要精力放在 Stage 3 prompt/contract 微调
- 更不该把 throughput 优化放在 validation closure 之前

### 3. 文档入口已经改为 `overview + design`

当前默认入口应固定为：

1. `docs/README.md`
2. `docs/overview/01_project-snapshot.md`
3. `docs/overview/02_codebase-map.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/04_current-state.md`
6. `docs/overview/05_spec-execution-audit.md`
7. `docs/design/README.md`

### 4. 测试规格已经建立，但“健康”必须看 runtime evidence

本地 `smoke/unit` 和 `integration` 已经可用，但当前健康判断必须同时看：

- `doctor/preflight/harness`
- round artifact
- `fast_feedback` 与 `controlled single` 的漏斗差异
- `candidate -> promote` 是否真正闭环

pytest 现在是必要条件，不再是充分条件。

## 推荐执行顺序

1. 先做 truth reset：更新 canonical docs、主线优先级、profile 边界和 runtime concessions。
2. 保持 `Stage 1 live closure`：不要回退 `pixiu run` env truth、blocking tool discovery 和 live test 真相口径。
3. 继续做 `controlled-run Stage 2 closure`：重点收 novelty waste、JSON robustness、`approved -> low_sharpe`。
4. 再做 `validation closure`：让 `candidate -> promote` 进入真实 runtime，并继续补 OOS / walk-forward / PIT / A 股执行边界。
5. 之后再做 throughput/cost 优化；不要在 validation closure 前优先做性能优化。
6. `Stage 2` 工具化、MiroFish、Dashboard、更广数据面扩展均后置到主线稳定之后。
