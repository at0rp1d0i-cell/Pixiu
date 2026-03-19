# Reference Guide

`docs/reference/` 存放相对稳定、会被长期复用的外部知识和实践材料。

这些文档不是当前系统设计真相，但它们适合在设计和实现时反复查阅。

## 适合放在这里的内容

- 外部开源项目、论文和工具索引
- 数据管线最佳实践
- 市场或基础设施背景资料
- 不直接依赖当前版本实现、但长期有参考价值的总结

## 当前内容

### 主参考

- `agent_research_os_sota.md`
  - Pixiu 下一阶段 agent runtime、retrieval、memory、MCP 与 skills 采用建议的主参考
- `data-download-guide.md`
  - 当前本地数据下载、转换、增量更新和验证的执行指南
- `tushare-dataset-matrix.md`
  - Tushare 官方数据面与 Pixiu 接入优先级矩阵

### 辅助背景

- `llm_quant_projects_and_papers.md`
  - 更宽口径的项目与论文索引；当需要 Pixiu 采用建议时，优先回到 `agent_research_os_sota.md`
- `a_share_quant_frameworks.md`
  - A 股开源量化基础设施背景调研；更适合作为生态扫盲资料，而不是当前选型真相

### 已归档的旧 memo

- `docs/archive/reference/qlib_data_pipeline_best_practices.md`
  - 早期 Qlib 数据管线备忘，已被 `data-download-guide.md` 吸收

## 不适合放在这里的内容

- 当前系统模块设计
- 当前执行计划
- 历史阶段报告
- 还在不断变化的讨论稿

这些内容应分别进入 `docs/design/`、`docs/plans/` 或 `docs/research/`。
