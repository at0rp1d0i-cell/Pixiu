# Pixiu Codex Workflow

这份入口只服务仓库内的 Codex 开发流程。

目录职责保持分离：

- `/.agents/skills/`：Codex 会自动发现的 repo-local skills，包含安装进来的 team runtime skills，以及仓库内的 `pixiu-*` workflow skills
- `/.codex/`：项目级配置、角色绑定、bridge 元数据，以及这份 workflow 说明

不要把 skills 放到 `/.codex/` 里当作 canonical root，否则新的 Codex 会话不会把它们当作 repo-local skills 自动发现

默认规则很简单：

- 先找真相锚点，再改代码
- 先绑定验证入口，再实现
- 引入让步时，必须记账
- 派 worker 时，brief 必须收口

## When To Use Which Skill

- `pixiu-official-source-gate`
  - 涉及 `Qlib / Tushare / OpenAI / Chroma / MCP` 语义时先用
- `pixiu-harness-first`
  - 改主链、改 stage 行为、改实验入口时先用
- `pixiu-runtime-concession-check`
  - 引入 fallback、降级、特判、延期实现时先用
- `pixiu-worker-brief`
  - 任何 worker 派单前先用

## Scope

这层 workflow 是仓库级约束，不替代：

- [AGENTS.md](/home/torpedo/Workspace/ML/Pixiu/AGENTS.md)
- [05_spec-execution-audit.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/05_spec-execution-audit.md)
- [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)

它的作用只是把这些锚点变成默认工作流，而不是继续靠临场发挥。
