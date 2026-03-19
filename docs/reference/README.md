# Reference Guide

`docs/reference/` 存放相对稳定、会被长期复用的外部知识和实践材料。

这些文档不是当前系统设计真相，但它们适合在设计和实现时反复查阅。

## 适合放在这里的内容

- 外部开源项目、论文和工具索引
- 数据管线最佳实践
- 市场或基础设施背景资料
- 不直接依赖当前版本实现、但长期有参考价值的总结

## 当前内容

- `agent_research_os_sota.md`
  - 面向 Pixiu 的 agent runtime、memory、MCP、skills 与经济学式研究流程前沿参考
- `llm_quant_projects_and_papers.md`
  - LLM 量化研究相关的项目、论文和数据源索引
- `a_share_quant_frameworks.md`
  - A 股开源量化基础设施背景调研
- `data-download-guide.md`
  - Pixiu 本地数据下载、转换、增量更新和验证的执行指南
- `qlib_data_pipeline_best_practices.md`
  - Qlib 日线数据管线的关键约束与清洗实践

## 不适合放在这里的内容

- 当前系统模块设计
- 当前执行计划
- 历史阶段报告
- 还在不断变化的讨论稿

这些内容应分别进入 `docs/design/`、`docs/plans/` 或 `docs/research/`。
