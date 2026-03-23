# Pixiu Codex Workflow

这份入口只服务仓库内的 Codex 开发流程。

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
