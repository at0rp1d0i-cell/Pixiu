# Pixiu v2 Agent 团队说明
Purpose: Define the agent role boundaries and collaboration topology inside Pixiu.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.0
> 创建：2026-03-09
> 前置依赖：`.../overview/03_architecture-overview.md`、`11_interface-contracts.md`
> 状态：**Active**

---

## 1. 目标

本文件描述 Pixiu v2 中各类 Agent 的职责边界、模型类型和相互关系。

它回答的问题是：

- 系统里有哪些 Agent
- 每个 Agent 负责什么，不负责什么
- 哪些是确定性组件，哪些是 LLM 驱动组件
- 反思与 Skills 在 Agent 体系中处于什么位置

---

## 2. Agent 团队清单

| Agent | 阶段 | 模型 | 类型 |
|---|---|---|---|
| MarketAnalyst | Stage 1 | deepseek-chat | LLM |
| LiteratureMiner | Stage 1 | deepseek-chat | LLM + RAG |
| AlphaResearcher | Stage 2 | deepseek-chat | LLM |
| SynthesisAgent | Stage 2 | deepseek-chat | LLM |
| Validator | Stage 3 | 规则引擎 | 确定性 |
| NoveltyFilter | Stage 3 | 向量相似度 | 确定性 |
| AlignmentChecker | Stage 3 | 小模型（快速） | LLM |
| ExplorationAgent | Stage 4 | deepseek-chat / GLM-5 | LLM + 代码执行 |
| Coder | Stage 4 | 无 LLM 主体 | 确定性模板执行 |
| Critic | Stage 5 | 规则引擎 | 确定性 |
| RiskAuditor | Stage 5 | 规则 + 简单统计 | 确定性 MVP |
| PortfolioManager | Stage 5 | 无 LLM 主体 | 确定性 equal-weight MVP |
| ReportWriter | Stage 5 | 模板渲染 | 模板化 MVP |
| ReflectionAgent | 跨轮异步 | deepseek-reasoner | LLM（推理优先） |

总计：14 个 Agent / 组件。

---

## 3. 团队分组

### Stage 1: 宽扫描组

- `MarketAnalyst`
  - 负责：宏观、北向、主题、市场制度的摘要
  - 不负责：提出最终因子公式
- `LiteratureMiner`
  - 负责：从 FactorPool / 历史研究中提炼相关经验
  - 不负责：运行回测

### Stage 2: 假设生成组

- `AlphaResearcher`
  - 负责：提出结构化 `FactorResearchNote`
  - 不负责：直接执行 Qlib 回测
- `SynthesisAgent`
  - 负责：寻找跨 Island 的关联与可合并思路
  - 当前状态：已进入主链路，但能力仍偏弱

### Stage 3: 前置过滤组

- `Validator`
  - 负责：Qlib 语法与 A 股硬约束检查
- `NoveltyFilter`
  - 负责：与 FactorPool 的重复度控制
- `AlignmentChecker`
  - 负责：经济直觉与公式方向的语义一致性

### Stage 4: 执行组

- `ExplorationAgent`
  - 负责：按需做 EDA / 探索性分析
  - 不负责：最终回测定稿
- `Coder`
  - 负责：确定性回测执行与结构化输出
  - 不负责：任何研究推理

### Stage 5: 判断与综合组

- `Critic`
  - 负责：阈值判定与失败归因
- `RiskAuditor`
  - 负责：最小风险审计与相似性风险
- `PortfolioManager`
  - 负责：本轮通过因子的确定性组合配置
- `ReportWriter`
  - 负责：生成模板化 `CIOReport` 并触发人机交互

### 跨轮学习组

- `ReflectionAgent`
  - 不在五阶段主漏斗内
  - 负责：将过程知识整理为反思与 Skill 提案

---

## 4. 设计原则

### 4.1 不是所有名字里带 Agent 的东西都应该是 LLM

Pixiu 的关键设计点之一，就是允许“研究推理组件”和“确定性执行组件”并存。

因此：

- `Coder` 不应该退化回通用代码助手
- `Validator` / `NoveltyFilter` 不应该被随意替换成 LLM
- `Critic` 当前应保持 deterministic judgment，不要重新漂回 LLM 归因器

### 4.2 文档驱动通信

Agent 之间只通过结构化文档通信，不直接共享隐式内部状态。

主要文档类型：

- `MarketContextMemo`
- `FactorResearchNote`
- `ExplorationResult`
- `BacktestReport`
- `CriticVerdict`
- `RiskAuditReport`
- `PortfolioAllocation`
- `CIOReport`

详情见 `11_interface-contracts.md`。

### 4.3 反思与 Skills 不是主漏斗步骤

反思、元反思和永久 Skills 体系属于跨轮学习层，不应挤进单轮五阶段漏斗中，否则会让主循环职责混乱。

---

## 5. Skills 与 Agent 的关系

当前 Skills 主要服务于 Researcher 类 Agent：

- `constraints/a_share_constraints.md`
- `constraints/qlib_formula_syntax.md`
- `researcher/alpha_generation.md`
- `researcher/island_evolution.md`
- `researcher/feedback_interpretation.md`

设计目标：

- 把稳定规则沉淀为 Skills
- 把实验性策略留在反思系统中
- 只有经过验证的规则才升级为长期注入的知识

---

实现边界与当前漂移点，请查看 `../overview/05_spec-execution-audit.md`。本文件只负责定义团队角色和职责边界。
