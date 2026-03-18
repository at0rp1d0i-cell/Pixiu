# Pixiu v2 Control Plane Design
Purpose: Define the stable runtime data plane for runs, approvals, artifacts, and audit state.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.0
> 角色：稳定定义运行态、审批记录和报告索引的数据面
> 前置依赖：`12_orchestrator.md`、`25_stage-45-golden-path.md`、`16_test-pipeline.md`

---

## 1. 目标

`control plane` 的职责是把运行态从 LangGraph 内部状态和 `FactorPool` 摘要中剥离出来，形成一个稳定的外部读模型。

第一版只解决三件事：

1. 让 orchestrator 能持久化当前 run 的状态
2. 让 CLI / API 能读取稳定的状态和报告索引
3. 让 human approval 有可追踪的记录面

## 2. 边界

`FactorPool` 继续负责知识平面，不承担控制平面职责。

控制平面只负责：

- run 状态
- snapshot 摘要
- artifact 索引
- human decision 记录

它不负责：

- 因子知识检索
- 长文本反思
- 组合分析知识沉淀

## 3. 第一版对象

### `RunRecord`

- `run_id`
- `mode`
- `status`
- `current_round`
- `current_stage`
- `started_at`
- `finished_at`
- `last_error`

### `RunSnapshot`

- `run_id`
- `approved_notes_count`
- `backtest_reports_count`
- `verdicts_count`
- `awaiting_human_approval`
- `updated_at`

### `ArtifactRecord`

- `run_id`
- `kind`
- `ref_id`
- `path`
- `created_at`

第一版 `kind` 只要求：

- `backtest_report`
- `cio_report`

### `HumanDecisionRecord`

- `run_id`
- `action`
- `created_at`

## 4. 当前实现选择

第一版采用本地 `SQLite-backed minimal state store`。

原因：

- 单机研发足够稳
- 不需要新服务
- 比 JSON store 更适合列表查询
- 后续可抽象成 storage adapter

## 5. 模块关系

- `src/control_plane/state_store.py`
  - 当前最小存储实现
- `src/schemas/control_plane.py`
  - 控制平面 schema
- `src/core/orchestrator/`
  - 关键节点写 run / snapshot / artifact
- `src/api/server.py`
  - 优先读取稳定状态和报告索引
- `src/cli/main.py`
  - `status / report` 优先走控制平面

## 6. 设计原则

1. orchestrator 只写 store，不把 graph internals 暴露给产品层
2. CLI / API 读控制平面，不直接猜运行态
3. schema 保持小而硬，不复制一个胖版 `AgentState`
4. 控制平面失败时要显式暴露，不伪装成正常状态

## 7. 后续方向

当前 `control plane` 仍是 MVP。后续扩展重点应是：

- 更完整的 artifact refs
- run history
- human decision 审计面
- Dashboard 可消费的数据模型
- 与 checkpoint 恢复语义的更严密对齐
