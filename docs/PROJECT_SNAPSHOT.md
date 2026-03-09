# Project Snapshot

这是“用一个文件看懂整个项目”的入口。

---

## 1. 项目是什么

Pixiu 是一个面向中国 A 股的 LLM-native Alpha 研究平台。它不是让 AI 模仿传统量化团队，而是围绕 Agent 的优势重新设计研究流程：

- 并行生成假设
- 漏斗式前置过滤
- 确定性执行回测
- 结构化评判与知识沉淀
- 人类只在 CIO 审批点介入

主架构入口见：

- `docs/specs/v2_architecture_overview.md`

---

## 2. 当前代码状态

### 已有主干

- `src/schemas/`
  - v2 的核心 schema 基本已经成型
- `src/core/orchestrator.py`
  - 12 节点 LangGraph 主图已存在
- `src/execution/`
  - Stage 4 执行层基础设施已经存在
- `src/factor_pool/`
  - FactorPool v2 API 已部分扩展
- `src/cli/` / `src/api/`
  - 已有最小 CLI 和 API 入口

### 当前最大缺口

- Stage 4
  - execution 层存在，但 orchestrator 仍有旧接口残留
- Stage 5
  - schema 已在，运行时实现没有真正落地
- Dashboard
  - 规格存在，前端基本未开始
- 测试管线
  - 已有测试文件，但没有完全收敛的测试基础设施与 CI 口径

详细审计见：

- `docs/specs/v2_spec_execution_audit.md`
- `docs/specs/v2_stage45_golden_path.md`

---

## 3. 规格执行结果

当前可以把项目状态分成四类：

- `已落主干`
  - schema
  - orchestrator 骨架
  - prefilter 主链路
  - execution 基础设施
- `部分落地`
  - FactorPool v2
  - CLI/API
  - Stage 1 / Stage 2
- `漂移`
  - Stage 4
  - Stage 5
- `前瞻规划`
  - reflection system
  - OOS/generalization
  - bootstrap
  - commercialization

如果只问一句“验收结果到底如何”：

> 架构方向和 schema 基本成型，但运行时闭环还没有完全收口；目前最接近可执行的部分是 Stage 1-4 的前半段，而 Stage 4/5 的最后收口仍是当前主任务。

---

## 4. 推荐阅读顺序

1. `docs/specs/v2_architecture_overview.md`
2. `docs/specs/v2_interface_contracts.md`
3. `docs/specs/v2_stage45_golden_path.md`
4. `docs/specs/v2_spec_execution_audit.md`
5. `docs/specs/v2_test_pipeline.md`
6. `docs/specs/v2_agent_team.md`
7. `docs/specs/v2_orchestrator.md`
8. `docs/specs/v2_stage4_execution.md`
9. `docs/specs/v2_stage5_judgment.md`

---

## 5. 文档体系怎么用

- `docs/specs/`
  - 当前有效规格
- `docs/plans/`
  - 短中期执行计划、任务清单
- `docs/research/`
  - 讨论与阶段报告
- `docs/reference/`
  - 背景资料
- `docs/archive/`
  - 历史文档、旧规格、AI 工作底稿

---

## 6. 当前建议优先级

1. 收敛 Stage 4 的唯一执行路径
2. 落 Stage 5 的 deterministic MVP
3. 把测试管线落实成真实 pytest 配置和 marker
4. 再推进控制平面与 Dashboard

当前用于 Stage 4→5 收口的主规格：

- `docs/specs/v2_stage45_golden_path.md`
