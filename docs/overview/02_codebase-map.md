# Codebase Map

Purpose: Provide a human-readable map from Pixiu concepts to the actual code directories and entrypoints.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

## 1. Repo at a Glance

如果你刚进入仓库，先记住这几个目录：

- `src/schemas/`
  - 所有核心对象与 schema 真相
- `src/core/orchestrator/`
  - 主编排图与 Stage 节点
- `src/agents/`
  - Stage 1/2/3 和 Stage 5 判断层的 agent 实现
- `src/execution/`
  - Stage 4 的确定性执行与回测隔离
- `src/factor_pool/`
  - 因子沉淀、约束写回与调度相关能力
- `src/control_plane/`
  - 运行状态、审批和 artifact 追踪
- `src/scheduling/`
  - Stage 2 子空间调度
- `src/cli/`, `src/api/`
  - CLI/API 入口
- `tests/`
  - smoke/unit/integration 测试

## 2. Stage-by-stage Runtime Path

### Stage 1: Market Context

- 入口节点：`src/core/orchestrator/nodes/stage1.py`
- 主要 agent：`src/agents/market_analyst.py`
- 产物：`MarketContextMemo`

### Stage 2: Hypothesis Expansion

- 入口节点：`src/core/orchestrator/nodes/stage2.py`
- 主要 agent：`src/agents/researcher.py`
- 相关调度：`src/scheduling/subspace_scheduler.py`
- 相关 schema：`src/schemas/research_note.py`, `src/schemas/hypothesis.py`

### Stage 3: Prefilter

- 入口节点：`src/core/orchestrator/nodes/stage3.py`
- 主要实现：`src/agents/prefilter.py`
- canonical 校验链：`Validator.validate()` → `src/formula/semantic.py`
- 遗留参考：`src/agents/validator.py`（非 canonical runtime）

### Stage 4: Execution

- 入口节点：`src/core/orchestrator/nodes/stage4.py`
- 核心执行：`src/execution/coder.py`
- 隔离执行：`src/execution/docker_runner.py`
- 模板：`src/execution/templates/qlib_backtest.py.tpl`

### Stage 5: Judgment

- 入口节点：`src/core/orchestrator/nodes/stage5.py`
- 判断层包：`src/agents/judgment/`
- 关键模块：
  - `critic.py`
  - `risk_auditor.py`
  - `portfolio_manager.py`
  - `report_writer.py`
  - `constraint_extractor.py`

## 3. Orchestration and Control Plane

如果你想理解“系统是怎么跑起来的”，先看：

- `src/core/orchestrator/graph.py`
  - LangGraph 主图与路由
- `src/core/orchestrator/_entrypoints.py`
  - 运行入口包装
- `src/core/orchestrator/_context.py`
  - 图上下文和共享依赖
- `src/core/orchestrator/nodes/control.py`
  - 循环控制、审批与运行控制相关节点
- `src/control_plane/state_store.py`
  - 最小状态与 artifact 持久化

## 4. Knowledge and State

如果你关心“系统把什么沉淀下来”，重点看：

- `src/factor_pool/pool.py`
  - 因子注册、通过因子读取、失败约束写回
- `src/factor_pool/scheduler.py`
  - 因子池侧调度逻辑
- `src/schemas/factor_pool.py`
  - `FactorPoolRecord`
- `src/schemas/failure_constraint.py`
  - 失败经验对象

## 5. Schemas First

Pixiu 的很多实现判断要先看 schema，再看 runtime。

最常用的 schema 文件：

- `src/schemas/stage_io.py`
  - 12 个节点的输入输出 TypedDict
- `src/schemas/judgment.py`
  - `CriticVerdict` 等 Stage 5 合约
- `src/schemas/backtest.py`
  - `BacktestReport`
- `src/schemas/research_note.py`
  - `FactorResearchNote`
- `src/schemas/market_context.py`
  - `MarketContextMemo`
- `src/schemas/thresholds.py`
  - 统一阈值

## 6. Product Entry Points

### CLI

- `src/cli/main.py`
- 常用命令：
  - `uv run pixiu --help`
  - `uv run pixiu run --mode single --island momentum`
  - `MAX_ROUNDS=20 uv run pixiu run --mode evolve --rounds 20`

### API

- `src/api/server.py`
- 本地启动：
  - `uv run uvicorn src.api.server:app --reload`

## 7. Where to Start for Common Tasks

- 想理解项目全貌：
  - 先看 `docs/overview/03_architecture-overview.md`
- 想核实设计和实现是否一致：
  - 先看 `docs/overview/05_spec-execution-audit.md`
- 想改 Stage 2：
  - 先看 `src/agents/researcher.py`、`src/scheduling/subspace_scheduler.py`、`src/schemas/research_note.py`
- 想改 Stage 4→5 收口：
  - 先看 `src/core/orchestrator/nodes/stage4.py`、`src/core/orchestrator/nodes/stage5.py`、`src/agents/judgment/`
- 想改 CLI/API：
  - 先看 `src/cli/main.py`、`src/api/server.py`
- 想改文档：
  - 先看 `docs/00_documentation-standard.md`

## 8. Recommended Next Reads

1. `03_architecture-overview.md`
2. `04_current-state.md`
3. `05_spec-execution-audit.md`
