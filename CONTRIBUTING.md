# Contributing

Purpose: Define the current maintainer workflow for Pixiu's internal development collaboration.
Status: active
Audience: both
Canonical: yes
Owner: maintainers
Last Reviewed: 2026-03-22

## Scope

这不是公开社区贡献指南。

当前默认协作对象只有：

- maintainer 本人
- 当前协作开发者

仓库未来可能继续公开、部分公开或转向闭源，但当前流程优先服务内部高带宽协作，而不是陌生外部贡献者。

## First Principles

Pixiu 的系统本体是 `alpha research OS`，不是投顾终端。

开发时优先守住这几条：

- 不扩大 `execution power`，扩大 `hypothesis space`
- 不绕过 Stage 3 hard gate
- intelligence 放在 Stage 1-2，execution 保持 deterministic
- 因子是 `research object / compressed hypothesis`，不是简单选股分数

## Read Order

在做架构判断、跨模块修改或文档更新前，先读：

1. `CLAUDE.md`
2. `docs/00_documentation-standard.md`
3. `docs/README.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/05_spec-execution-audit.md`
6. `docs/design/16_test-pipeline.md`

如果文档与代码冲突，默认信任顺序遵循 `docs/00_documentation-standard.md`。

## Collaboration Mode

当前推荐协作模式：

- 主线程负责架构判断、产品边界、任务拆分、集成裁决
- worker 负责单模块实现、bounded debug、单组测试或只读审计
- 写集不重叠时才允许并行
- 没有明确 `Task / Context / Constraints / Output / Done When` 的任务，不派 worker

不要把以下内容外包给 worker：

- 架构决策和跨模块判断
- schema / contract 设计变更
- Stage 间接口定义
- spec-execution-audit 更新
- 与用户的产品/设计讨论

## Before You Edit

开始动手前先回答：

- 这是代码 ahead、spec behind，还是两者 drift？
- 当前真相在哪个文件？
- 这次改动是否触及 `src/schemas/`？
- 是否需要先更新 spec 或 plan？

如果会新增模块：

- 必须同时补对应 smoke/unit tests

## Runtime Guardrails

以下属于硬边界：

- 不绕过 `src/agents/prefilter.py`
- 不把“聪明逻辑”塞进 `src/execution/`
- schema 变更先改 `src/schemas/`，再改 runtime
- `uv` 是唯一环境管理工具，不用 `pip` / `conda` / `poetry`

## Experiment Workflow

实验不是“先跑再解释”。

开始实验前至少明确：

- 目标问题
- 控制变量
- reset 范围
- 观测面
- stop 条件

当前默认 reset 边界：

- 可清：
  - `data/control_plane_state.db`
  - `data/experiment_runs/`
  - `data/artifacts/`
- 默认不清：
  - `data/factor_pool_db/`

原因：少数幸存因子可能仍有研究价值，不应与失败实验运行痕迹一起抹掉。

## Issue / PR Discipline

内部协作也走结构化入口：

- 架构调整：用 `Architecture Change` issue
- bounded runtime 修复：用 `Runtime Fix` issue
- 受控实验：用 `Experiment Run` issue

PR 必须写清楚：

- 架构影响
- truth / drift 关系
- 文档是否同步
- 验证命令与结果
- 风险
- 是否需要 reset 实验状态

## Commit Discipline

推荐使用仓库根目录的 `.gitmessage` 模板。

提交信息格式：

`type(scope): subject`

常见类型：

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`

如果本次改动由 AI 实际参与完成，可以在 commit message 末尾追加：

`Co-authored-by: OpenAI Codex <noreply@openai.com>`

不要机械同时带多个 co-author。谁真实参与，带谁。

## Verification Standard

没有验证结果，任务不算完成。

最少要回报：

1. What changed
2. Why
3. Verification
4. Open items

默认验证入口：

```bash
uv run pytest -q tests -m "smoke or unit"
```

需要时再追加：

```bash
uv run pytest -q tests -m integration
uv run pixiu run --mode single --island momentum
uv run pixiu --help
```

## Repository Visibility

当前模板和流程按内部协作编写，不代表仓库最终会维持完全开源。

如果后续决定：

- 继续全公开
- 变为部分公开
- 转为闭源产品仓库

应在那一轮单独重写本文件和 `.github/` 模板，而不是在当前版本提前写成泛化社区文档。

