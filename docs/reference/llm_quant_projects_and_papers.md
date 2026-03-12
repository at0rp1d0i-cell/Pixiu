# LLM 量化研究项目与论文索引

> 最后更新：2026-03-08

这份文档属于长期参考资料，而不是当前实现真相。

使用方式：

- 需要理解外部参照物、论文脉络和可借鉴项目时查阅这里
- 需要知道当前 Pixiu 采用了什么设计时，回到 `docs/overview/` 和 `docs/design/`

---

## P0 级 — 必须深度研究（直接竞争/参照对象）

### 开源项目

| 项目 | URL | 核心价值 |
|------|-----|---------|
| **Microsoft RD-Agent** | https://github.com/microsoft/RD-Agent | Qlib + LLM 自动化因子研究，Pixiu 的直接参照物之一。Apache 2.0，MSRA 维护。弱点：Azure 锁定、无 A 股深度特化、无实盘层 |
| **LangChain MCP Adapters** | https://github.com/langchain-ai/langchain-mcp-adapters | MCP Server 接入 LangGraph 的桥梁，是当前工具边界方案的重要参考 |
| **DeepSeek-R1** | https://github.com/deepseek-ai/DeepSeek-R1 | 开源权重，中文金融推理强，可本地部署作为私有化 Researcher 后端 |

### 学术论文

| 论文 | arXiv | 年份 | 核心贡献 | 与 Pixiu 的关联 |
|------|-------|------|---------|------------------|
| **AlphaAgent** | 2502.16789 | 2025 | 三维前置过滤漏斗（复杂度/语义对齐/新颖性）+ ICRank 评估 | **Stage 3 PreFilter 直接蓝本** |
| **RD-Agent (Microsoft)** | 2505.15155 | 2025 | 文档驱动接口，Research→Development 分离，YAML/JSON 任务对象 | **核心接口设计原则** |
| **QuantaAlpha** | 2602.07085 | 2026 | 探索性轨迹变异 + 收敛到因子表达式 + 语义一致性约束 | **Exploration Agent 设计** |
| **CogAlpha** | 2511.18850 | 2025 | 七层智能体层次 + 21 个 Agent 质量检验体系 | **Agent 团队规模参考** |
| **QuantAgent (Huawei)** | 2402.03755 | 2024 | 双循环架构：内循环=写代码试错，外循环=知识提取存入向量库 | **Island 进化外循环** |
| **Alpha-GPT 2.0** | — | 2024 | LLM 迭代挖因子的学术范式验证，多轮 Researcher→回测→反馈循环 | 漏斗架构的早期验证 |
| **FinMem** | — | 2024 | 三层分层记忆（工作/情节/语义） | FactorPool v2 三集合设计参考 |

---

## P1 级 — 短期内借鉴

### 开源项目

| 项目 | URL | 借鉴点 |
|------|-----|--------|
| **TradingAgents** | https://github.com/TauricResearch/TradingAgents | LangGraph 多智能体交易框架。特色：多分析师团队（基本面/情绪/新闻/技术）+ Bull vs Bear 辩论机制 + Risk Manager 层。**借鉴：** Stage 1 多分析师分工、CriticVerdict 反驳机制、RiskAuditor 层级设计 |
| **VNPy** | https://github.com/vnpy/vnpy | 事件驱动 Reactor 模式 + Gateway 抽象 + 26+ 券商接入。**借鉴：** 事件驱动解耦、标准网关接口（Phase 4 实盘对接） |
| **Dexter** | https://github.com/virattt/dexter | LLM 任务分解 + JSONL 审计日志 + LLM-as-Judge。**借鉴：** 可审计性设计、多提供商 LLM 支持、结构化日志 |
| **FinGPT** | https://github.com/AI4Finance-Foundation/FinGPT | ChatGLM/LLaMA 金融微调，可作本地情绪分析因子引擎（~14k stars） |
| **FinRobot** | https://github.com/AI4Finance-Foundation/FinRobot | 多Agent金融平台，参考其Agent角色设计；弱点：无真正回测循环 |
| **Smolagents (HF)** | https://github.com/huggingface/smolagents | 轻量级Agent框架，备选 Researcher 实现方案 |
| **Nautilus Trader** | https://github.com/nautilus-trader/nautilus_trader | Rust核心+Python接口，Phase 4 实盘执行层的候选 |
| **Polars** | https://github.com/pola-rs/polars | 替代 Pandas，数据管线提速 10-100x |
| **pytorch-forecasting (TFT)** | https://github.com/jdb78/pytorch-forecasting | Temporal Fusion Transformer 生产级实现 |
| **MCP Protocol Spec** | https://modelcontextprotocol.io | Anthropic MCP 协议规范 |

### 学术论文

| 论文 | 年份 | 核心贡献 |
|------|------|---------|
| **Temporal Fusion Transformers** | 2021 (IJF) | 多时域时序预测+可解释注意力权重；A股5日收益预测优于LSTM |
| **FunSearch (DeepMind)** | 2024 | LLM 进化搜索数学解，可改造为"因子群体进化"替代单路迭代 |

---

## P2 级 — 中长期参考

### 开源项目

| 项目 | URL | 借鉴点 |
|------|-----|--------|
| **FinRL** | https://github.com/AI4Finance-Foundation/FinRL | RL 驱动仓位管理，Phase 4 替代等权配置（~10k stars） |
| **OpenBB** | https://github.com/OpenBB-finance/OpenBBTerminal | 开源 Bloomberg 替代，MCP Server 在开发中 |
| **Qlib Model Zoo** | https://github.com/microsoft/qlib/tree/main/qlib/contrib/model | 内置 ALSTM, GATs, TFT, Double Ensemble 等，可直接对比 |
| **PyO3** | https://github.com/PyO3/pyo3 | Python+Rust 绑定，Phase 4 性能优化备选 |
| **pykan (KAN)** | https://github.com/KindXiaoming/pykan | 可解释性因子公式发现，金融领域探索中 |
| **pytorch_geometric** | https://github.com/pyg-team/pytorch_geometric | GNN 实现，行业关联图建模 |
| **Mamba SSM** | https://github.com/state-spaces/mamba | 长序列状态空间模型，长历史窗口因子的实验选项 |

### 学术论文

| 论文 | 年份 | 核心贡献 |
|------|------|---------|
| **TradingGPT** | 2024 | 增加 Risk Manager Agent 角色的多Agent交易框架 |
| **Mamba (Gu & Dao)** | 2023 | 线性复杂度序列建模，500日回望不爆显存 |
| **KAN (MIT/Caltech)** | 2024 | 函数逼近网络，可输出符号化表达式 |
| **TabPFN v2** | 2024 | 小样本表格数据的上下文学习，无需训练的快速因子验证器 |

---

## 数据源参考

### 机构级（高成本高质量）

| 数据源 | 费用 | 核心价值 |
|--------|------|---------|
| 万得 Wind WSD | ¥5-20万/年 | A股机构级标准，研报结构化数据 |
| 东方财富 Choice数据 | ¥3-8万/年 | 最佳研报元数据覆盖（标题/分析师/评级/目标价） |
| 同花顺 iFinD | ¥3-8万/年 | 分析师一致预期聚合（EPS FY1/FY2/FY3） |

### 中等成本（推荐起步）

| 数据源 | 费用 | 核心价值 |
|--------|------|---------|
| Tushare Pro | ~¥1000-5000/年 | 机构持股、分析师预测、公告 |
| 聚宽 JoinQuant | ~¥3000-8000/年 | 预计算 Alpha101 因子、CSI300 点时成分 |

### 免费层（已用或待整合）

| 数据源 | URL | 核心价值 |
|--------|-----|---------|
| AKShare | https://akshare.akfamily.xyz | 研报元数据：`ak.stock_research_report_em()` |
| BaoStock | http://baostock.com | 复权历史数据（已用） |
| 证监会/上交所 RSS | 官方网站 | 监管公告（零延迟权威信源） |
| Tavily | https://tavily.com | AI优化的新闻检索（daily_stock_analysis已验证） |

---

## LangGraph 关键文档

| 功能 | URL |
|------|-----|
| Human-in-the-loop interrupt | https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/ |
| Streaming | https://langchain-ai.github.io/langgraph/how-tos/streaming/ |
| Persistence | https://langchain-ai.github.io/langgraph/concepts/persistence/ |
| MLflow 追踪 | https://mlflow.org/docs/latest/tracking.html |
