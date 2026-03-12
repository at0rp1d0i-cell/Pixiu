# Overview Guide

`docs/overview/` 只回答三类问题：

- 这个项目是什么
- 现在做到了哪里
- 应该先读哪些设计文档

它不是实现细节堆放区，也不是历史讨论区。

## Reading Order

1. `project-snapshot.md`
   - 用一个文件快速理解项目、当前进度和目标用户。
2. `architecture-overview.md`
   - 系统级总览；每个一级模块都必须映射到 `docs/design/` 中的展开设计。
3. `spec-execution-audit.md`
   - 当前哪些设计已经落地、哪些仍在漂移、哪些只是前瞻。

## Rules

- `overview` 中出现的一级模块，必须能在 `docs/design/` 中找到对应设计文档。
- `overview` 只保留系统边界、主张、当前状态和阅读顺序，不承载大段实现细节。
- 当 `overview` 和实现不一致时，先更新 `spec-execution-audit.md`，再决定是否改设计或改代码。
