# Overview Guide

`docs/overview/` 是 Pixiu 给人类读者准备的主阅读路径。

它只回答四件事：

- 项目是什么
- 代码入口在哪
- 现在做到哪了
- 下一篇该读什么

## Reading Order

1. `01_project-snapshot.md`
   - 用一个文件快速理解 Pixiu 是什么、不是什么。
2. `02_codebase-map.md`
   - 找到代码入口和目录职责。
3. `03_architecture-overview.md`
   - 理解系统结构和 Stage 关系。
4. `04_current-state.md`
   - 用人类可读方式看清当前进度。
5. `05_spec-execution-audit.md`
   - 用审计视角核实哪些设计已经落地、哪些仍在漂移。

读完这五篇后，如果你还需要区分“当前主线故意接受的让步”和“设计实现漂移”，再继续看：

6. `06_runtime-concessions.md`
   - 查看当前仍生效的运行时让步、实验特判、MVP 简化和延期实现。

## Rules

- 编号只在 `overview/` 目录内表达阅读顺序，不承诺跨目录顺序。
- `overview` 只保留高层真相和阅读顺序。
- 大段实现细节应进入 `docs/design/`。
- 当前执行计划应进入 `docs/plans/`。
- 设计与代码不一致时，先更新 `05_spec-execution-audit.md`。
