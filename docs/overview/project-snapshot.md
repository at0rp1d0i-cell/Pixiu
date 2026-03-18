# Project Snapshot

> 更新时间：2026-03-18

这是”用一个文件看懂整个项目”的入口。

## 1. 项目定义

Pixiu 当前应当同时用两句话理解：

- 对外：一个专属于 LLM 的金融研究团队
- 对内：一个面向中国市场的 `alpha research OS`

它的目标不是先做成投顾外壳，而是先形成一套可持续生成、筛选、执行、淘汰和沉淀 alpha hypotheses 的研究基础设施。

## 2. 现在做到哪里了

### 已有主干

- `src/schemas/`
  - 核心 schema 已基本成型
- `src/core/orchestrator/`
  - 主编排图已拆分为包（graph.py + nodes/ + _context.py），Stage I/O TypedDicts 覆盖全部12个节点
- `src/execution/`
  - Stage 4 确定性执行主路径已接入主链
- `src/agents/judgment.py`
  - Stage 5 deterministic MVP 已存在
- `src/schemas/stage_io.py`
  - 12个 Stage I/O TypedDict，节点返回类型完全收紧
- `src/control_plane/`
  - 最小 `state_store` 已出现
- `tests/`
  - 默认 `smoke/unit` 与本地 `integration` 入口已可用

### 当前最大缺口

- 数据源仍以 AKShare 宏观数据为主；Stage 2 子空间缺少专项数据支撑（Narrative Mining 缺新闻/公告；Regime Conditional 缺更丰富 regime 特征量）
- 控制平面仍是 MVP（state_store 最小实现，无稳定读模型）
- SubspaceScheduler Thompson Sampling 缺乏多轮 track record 积累（cold start 期）
- FailureConstraint cold start：首轮无约束，Filter D 形同虚设
- 产品层仍停留在 CLI/API 最小实现

## 3. 当前最重要的架构判断

目前项目最关键的修正是：

> 不扩大 `execution power`，扩大 `hypothesis space`。

这意味着：

- Stage 2 承担更多探索能力
- Stage 3/4/5 承担更硬的收缩、执行和裁决
- 下游只消费结构化、可审计对象

## 4. 文档体系

- `docs/overview/`
  - 项目是什么、当前到哪、应该先读什么
- `docs/design/`
  - `overview` 中每个 part 的展开设计
- `docs/plans/`
  - 会变化的执行计划和工程债
- `docs/research/`
  - 历史讨论和背景分析
- `docs/reference/`
  - 稳定外部参考资料
- `docs/archive/`
  - 历史文档和旧规格

## 5. 推荐阅读顺序

1. `architecture-overview.md`
2. `spec-execution-audit.md`
3. `../design/README.md`
4. `../design/authority-model.md`
5. `../design/stage-2-hypothesis-expansion.md`
6. `../design/stage-45-golden-path.md`
7. `../design/test-pipeline.md`

## 6. 目标用户和验证方向

当前更合理的早期验证目标，不是“谁愿意立刻付费”，而是：

- 几个陌生但技术强的早期用户
- 每周反复回来用它做研究

因此产品的第一价值应该是：

- 帮用户持续推进研究工作流
- 而不是每天输出一句投资建议

## 7. 当前优先级

1. ~~重构文档体系，保证 `overview -> design` 映射准确~~ ✅ Phase A 已完成
2. ~~将 Stage 2 从”并行假设生成”升级为 `Hypothesis Expansion Engine`~~ ✅ Phase 2 已完成（327 smoke/unit tests 通过）
3. ~~继续收紧 `BacktestReport / CriticVerdict / FactorPoolRecord`~~ ✅ Phase 3A 已完成（FailureMode 对齐、regime_at_judgment 字段、decision 枚举、subspace_origin 溯源）
4. ~~Phase 3 模块化收口~~：orchestrator/judgment 包拆分，Stage I/O TypedDicts，测试42→20文件，THRESHOLDS 单例，register() 删除 ✅ Phase 3 已完成
5. 数据源扩展：NARRATIVE_MINING（新闻/公告）+ REGIME_CONDITIONAL（更多 regime 特征量）优先
6. ~~代码清理：归档兼容层（critic.py / factor_pool_writer.py / cio_report_renderer.py / schemas.py / factor_pool_record.py）~~ ✅ 已完成（phase3b 全部删除）
7. MiroFish 协议层（NarrativePrediction schema + MiroFishAdapter）与控制平面扩展
8. 最后再补 live / e2e 和更完整的产品壳
