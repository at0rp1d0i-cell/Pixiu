Status: active
Owner: coordinator
Last Reviewed: 2026-03-23

Purpose: Define a repository-scoped Codex workflow layer for Pixiu so development defaults to source-backed, harness-first, concession-aware execution instead of free-form agent behavior.

---

## Why Now

Pixiu 目前的主问题已经不只是代码复杂度，而是开发流程本身仍然过于探索型。

典型症状已经出现：

- 外部系统语义没有先查官方资料就直接写实现
- 主链改动没有先绑定 harness/profile/artifact 验证路径
- 临时降级和实验特判容易散落在对话里，不进入长期真相
- worker 派单质量依赖主线程临场发挥，缺少稳定模板

这些问题继续存在，会直接污染后续的 Stage 2 收敛、实验有效性和文档可信度。

因此这一轮先不继续扩 runtime 能力，而是先为 Codex 建一层项目级 workflow 约束。

---

## Goals

这轮必须达成：

1. Pixiu 仓库拥有自己的 Codex workflow 层，而不是完全依赖全局默认行为
2. 涉及 `Qlib / Tushare / OpenAI / Chroma / MCP` 的改动，默认先查官方资料或本地 runtime 真相
3. 任何主链改动都默认走 harness-first 思路，而不是“先写完再补验证”
4. 引入降级、fallback、延期实现时，默认同步检查 runtime concessions ledger
5. worker 派单格式收口，减少无依据脑补和低质量任务描述

---

## Non-Goals

这轮不做：

- 不调整全局 `~/.codex/config.toml`
- 不新增项目级 `.codex/agents/`
- 不改 Pixiu runtime 逻辑
- 不一次性把所有开发流程都 skill 化
- 不替代现有 `AGENTS.md` 和文档体系

---

## Chosen Shape

采用“仓库级 skills + 极短入口文档 + 最小 AGENTS 接入”的方案。

具体包括：

- `/.codex/README.md`
  - 仓库级 Codex workflow 入口
- `/.codex/skills/...`
  - 少量高杠杆项目技能
- `AGENTS.md`
  - 只加一小段入口说明，把项目级 skills 接入仓库工作流

不在这一轮引入项目级 agent files。

原因：

- skills 更适合表达稳定流程约束
- 当前最缺的是“默认不允许无依据开工”，不是更多角色
- 仓库级 skills 能直接跟项目一起版本化

---

## First Skill Set

第一批只落四个 skills：

### 1. `pixiu-official-source-gate`

用途：

- 涉及外部系统语义时，必须先查官方资料或本地 runtime 真相

首批强制对象：

- `Qlib`
- `Tushare`
- `OpenAI`
- `Chroma`
- `MCP`

目标：

- 默认阻止“没查文档就乱写”

### 2. `pixiu-harness-first`

用途：

- 所有主链改动在开工前明确：
  - 这是 `fast feedback` 还是 `controlled run`
  - 用哪个 profile
  - 哪个 artifact 用于证明改动有效

目标：

- 把开发流程从“实现优先”改成“验证入口优先”

### 3. `pixiu-runtime-concession-check`

用途：

- 引入 fallback、特判、降级、延期实现时
- 默认同步检查 [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)

目标：

- 不让临时让步继续散落在聊天和脑中

### 4. `pixiu-worker-brief`

用途：

- 统一 worker 派单模板：
  - `Task`
  - `Context`
  - `Constraints`
  - `Output`
  - `Done When`

目标：

- 减少 worker 脑补和低质量任务描述

---

## Entry Strategy

项目级 workflow 入口分三层：

1. `AGENTS.md`
   - 告诉后续 Codex：该仓库有项目级 workflow skills
2. `/.codex/README.md`
   - 用极短方式解释什么时候该看哪些 skills
3. `/.codex/skills/*`
   - 承载实际流程约束

约束：

- `AGENTS.md` 只加最小入口，不再写胖
- `/.codex/README.md` 只做导航，不复制 skill 正文

---

## Interaction With Existing Truth Anchors

这层 workflow 不是新的真相层，而是现有真相层的执行入口。

它依赖并尊重以下锚点：

- `AGENTS.md`
- `docs/overview/05_spec-execution-audit.md`
- `docs/overview/06_runtime-concessions.md`
- `src/schemas/`
- `src/schemas/stage_io.py`
- experiment harness / resolved profile

skill 只负责把这些锚点变成默认工作流，不重新定义它们。

---

## Acceptance

完成标准：

1. 仓库内存在可版本化的 `.codex/` workflow 层
2. 新 skill 不与现有 truth hierarchy 冲突
3. `AGENTS.md` 能最小引导 Codex 进入项目级 workflow
4. 第一批四个 skills 都能服务 Pixiu 当前最痛的流程问题
5. 实现不碰 Pixiu runtime 代码
