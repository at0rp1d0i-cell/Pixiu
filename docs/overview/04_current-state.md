# Current State

Purpose: Give a short human-readable summary of what is stable, partial, and future work in the current Pixiu codebase.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

## 1. Stable Enough to Rely On

- `src/core/orchestrator/` 已完成包级拆分，12 节点主图可运行
- Stage 4→5 的最小 deterministic 闭环已经存在
- `src/schemas/stage_io.py` 已把 Stage I/O TypedDict 收紧到主干
- `src/control_plane/state_store.py` 已提供最小控制平面存储
- `src/agents/judgment/` 已取代旧单文件 Stage 5 实现
- 默认测试入口 `uv run pytest -q tests -m "smoke or unit"` 可用

## 2. Partial but Important

- Stage 2 的四个活跃子空间和 regime 基础设施层已经进入主干
- `AlphaResearcher` 仍是纯 LLM 调用，尚未具备主动 MCP/tool access
- `FactorPoolRecord.subspace_origin` 的 schema 和存储位点已存在，但 Stage 5 写回链还没完全接通
- 控制平面仍是 MVP，不是完整读模型和审计面
- CLI/API 是当前产品入口，但 Dashboard 仍未进入实现阶段

## 3. What Changed Recently

Phase 3 的主线不是简单加功能，而是大规模收口与模块化：

- judgment 与 orchestrator 从单文件拆成包
- v1→v2 schema 和 compat 层进一步清理
- Stage I/O 类型收紧进入主链
- 测试文件与命令重新收敛

这也是本轮要做文档整编的直接原因：代码边界已经变了，文档系统必须跟着变。

## 4. Current Engineering Priorities

1. Stage 2 工具化与数据源扩展
2. richer contracts 的端到端收口
3. 控制平面的稳定化
4. Phase 4B 实验与 MiroFish Go/No-Go 决策
5. 之后再扩展 Dashboard 与更多产品表层

## 5. How to Read This State Correctly

- 想快速理解项目：看 `01_project-snapshot.md`
- 想找代码入口：看 `02_codebase-map.md`
- 想理解系统结构：看 `03_architecture-overview.md`
- 想核对真实漂移：看 `05_spec-execution-audit.md`

`Current State` 是人类摘要，不替代审计文档。
