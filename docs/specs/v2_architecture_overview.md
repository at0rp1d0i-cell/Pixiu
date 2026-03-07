# EvoQuant v2 系统架构总览

> 版本：2.0
> 创建：2026-03-07
> 状态：待 Gemini 执行
> 执行优先级：**P0 — 所有其他 Spec 的前置依赖，必须先读此文档**

---

## 1. 设计哲学：LLM 原生 vs 模仿人类

### v1 的问题

EvoQuant v1 是线性管线（Researcher → Validator → Coder → Critic），本质上在用 AI 模仿人类研究员的工作方式。这导致：

- 瓶颈在错误的地方：AI 生成假设的速度远超 Qlib 回测速度，但没有利用这一点
- Coder 层依赖 Claude Code（不开源、接口脆弱、字符串解析结果）
- 没有前置过滤：劣质假设直接进回测，浪费算力
- 单一 Researcher：没有利用 LLM 的并行能力
- 无宏观上下文注入：每次研究从零开始，不读市场信号

### v2 的核心原则

**LLM 的真正优势**：
- 阅读速度：数百份报告/轮，近乎免费
- 并行假设生成：N 个 Researcher 并行，成本线性扩展
- 跨域知识综合：行为金融 + 市场微观结构 + 宏观经济同时整合
- 快速生成探索性分析脚本，驱动假设精化

**v2 的真正瓶颈**：Qlib 回测执行时间（5-10 分钟/次）

**因此 v2 核心架构原则**：
> **用廉价的 LLM 阶段大量生成候选，逐层筛选，只将最有价值的候选推进到昂贵的回测阶段。**

这是**高通量漏斗**（参考药物发现 pipeline），不是线性管线。

### 学术支撑

| 论文 | 核心验证点 |
|---|---|
| AlphaAgent (arXiv:2502.16789) | 三维前置过滤 + 漏斗架构，CSI300 验证 |
| RD-Agent (arXiv:2505.15155) | 文档驱动接口，Research/Development 层分离 |
| QuantaAlpha (arXiv:2602.07085) | 探索性轨迹 + 收敛到公式表达式 |
| CogAlpha (arXiv:2511.18850) | 多层智能体质量检验体系 |
| QuantAgent (arXiv:2402.03755) | 双循环：内循环精炼 + 外循环市场验证 |

---

## 2. 系统分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        产品接入层                                 │
│  Terminal CLI (evoquant run)    │  Web Dashboard (后台监控)       │
└─────────────────────────────────────────────────────────────────┘
                                ↕
┌─────────────────────────────────────────────────────────────────┐
│                      Orchestrator 层                             │
│  LangGraph StateGraph + Island Scheduler + Human interrupt()     │
└─────────────────────────────────────────────────────────────────┘
                                ↕
┌─────────────────────────────────────────────────────────────────┐
│                    五阶段漏斗 (核心研究循环)                        │
│                                                                   │
│  Stage 1        Stage 2        Stage 3     Stage 4    Stage 5    │
│  宽扫描    →   并行假设生成  →  前置过滤 →  执行层  →  判断综合  │
│  [极低成本]    [低成本×N]     [低成本]    [高成本]   [低成本]    │
└─────────────────────────────────────────────────────────────────┘
                                ↕
┌─────────────────────────────────────────────────────────────────┐
│                       数据与工具层                                │
│  Qlib Engine │ MCP Servers (AKShare/ChromaDB) │ FactorPool v2    │
│  Docker Sandbox │ News Feed │ Academic Factor Library             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 五阶段漏斗详解

### Stage 1：宽扫描（MarketContext 生成）
**成本**：极低（LLM 读取，无回测）
**目标**：为本轮研究建立市场上下文

输入：AKShare 实时数据、新闻 RSS、FactorPool 历史摘要
输出：`MarketContextMemo`（结构化，见 Interface Contracts Spec）

**Agent**：
- `MarketAnalyst`：北向资金/宏观信号/热点板块综合
- `LiteratureMiner`：从 FactorPool + 学术因子库检索相关历史

### Stage 2：并行假设生成
**成本**：低，可横向扩展
**目标**：利用 LLM 并行能力，一次生成多个研究方向

输入：`MarketContextMemo` + Island 配置 + FactorPool 摘要
输出：批量 `FactorResearchNote`

**Agent**：
- `AlphaResearcher × N`：每个活跃 Island 分配一个，并行运行
- `SynthesisAgent`：检测跨 Island 的关联假设，避免重复

**关键设计**：Researcher 可以在 Note 中提出探索性问题（`exploration_questions` 字段），这些问题将在 Stage 4 由 ExplorationAgent 执行。

### Stage 3：三维前置过滤
**成本**：低（无回测，规则+小模型）
**目标**：在进入昂贵回测前淘汰明显无效候选，只保留 Top K（默认 K=5）

三个过滤器串行执行（任一失败即淘汰）：

| 过滤器 | 实现 | 检验内容 |
|---|---|---|
| Filter A: Validator | 规则引擎（无 LLM） | Qlib 语法合法性 + A 股硬约束 |
| Filter B: Novelty | 向量相似度（无 LLM） | AST 相似度 vs FactorPool（防重复） |
| Filter C: Alignment | 快速 LLM 调用 | 经济直觉与公式方向语义一致性 |

### Stage 4：执行层
**成本**：高（Qlib 回测 5-10 分钟/次）
**目标**：执行回测，获得真实性能数据

两类执行路径：

**4a. ExplorationAgent**（按需，服务 Researcher 探索性问题）：
- 输入：`FactorResearchNote.exploration_questions`
- 行为：生成 pandas/numpy EDA 脚本 → Docker 沙箱执行 → 返回统计结果
- 输出：`ExplorationResult`，反馈给 AlphaResearcher 精化公式
- **不生成最终因子**，只产生分析见解

**4b. Coder**（确定性，无 LLM 主体）：
- 输入：最终 Qlib 公式表达式（来自 `FactorResearchNote.final_formula`）
- 行为：将公式填入标准 Qlib 回测模板 → Docker subprocess 执行 → 解析 stdout JSON
- 输出：`BacktestReport`
- **重要**：Coder 不使用 Claude Code，不调用任何 LLM，是纯确定性 Python 函数

### Stage 5：判断与综合
**成本**：低
**目标**：评估结果，维护 FactorPool，生成 CIO 报告

**Agent**：
- `Critic`：多维阈值判断（Sharpe/IC/ICIR/换手率），写入 FactorPool
- `RiskAuditor`：过拟合检测 + 与现有因子相关性矩阵分析（新增）
- `PortfolioManager`：跨 Island 最优因子组合 + 权重分配（新增）
- `ReportWriter`：生成 CIO 可读 Markdown 报告 → 触发 `interrupt()`

---

## 4. Agent 团队完整清单

| Agent | 阶段 | 模型 | 类型 |
|---|---|---|---|
| MarketAnalyst | Stage 1 | deepseek-chat | LLM |
| LiteratureMiner | Stage 1 | deepseek-chat | LLM + RAG |
| AlphaResearcher | Stage 2 | deepseek-chat | LLM |
| SynthesisAgent | Stage 2 | deepseek-chat | LLM |
| Validator | Stage 3 | 规则引擎 | 确定性 |
| NoveltyFilter | Stage 3 | 向量相似度 | 确定性 |
| AlignmentChecker | Stage 3 | 小模型（快速）| LLM |
| ExplorationAgent | Stage 4 | deepseek-chat / GLM-5 | LLM + 代码执行 |
| Coder | Stage 4 | **无 LLM** | 确定性模板执行 |
| Critic | Stage 5 | 规则引擎 + LLM 归因 | 混合 |
| RiskAuditor | Stage 5 | 统计模型 | 确定性 + LLM 解释 |
| PortfolioManager | Stage 5 | deepseek-chat | LLM |
| ReportWriter | Stage 5 | claude-sonnet | LLM |

**总计**：13 个 Agent（vs v1 的 4 个）

---

## 5. 关键接口原则（文档驱动）

> 这是 v1 和 v2 最核心的差异。

**v1**：Agent 之间通过松散 dict 传递数据，接口隐式约定。
**v2**：所有 Agent 之间交换的是**强类型 Pydantic 模型**，接口显式定义，版本化管理。

完整 schema 定义见：`docs/specs/v2_interface_contracts.md`

主要文档类型：
- `MarketContextMemo`：Stage 1 输出
- `FactorResearchNote`：Stage 2 输出，Stage 3-4 输入
- `ExplorationRequest` / `ExplorationResult`：Stage 4a I/O
- `BacktestReport`：Stage 4b 输出
- `CriticVerdict`：Stage 5 Critic 输出
- `PortfolioAllocation`：Stage 5 PM 输出
- `CIOReport`：Stage 5 最终人机交互文档

**规则**：任何 Agent 不得直接读写另一个 Agent 的内部状态，只能通过上述文档类型通信。

---

## 6. 人机交互设计

### 产品形态（双模式）

```
evoquant run --mode evolve --rounds 20     # 启动后台研究循环
evoquant status                            # 查看当前状态
evoquant approve --factor-id xxx          # 审批因子上线
```

后台运行时，Web Dashboard 提供实时监控（因子池状态、Island 进度、最新 Sharpe 排行）。

### 三层人类介入

| 层级 | 触发条件 | 人类操作 |
|---|---|---|
| 自动 | Stage 1-4 正常运行 | 无需介入 |
| 通知 | 异常（崩溃/连续失败>10/Sharpe 骤降）| 告警推送 |
| 审批 | ReportWriter 完成 CIO 报告 | `/approve` `/redirect` `/stop` |

---

## 7. 与 v1 的迁移策略

执行时，**不要在 v1 代码上打补丁**，而是：

1. 保留 `src/agents/` 目录结构，但每个 Agent 文件从新 Spec 重写
2. 保留 `src/factor_pool/` 的 FactorPool 类，扩展 schema（见 v2_factorpool.md）
3. 保留 `src/core/orchestrator.py`，按 v2_orchestrator.md 重写 LangGraph 图
4. 删除 `src/sandbox/`（Claude Code 适配器），替换为新 `src/execution/` 模块
5. 所有新 schema 放入 `src/schemas/`（新目录）
6. 测试：迁移现有 32 个测试，新增每个新 Agent 的单元测试

---

## 8. 实施顺序

按以下顺序阅读和执行 Spec 文档：

1. **本文档**（已读）
2. `v2_interface_contracts.md` — 先理解所有数据结构
3. `v2_orchestrator.md` — 理解整体调度逻辑
4. `v2_stage4_execution.md` — **优先修复 Coder 层**（当前最脆弱）
5. `v2_stage3_prefilter.md` — 扩展现有 Validator
6. `v2_stage5_judgment.md` — 扩展现有 Critic，新增 Risk Auditor + PM + Report Writer
7. `v2_stage1_market_context.md` — 新增 Stage 1 Agent
8. `v2_stage2_hypothesis_generation.md` — 扩展为并行 Researcher
9. `v2_factorpool.md` — ChromaDB schema 更新
10. `v2_terminal_dashboard.md` — CLI + Dashboard 产品层

每完成一个 Spec 的实施，运行 `pytest tests/ -v` 确保无回归后再进行下一个。
