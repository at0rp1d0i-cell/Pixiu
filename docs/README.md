# Docs Guide

这份目录是 Pixiu 文档系统的唯一入口。

如果你不知道该先读什么，就从这里开始，不要直接在 `docs/` 里扫文件名。

## Default Reading Path

### 15 分钟理解项目

1. `docs/overview/01_project-snapshot.md`
2. `docs/overview/02_codebase-map.md`
3. `docs/overview/03_architecture-overview.md`
4. `docs/overview/04_current-state.md`
5. `docs/overview/05_spec-execution-audit.md`

### 要深入当前设计

1. `docs/design/README.md`
2. 当前相关模块的 design 文档

### 要看当前执行工作

1. `docs/plans/current_implementation_plan.md`
2. `docs/plans/README.md`

### 要准备本地数据或恢复下载

1. `docs/reference/data-download-guide.md`

### 要看未来路线

1. `docs/futures/README.md`

## Two-layer Model

Pixiu 的文档系统采用双层结构：

- 上层：人类优先
  - `docs/README.md`
  - `docs/overview/`
- 下层：实现与维护
  - `docs/design/`
  - `docs/plans/`
  - `docs/futures/`
  - `docs/reference/`
  - `docs/research/`
  - `docs/archive/`

## After the Main Path

- `docs/design/`
  - 当前有效设计，只有在你已经读完 `overview` 后再进入
- `docs/plans/`
  - 当前执行计划和工程债
- `docs/futures/`
  - 前瞻但非当前运行时的设计

其余目录如 `reference / research / archive / specs` 默认都不在第一阅读路径里。

## Ground Rules

- 需要理解项目时，先走 `overview` 五篇主路径。
- 需要改实现时，再进入 `design/` 或 `plans/`。
- 当设计与代码不一致时，以 `docs/overview/05_spec-execution-audit.md` 为准。
- 文档系统本身的规范见 `docs/00_documentation-standard.md`。
