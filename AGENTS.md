# AGENTS.md

Repository guidance for AI agents working in this project.

## Canonical Docs

Before making architectural decisions, read these in order:

1. `CLAUDE.md` — 项目定义、技术栈、AI Team 设计、Stage 2 四个活跃子空间 + regime 基础设施层
2. `docs/00_documentation-standard.md` — 文档级别与目录职责规范
3. `docs/README.md` — 文档体系入口
4. `docs/overview/03_architecture-overview.md` — 系统总览
5. `docs/overview/05_spec-execution-audit.md` — 设计与实现一致性审计
6. `docs/design/16_test-pipeline.md` — 测试分层规范

Do not treat `docs/archive/` as the source of truth for current implementation.

## Repo-local Codex Workflow

This repository also carries repo-local Codex workflow skills under `/.codex/skills/`.

When the task involves external system semantics, experiment-mainline validation, runtime concessions, or worker delegation quality, check `/.codex/README.md` first and use the relevant repo-local skill before proceeding.

## Project State

Pixiu v2 — LLM-native alpha research OS for A-shares.

- Schema 真相：`src/schemas/`
- 主编排：`src/core/orchestrator/`
- 控制平面：`src/control_plane/state_store.py`
- Stage 5 canonical runtime：`src/agents/judgment/`
- 设计与实现偏差以 `docs/overview/05_spec-execution-audit.md` 为准
- 当前架构重心：扩大 hypothesis space，不扩大 execution power

### 架构灵魂

- 上游极强探索（Stage 1-2），中游严格收缩（Stage 3），下游只输出可审计对象（Stage 4-5）
- Pixiu = alpha research infrastructure，不是投顾团队
- 因子是 research object / compressed hypothesis，不只是选股分数

## Environment

```bash
# 环境管理统一使用 uv（不使用 pip / conda / poetry）
uv sync --dev          # 同步全部依赖
uv run pytest ...      # 运行测试
uv add <pkg>           # 添加依赖
uv add --group dev <pkg>  # 添加开发依赖
```

关键文件：`pyproject.toml`、`uv.lock`、`.python-version`

## AI Team

详细 team 设计见 `CLAUDE.md` 的 "AI Team 设计" 章节。

### 角色速查

| 角色 | 身份 | 模型 | 适合任务 |
|------|------|------|----------|
| **Coordinator** | Claude 主对话 | Claude Opus | 架构决策、设计讨论、brainstorming、集成验证、schema 变更 |
| **codex** | Codex CLI worker | — | 单模块实现、重构、debug、测试编写 |
| **coworker** | Codex CLI reviewer | GPT-5.4 xhigh | 设计审阅、代码 review、spec 一致性审计、跨文件质量检查 |

### 派单规则

1. 每个 worker 任务必须明确：Task / Context / Constraints / Output / Done When
2. 写集不重叠时才可并行
3. 默认拓扑 `coordinator + 1-2 workers`，不搞大团队
4. 超时无产出 → coordinator 接管或拆小

### 不可外包给 worker 的事

- 架构决策和跨模块判断
- Schema / contract 设计变更
- Stage 间接口定义
- spec-execution-audit 更新
- 与用户的设计讨论和 brainstorming

## Working Rules

- When specs and code disagree, first determine whether the code is ahead, behind, or drifting from spec. Record the answer in the relevant spec before large implementation changes.
- Prefer `docs/overview/` + `docs/design/` over legacy design notes.
- Treat `docs/research/` as context and historical discussion, not as implementation truth.
- Treat `docs/reference/` as supporting material only.
- Schema changes must update `src/schemas/` first, then runtime.
- New modules must have corresponding smoke/unit tests.
- Do not bypass the Stage 3 prefilter hard gate.
- Do not add "smart" logic to the execution layer — intelligence belongs in Stage 2.
- Environment: use `uv` exclusively. Never use `pip install` or `conda`.

## Useful Commands

```bash
# sync environment
uv sync --dev

# default test entry
uv run pytest -q tests -m "smoke or unit"

# local integration tests
uv run pytest -q tests -m integration

# baseline
uv run python -m src.core.run_baseline

# single-island debug run
uv run pixiu run --mode single --island momentum

# evolve loop
MAX_ROUNDS=20 uv run pixiu run --mode evolve --rounds 20

# CLI
uv run pixiu --help

# API
uv run uvicorn src.api.server:app --reload
```

## Current Design Focus

Recommended execution order:

1. Reset truth anchors first: keep `docs/overview/05_spec-execution-audit.md`, `docs/overview/06_runtime-concessions.md`, and `docs/plans/current_implementation_plan.md` aligned to current runtime evidence
2. Close `Stage 1 live` under `default/controlled`: env truth, blocking tool discovery, and current Tushare-based live tests
3. Close controlled-run `Stage 2`: novelty waste, JSON/output robustness, and `approved -> low_sharpe` value density
4. Close validation runtime: make `candidate -> promote` real with OOS / PIT / A-share execution boundaries
5. Only then optimize throughput/cost or expand Stage 2 data-source surface, MiroFish, Dashboard, and broader product layers

## Worker Output Requirements

Every worker must return:

1. **What changed** — file list + change summary
2. **Why** — decision rationale
3. **Verification** — commands run + results
4. **Open items** — anything unfinished, explicitly listed

No verification result = task not complete.
