# Orchestrator Boundary Refactor Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-19

Purpose: Clarify the orchestrator package boundary by separating config, runtime state, graph construction, and control-plane helpers.

---

## Problem

[src/core/orchestrator/__init__.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/__init__.py) 当前同时充当：

- 配置常量容器
- 模块级运行时状态持有者
- scheduler / factor pool / state store gateway
- snapshot / report persistence helper
- node re-export layer
- graph entrypoint layer

这会造成：

- CLI / API / tests 都耦合到 package root
- monkeypatch seam 和真实 runtime seam 混在一起
- 单个 stage 的语义分散在 node wrapper、package root、entrypoint 三处

---

## Goal

把 orchestrator 包收口成更清晰的边界：

- config
- runtime context
- graph factory
- control-plane bridge
- node wrappers

---

## Recommended Design

### 1. 拆出 runtime config

新增：

- `src/core/orchestrator/config.py`

负责：

- `MAX_ROUNDS`
- `ACTIVE_ISLANDS`
- `REPORT_EVERY_N_ROUNDS`
- `MAX_CONCURRENT_BACKTESTS`
- `REPORTS_DIR`

### 2. 拆出 runtime context

新增：

- `src/core/orchestrator/runtime.py`

负责：

- `_scheduler`
- `_current_run_id`
- `_graph`
- accessor / reset helpers

### 3. 拆出 control-plane bridge

新增：

- `src/core/orchestrator/control_plane.py`

负责：

- run record
- snapshot persistence
- CIO report persistence

### 4. 保留 package root 仅做稳定 re-export

`__init__.py` 应只做：

- 常用 public symbol re-export
- 向后兼容入口

而不是继续承载真实逻辑。

### 5. 更明确地定义 node wrapper 角色

`nodes/` 只保留：

- graph-friendly node signature
- stage runtime object construction
- stage I/O adaptation

不要在 wrapper 里继续堆持久化和全局运行时管理。

---

## Migration Strategy

### Phase 1

- 先抽 `config.py`
- 再抽 `runtime.py`

### Phase 2

- 抽 `control_plane.py`
- 让 CLI / API / tests 改为依赖新边界

### Phase 3

- 收缩 `__init__.py`
- 更新 monkeypatch 路径和测试 seam

---

## Non-Goals

- 不改 Stage 1-5 的业务语义
- 不改 LangGraph 主路由结构
- 不在这一期里重做 CLI/API 产品接口

---

## Exit Criteria

- package root 不再兼任多角色
- CLI / API / tests 对 orchestrator internals 的依赖更显式
- runtime config、run context、control-plane helper 各有单独归属
- graph/node 逻辑更容易做局部测试
