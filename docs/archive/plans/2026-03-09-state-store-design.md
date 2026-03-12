# State Store Design

> 日期：2026-03-09
> 关联规格：`docs/specs/v2_stage45_golden_path.md`、`docs/specs/v2_test_pipeline.md`、`docs/specs/v2_spec_execution_audit.md`

---

## 目标

为 Pixiu 增加一个最小 `state_store`，把控制平面从 LangGraph 内部状态和 `FactorPool` 摘要里剥离出来。

第一版只解决三件事：

1. 让 orchestrator 能持久化“当前 run 在做什么”
2. 让 CLI / API 能读取稳定的运行状态与报告索引
3. 让 human approval 有明确的记录面，而不是只靠 graph 内部注入

---

## 为什么现在做

当前代码已经有 Stage 4→5 的最小闭环，但控制平面仍然是碎片化的：

- `AgentState` 适合 graph 内部传递，不适合直接暴露给 CLI / API
- `/api/status` 和 `/api/reports` 主要依赖 `FactorPool` 摘要，不是真正的运行状态
- CLI 的 `status / report / approve` 也还没有稳定的数据面

这会导致一个后果：runtime 虽然开始收口，但产品层仍然没有可靠的“读模型”。

---

## 设计原则

1. `FactorPool` 继续负责知识平面，不承担控制平面职责
2. `state_store` 只保存运行态摘要、产物索引和审批记录
3. 第一版优先本地单机可用，不引入额外服务
4. orchestrator 只写 store，不让 CLI / API 直接理解 graph internals
5. schema 必须足够小，避免又造一个胖版 `AgentState`

---

## 方案选择

### 方案 A：继续直接读 LangGraph checkpoint

优点：
- 不需要新组件

问题：
- CLI / API 与 graph internals 强耦合
- 不适合报告列表、产物索引和审批审计
- 很难支撑后续 Dashboard

结论：
- 不采用

### 方案 B：文件型 JSON store

优点：
- 最简单，调试容易

问题：
- 查询能力差
- 并发和更新语义脆弱
- 很快会长出“手写数据库”

结论：
- 可作为兜底思路，但不是首选

### 方案 C：SQLite-backed minimal state store

优点：
- 本地单机足够稳
- 查询简单，适合列表型接口
- 不需要新服务
- 后续可以平滑抽象成 storage adapter

问题：
- 需要定义 schema 和迁移边界

结论：
- 第一版采用

---

## 第一版范围

### 保存对象

#### 1. `RunRecord`

- `run_id`
- `mode`
- `status`
- `current_round`
- `current_stage`
- `started_at`
- `finished_at`
- `last_error`

#### 2. `RunSnapshot`

- `run_id`
- `approved_notes_count`
- `backtest_reports_count`
- `verdicts_count`
- `awaiting_human_approval`
- `updated_at`

#### 3. `ArtifactRecord`

- `run_id`
- `kind`
- `ref_id`
- `path`
- `created_at`

第一版 `kind` 只支持：

- `backtest_report`
- `cio_report`

#### 4. `HumanDecisionRecord`

- `run_id`
- `action`
- `created_at`

---

## 第一版不做什么

- 事件溯源
- 多用户权限
- 复杂筛选与全文检索
- 分布式并发控制
- Dashboard 专用聚合接口
- 直接替代 `FactorPool`

---

## 模块边界

### 新模块

建议新增：

- `src/schemas/control_plane.py`
- `src/control_plane/state_store.py`

### 边界划分

- `src/core/orchestrator.py`
  - 在关键节点写 run/snapshot/artifact
- `src/api/server.py`
  - 优先从 `state_store` 读 `/api/status`、`/api/reports`
- `src/cli/main.py`
  - `status / report` 优先走 `state_store`
- `src/factor_pool/`
  - 不改为控制平面存储，只保留知识平面职责

---

## 最小接口

```python
create_run(mode: str) -> RunRecord
update_run(run_id: str, **fields) -> RunRecord
write_snapshot(snapshot: RunSnapshot) -> None
append_artifact(record: ArtifactRecord) -> None
append_human_decision(record: HumanDecisionRecord) -> None
get_latest_run() -> Optional[RunRecord]
get_snapshot(run_id: str) -> Optional[RunSnapshot]
list_artifacts(run_id: str, kind: Optional[str] = None) -> list[ArtifactRecord]
list_reports(limit: int = 20) -> list[ArtifactRecord]
```

---

## 数据流

### orchestrator 写路径

1. run 启动时创建 `RunRecord`
2. 每次阶段推进时更新 `current_stage`
3. Stage 4 / 5 结束后更新 snapshot 计数
4. 生成 `BacktestReport` / `CIOReport` 时写 `ArtifactRecord`
5. 进入 human gate 时写 `awaiting_human_approval = true`
6. 注入 approve / redirect / stop 时写 `HumanDecisionRecord`

### CLI / API 读路径

- `status`
  - `latest_run + snapshot`
- `report`
  - `latest_run` 的 `cio_report` artifact
- `/api/reports`
  - 报告 artifact 列表，而不是 `FactorPool` 摘要伪装

---

## 失败与降级策略

第一版允许两层降级：

1. `state_store` 不可用时，orchestrator 记录 warning，但主研究流程不直接崩
2. CLI / API 如果读不到 `state_store`，返回空状态或明确错误，不再偷偷回退成与运行态无关的伪数据

这一步很重要。控制平面失败不应该伪装成“系统正常运行”。

---

## 测试策略

第一版至少补三类测试：

1. `tests/test_state_store.py`
   - CRUD 与列表查询
2. `tests/test_api_state_store.py`
   - `/api/status`、`/api/reports` 优先读取 `state_store`
3. `tests/test_orchestrator_state_store.py`
   - 最小主链会写 run/snapshot/artifact

---

## Definition of Done

满足以下条件即算第一版完成：

1. 能创建和更新 `RunRecord`
2. orchestrator 能写 `RunSnapshot`
3. `CIOReport` 能被登记为 artifact
4. human decision 能留痕
5. CLI / API 的 `status / reports` 可以优先读 `state_store`
6. 有一组 local integration tests 锁住最小数据流

---

## 后续扩展

第一版完成后，再考虑：

- `BacktestReport` artifact refs 全量化
- run history 列表
- Dashboard 轮询接口
- storage adapter 抽象
- 与 LangGraph checkpoint 的恢复语义对齐
