# Docs Guide

这份目录是 Pixiu 文档系统的唯一入口。

如果你不知道该先读什么，就从这里开始，不要直接在 `docs/` 里扫文件名。

## Truth Hierarchy

- `L1`: `docs/overview/`（项目真相与默认阅读入口）
- `L2`: `docs/design/`（当前有效设计）
- `L3`: `docs/plans/`（当前执行计划与工程债，不承载长期产品真相）
- `L4`: `docs/futures/` `docs/reference/` `docs/research/`（前瞻与支持材料）
- `L5`: `docs/archive/`（历史归档）

## Numbering Rule

- 编号只在**同一目录内**表示阅读顺序。
- 不存在跨目录的全局编号阅读链。

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

## After the Main Path

- `docs/design/`
  - 当前有效设计，只有在你已经读完 `overview` 后再进入
- `docs/plans/`
  - 当前执行计划和工程债（会变化，不作为长期真相）
- `docs/futures/`
  - 前瞻但非当前运行时的设计

其余目录如 `reference / research / archive / specs` 默认都不在第一阅读路径里。

如果你已经读完 `overview` 主路径，但还需要理解：

- 哪些行为是当前主线故意接受的降级
- 哪些实验特判只服务于 fast feedback / harness
- 哪些能力已经达成共识、但明确延期实现

继续读：

1. `docs/overview/06_runtime-concessions.md`

## Ground Rules

- 需要理解项目时，先走 `overview` 五篇主路径。
- 需要改实现时，再进入 `design/` 或 `plans/`。
- 需要区分“设计漂移”和“故意让步”时，再看 `docs/overview/06_runtime-concessions.md`。
- 当设计与代码不一致时，以 `docs/overview/05_spec-execution-audit.md` 为准。
- 文档系统本身的规范见 `docs/00_documentation-standard.md`。
