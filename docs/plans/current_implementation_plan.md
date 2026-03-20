# Current Implementation Plan

Status: active
Owner: coordinator
Last Reviewed: 2026-03-20

> 更新时间：2026-03-20
> 来源：`docs/overview/05_spec-execution-audit.md`、`docs/design/25_stage-45-golden-path.md`

---

## 目标

把 Pixiu 从“主干闭环可运行但数据与能力边界仍漂移”的状态，推进到“Stage 2-5 合约更一致、数据能力真实可见、实验可解释”的状态。
并继续完成 authority model 收口：LLM 负责认知，deterministic 系统负责执行真值。

---

## 当前阶段

### Phase A: 文档与入口收敛

- [x] 建立 `docs/README.md`
- [x] 建立 `docs/overview/README.md` 与 `docs/design/README.md`
- [x] 建立规格执行审计
- [x] 建立测试管线设计
- [x] 拆分旧总览文档中过重主题
- [x] 建立 Stage 4→5 golden path 收口规格
- [x] 完成 docs reorganization，默认阅读路径已收口

### Phase B: Stage 4 收口

- [x] 明确 `src/execution/` 为唯一执行路径
- [x] 清理 orchestrator 中旧 coder 接口
- [x] 明确 `BacktestReport` 的唯一生成方式（最小版）
- [x] 对应补 execution integration tests

### Phase C: Stage 5 MVP

- [x] 实现 deterministic `Critic`
- [x] 打通 `FactorPool.register_factor` 的最小写回路径
- [x] 生成最小 `CIOReport`
- [x] 明确 `src/agents/judgment/` 包为唯一 Stage 5 主路径，旧 Stage 5 文件降级为兼容层

注：当前已经落下 deterministic `Critic / RiskAuditor / PortfolioManager / ReportWriter` 的最小运行时，但 richer contract 和控制平面还未完成。

### Phase D: 测试基础设施

- [x] 配置 pytest 入口，无需手工 `PYTHONPATH`
- [x] 注册 marker：`smoke/unit/integration/live/e2e`
- [x] 显式 primary marker 已收口，`tests/conftest.py` 不再自动补 `unit/live/e2e`
- [x] 将实验脚本隔离出默认 pytest 收集路径
- [ ] 收敛 async 测试的长期策略：继续同步包装或正式引入 `pytest-asyncio`

### Phase E: 控制平面与产品层

- [x] 设计并落最小 `state_store`
- [x] 收敛 CLI/API 到稳定数据面的最小读路径
- [ ] 再考虑 Dashboard 落地

### Phase F: 实验可观测性

- [x] `round_*.json` 已补充 prefilter / execution / judgment 级别的诊断摘要
- [x] 可直接区分 Stage 3 拒绝、Stage 4 执行、Stage 5 verdict 的主要失败来源
- [ ] 如有需要，再决定是否把这批 round telemetry 上推到 control plane

### Phase G: 数据能力收口（进行中）

- [x] 新增 runtime capability manifest，Stage 2/3 按本地 Qlib 覆盖率动态决定字段可用性
- [x] `fina_indicator -> Qlib bins` 转换链已打通，`$roe` 已可进入 runtime 可用字段集合
- [x] `daily_basic` 下载与转换链已建立（`pb / pe_ttm / turnover_rate / float_mv`）
- [x] `daily_basic` 全量下载已完成（`5490 / 5490`），尾项失败已补跑成功
- [x] `pb / pe_ttm / turnover_rate / float_mv` 已全部达到 runtime coverage 阈值并进入 Stage 2/3 可用字段列表
- [x] `moneyflow_hsgt` 下载脚本已建立，可作为下一批 Stage 1 / regime 资金流数据
- [x] `moneyflow` / `stk_limit` staging 下载脚本已建立，进入 P1 数据面准备阶段
- [x] Tushare 下载脚本已内建 localhost proxy 清理，避免本地失效代理导致批量下载中断
- [ ] `moneyflow` / `stk_limit` 的真实下载与后续接入顺序仍待执行
- [ ] 再次运行 Phase 4B 实验前，需确认扩展字段覆盖率与 Docker Stage 4 blocker 都已收口

### Phase H: 独立重构 Epic（进行中）

- [ ] `Test Pipeline Refactor`
  - 见 `docs/plans/2026-03-20-test-pipeline-refactor-design.md`
  - 实施计划：`docs/plans/2026-03-20-test-pipeline-refactor-implementation.md`
  - 这是 `FactorPool Boundary Refactor` 与 `Orchestrator Boundary Refactor` 的前置 gate
  - [x] Slice 1：canonical docs / marker truth 对齐
  - [x] Slice 2：test harness stabilization（explicit marker、`sys.path` 清理、重型 smoke 归类、live/e2e runtime env gating 已完成）
  - [x] Slice 3：approval / entrypoint / FactorPool / readiness 高价值 contract tests
- [ ] `Data Capability Platform Refactor`
  - 见 `docs/plans/2026-03-19-data-capability-platform-refactor-design.md`
  - 第一批实施计划：`docs/plans/2026-03-19-data-capability-platform-refactor-implementation.md`
  - [x] Slice 1：canonical formula capability kernel（field/operator manifest + 错误示例清理）
  - [x] Slice 2：formula-exposed dataset registry + readiness（`qlib_price_volume / fina_indicator / daily_basic`）
  - [ ] Slice 3：扩展到 non-formula dataset readiness 与 Stage 1 / regime data reporting
- [ ] `FactorPool Boundary Refactor`
  - 见 `docs/plans/2026-03-19-factor-pool-boundary-refactor-design.md`
  - [x] Slice 1：storage/bootstrap wiring 已抽出到 `src/factor_pool/storage.py`
  - [ ] Slice 2：write/query/constraint façade delegation 与文档收口
- [ ] `Orchestrator Boundary Refactor`
  - 见 `docs/plans/2026-03-19-orchestrator-boundary-refactor-design.md`
  - [x] Slice 1：`config.py / runtime.py / control_plane.py` 已进入主干，package root 保持 compatibility façade
  - [ ] Slice 2：剩余 caller/doc seam 收口与 facade 进一步瘦身
- [ ] 总顺序与依赖控制
  - 见 `docs/plans/2026-03-19-refactor-roadmap.md`

### Phase 2: Hypothesis Expansion Engine ✅

- [x] FailureConstraint schema（9 种 FailureMode：N_SHORT/N_MID/N_LONG/O_SHORT/O_MID/O_LONG/DRIFT/REGIME_MISMATCH/CONSTRAINT_VIOLATION）
- [x] ConstraintExtractor（Stage 5 产生约束），ConstraintChecker/Filter D（Stage 3 消费）
- [x] RegimeFilter / Filter E（invalid_regimes 检查，假设失效 regime 过滤）
- [x] SynthesisAgent（TF-IDF 去重 threshold=0.85，scipy 因子家族聚类）
- [x] SymbolicMutator（5 种算子：SWAP_HORIZON/CHANGE_NORMALIZATION/REMOVE_OPERATOR/ADD_OPERATOR/ALTER_INTERACTION，AST 运行时）
- [x] RegimeDetector（5 种 regime 规则：BULL/BEAR/RANGING/HIGH_VOL/LIQUIDITY_CRISIS，detect/detect_from_signals 双入口）
- [x] SubspaceScheduler Thompson Sampling 反馈回路（loop_control_node 调用 update_state，WARM_START_THRESHOLD=30）
- [x] 327 smoke/unit tests 通过，现有 e2e 测试继续通过

### Phase 3A: 合约收紧 ✅

- [x] CriticVerdict.failure_mode → Optional[FailureMode]（field_validator 向后兼容未来 None 值）
- [x] CriticVerdict.regime_at_judgment: Optional[str]（判断时的 market regime 上下文）
- [x] CriticVerdict.decision → Literal["promote","archive","reject","retry"]（明确决策枚举）
- [x] _diagnose_failure() 直接返回 Optional[FailureMode]（删除 _FAILURE_MODE_MAP bridge，消除二次解析）
- [x] FactorPoolRecord.subspace_origin: Optional[str]（假设来源子空间溯源）
- [x] Stage 5 → FactorPool 端到端 `subspace_origin` 写回（`register_factor()` 已通过 `note` 完成主路径写回）
- [x] factor_pool_writer.py factor_spec None guard（处理历史兼容对象）

### Phase 3B（计划）: 代码清理

- [x] 兼容层清理已完成：旧 Stage 5 shim、重复 schema 定义和 legacy re-export wrapper 已在 phase3b 删除

### Phase 3C（计划）: 数据源扩展

- [ ] NARRATIVE_MINING 子空间：接入新闻/公告文本数据源（当前优先走 Stage 1 消费，Stage 2 直连需 Researcher 工具化）
- [ ] Researcher 工具化升级：为 `AlphaResearcher` 增加 MCP / tool calling 能力
- [ ] regime 基础设施层：扩展特征量（资金流向、估值分位、波动率结构等）
- [ ] CROSS_MARKET：美股/港股/商品价格信号对齐与 pattern transfer

### Phase 3D（计划）: MiroFish 协议层

- [ ] NarrativePrediction schema（MiroFish 预测结果契约）
- [ ] MiroFishAdapter（离线快照加载 + 两层解析，符合 point-in-time 防前视）
- [ ] MarketContextMemo.narrative_predictions 字段注入
- [ ] NARRATIVE_MINING 子空间注入 MiroFish 预测作为上下文增强

---

## 当前验收结论

当前已经不是“Stage 4/5 没落地”，而是：

- 方向明确
- schema 基本成型
- Stage 4/5 最小闭环已经可运行、可回归
- 默认测试入口已经稳定
- 最小 control-plane state_store 已经落地
- richer contract 已开始进入主干，但仍处在新旧字段双轨期
- 当前主任务已经转为三条主线
- 测试体系已从“支持开发”升级为“后续 B/C 重构的前置 gate”
- 数据能力收口与下载链稳定化
- Researcher 技能/工具边界继续收口
- richer contract、控制平面和产品层继续推进
