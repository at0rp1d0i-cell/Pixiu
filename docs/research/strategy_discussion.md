# EvoQuant 战略讨论文档

> 持续更新，记录每轮讨论的结论与建议
> 最后更新：2026-03-04

---

## 第一轮讨论：项目审阅

### 项目现状总结

| 阶段 | 状态 | 备注 |
|------|------|------|
| Phase 1 Skateboard | ✅ 完成 | Sharpe 2.67 已确立，数据管线可用 |
| Phase 2 Bicycle | ⚠️ 60% | LangGraph 框架搭好，Docker沙箱未构建 |
| Phase 3 Car | ❌ 未开始 | /frontend/ 是空目录 |
| Phase 4 Self-Driving | ❌ 未开始 | 无券商API接入 |

### P0 级立即修复清单

1. API Key 硬编码在源码中 → 迁移到 `.env` + `python-dotenv`
2. 无 `requirements.txt` → 添加并锁定版本
3. Docker 镜像从未构建 → `docker build -f docker/Dockerfile.coder -t evoquant-coder:latest .`
4. 使用 `print()` 而非 `logging` → 引入标准日志框架
5. Critic 靠正则解析自由文本 → 改为结构化 JSON 输出

---

## 第二轮讨论：五大战略问题

### Q1：daily_stock_analysis 引入方案

**结论：只取三个模块，不全盘复制**

| 模块 | 价值 | 改造方式 |
|------|------|----------|
| `data_provider/`（6数据源统一接口） | 高 | 替换现有单一BaoStock接入 |
| `search_service.py`（Tavily/SerpAPI新闻聚合） | 高 | 替代占位的 `news_sentiment_spider.py` |
| `trading_calendar.py`（交易日历） | 中 | 防止非交易日浪费LLM调用 |

**不引入：** LLM分析管线、通知推送（Phase 3再做）、内置策略（提取文字描述即可）

---

### Q2：Skills + MCP 标准化 Agent 方案

**推荐架构：**

```
EvoQuant/
├── mcp_servers/
│   ├── akshare_server.py      # OHLCV、基本面、北向资金
│   ├── qlib_server.py         # 因子评估、IC/Sharpe/换手率
│   ├── chromadb_server.py     # 向量检索历史因子
│   ├── news_server.py         # 金十/东财RSS、证监会公告
│   └── backtest_server.py     # 触发Docker沙箱回测
└── knowledge/
    ├── factors/               # 因子字典（已有）
    ├── skills/
    │   ├── factor_hypothesis.md   # 提因子假设的标准Skill
    │   ├── backtest_debug.md      # 回测失败调试Skill
    │   ├── ic_analysis.md         # IC衰减分析Skill
    │   └── regime_detection.md    # 市场状态识别Skill
    └── constraints/
        └── china_market_rules.md  # T+1、涨跌停、停牌规则
```

**集成方式：** 用 `langchain-mcp-adapters` 将 MCP Server 暴露为 LangGraph 工具，每个 Agent 只访问它需要的工具（最小权限原则）。

---

### Q3：是否开源以及盈利路径

**结论：Apache 2.0 开源核心，商业化增值服务**

| 开源部分 | 商业化部分 |
|----------|-----------|
| 数据管线、Agent框架、因子字典 | 已验证的高Sharpe因子库 |
| 基线回测代码 | 实盘对接层（QMT/Ptrade） |
| MCP Server 实现 | CIO面板 SaaS托管版 |

**盈利路径：**
1. 因子即服务（Factor-as-a-Service）订阅
2. 托管版 SaaS（CIO审批 + 自动回测 + 信号推送）
3. 私募/量化团队定制咨询
4. "AI量化研究员"培训课程

**开源前必做：** 移除所有硬编码 Key + 添加 `.env.example` + 补 `pyproject.toml` + 至少 10 个核心单元测试

---

### Q4：值得借鉴的开源项目和论文

详见：`docs/research/references.md`

---

### Q5：安全性与 Token 消耗控制

**安全层级：**

| 层级 | 措施 | 优先级 |
|------|------|--------|
| 密钥管理 | `.env` + `python-dotenv` + `.gitignore` | P0 |
| 沙箱隔离 | Docker只读挂载 + 无外网 | P1 |
| 代码扫描 | 禁止 `os.system`/`subprocess`/网络调用 | P1 |
| 审计日志 | JSON Lines 结构化日志 | P2 |

**Token 消耗控制——多层防御：**

```
Layer 1: 硬性上限
├── max_iterations = 3（已有）
├── max_tokens_per_run = 100,000（新增）
└── LangGraph recursion_limit

Layer 2: 收敛检测（新增）
├── Sharpe增量 < 0.05 连续2轮 → 提前终止
├── 重复因子检测（余弦相似度 > 0.9 → 拒绝）
└── 状态哈希检测死循环

Layer 3: 成本优化
├── Prompt Caching（系统提示+因子字典固定 → 缓存后降90%成本）
├── 分级模型（Validator/Critic用Haiku，Researcher用Sonnet/Opus）
└── LangFuse/LangSmith 可观测性追踪

Layer 4: 优雅退出
└── 超预算时保存最佳结果，生成总结报告
```

**单轮成本估算：** ~$0.03，3轮最大约 ~$0.10，成本完全可控

---

## 第三轮讨论：六大深化问题

### Q1：我们的优势在哪里？如何在大厂方案中脱颖而出？

**竞争格局对比：**

| 平台 | 因子研究循环 | A股专项 | 实盘交易 | 开源 | 个人友好 |
|------|------------|---------|---------|------|---------|
| **EvoQuant（本项目）** | LLM循环 | 深度 | Phase 4 | ✅ | ✅ |
| Microsoft RD-Agent | LLM循环 | 浅 | ❌ | ✅ | ❌（依赖Azure） |
| Alpha-GPT 2.0 | LLM循环 | 中 | ❌ | 部分 | 中 |
| QuantAgent（华为） | ❌ | 中 | ❌ | 部分 | ❌（华为生态） |
| FinRobot | 浅 | 浅 | ❌ | ✅ | 中 |
| 聚宽/米筐 LLM | 中 | 深度 | ✅ | ❌ | ❌（SaaS） |

**核心差异化优势（大厂做不到的）：**

1. **A股市场深度特化**
   - T+1规则约束（大厂不会硬编码）
   - 涨跌停板机制（10%限制对因子构建的影响）
   - 北向资金（沪深港通）作为实时机构信号
   - 政策冲击敏感性（证监会公告、央行降息）
   - 零售主导（70%散户）的动量/反转特征
   - 将以上规则硬编码进 Critic Agent 评估标准，是真正的质量护城河

2. **完整闭环产品（研究→审批→实盘）**
   - RD-Agent 和 FinRobot 都止步于研究，EvoQuant 目标是全栈打通

3. **更快的迭代速度**
   - Claude Opus 4 发布后可在数天内集成，微软内部审批周期要几个月

4. **DeepSeek-R1 作为本地 Researcher**
   - 零API成本 + 无数据隐私顾虑（机构采购关键点）
   - 中文金融文本理解更强
   - RD-Agent 和 FinRobot 都依赖 OpenAI API

5. **CIO 人机协作工作流**
   - 所有竞争对手都没有正式的人类审批层，Phase 3 的 React CIO 面板是真正的产品差异化

6. **中文社区生态**
   - 英文社区为主的 RD-Agent 没有覆盖知乎+量化交流群的中国用户

**2026年3月可利用的新技术：**

| 技术 | 用途 | 优先级 |
|------|------|--------|
| MCP Protocol + `langchain-mcp-adapters` | 工具调用标准化，AKShare/Qlib变成原生工具 | P1 |
| Claude Extended Thinking | Researcher生成因子时深度推理（预算8k-16k tokens） | P1 |
| LangGraph `interrupt()` | Phase 3 CIO审批工作流的技术基础 | P1 |
| DeepSeek-R1（本地部署） | 零成本私有化Researcher，机构客户的关键 | P2 |
| LLM 结构化输出（JSON Schema） | 消除Critic的正则解析脆弱性 | P0 |
| Polars 替代 Pandas | 数据处理性能提升 10-100x | P2 |

---

### Q2：文档保存

本文档持续更新。论文参考另见 `docs/research/references.md`

---

### Q3：高质量信息获取方案

**数据源层级（由低到高成本）：**

**免费/低成本层：**
- AKShare：日行情、指数成分、北向资金、宏观数据（已用）
- BaoStock：复权数据（已用）
- 证监会/上交所/深交所 官方RSS：监管公告（零延迟、权威）
- EFinance：东方财富实时行情
- Tushare（免费额度）：基本面、公告

**中等成本层（关键推荐）：**
- **Tushare Pro**（~¥2000/年）：机构持股、分析师预测、研报摘要
- **聚宽 JoinQuant**（按量付费）：Alpha因子库、财务预测数据
- **掘金量化**：事件驱动数据（业绩预警、股权变动）

**每日研报获取方案（重要！）：**
- **方案A（免费）：** 各大券商官网PDF + PyMuPDF解析 + Claude摘要提取
- **方案B（付费）：** 万得Wind API（机构级，¥数万/年）
- **方案C（中等）：** Choice数据（东方财富，~¥5000/年）
- **方案D（社区）：** 雪球、同花顺研报频道 + newspaper3k 抓取

**推荐的研报集成架构：**
```
研报爬取 → PDF解析（PyMuPDF）→ Claude摘要（结构化JSON）
    → 关键字段提取（目标价/评级/核心逻辑）
    → 向量化存入 ChromaDB
    → Researcher Agent 通过 RAG 检索相关研报
```

**新闻情绪因子化（将情绪转为 Qlib 因子）：**
```python
# 将每日情绪分值注册为 Qlib 自定义表达式
sentiment_factor = "Mean(news_sentiment_score, 5)"  # 5日滚动平均情绪
```

---

### Q4：量化模型选择（数学模型）

**2026年的模型格局：**

| 模型 | 类型 | A股实证效果 | 计算成本 | 推荐度 |
|------|------|-----------|---------|--------|
| LightGBM | GBDT | 已验证基线Sharpe 2.67 | 低 | ⭐⭐⭐⭐⭐（现有基线） |
| XGBoost | GBDT | 略差于LightGBM | 低 | ⭐⭐⭐⭐ |
| **Temporal Fusion Transformer (TFT)** | 注意力+LSTM | 时序依赖强时优于GBDT | 中 | ⭐⭐⭐⭐（强烈推荐探索） |
| **Mamba (SSM)** | 状态空间模型 | 长序列建模新SOTA | 中 | ⭐⭐⭐⭐（2025新锐） |
| TabPFN | 先验拟合网络 | 小样本强，大样本一般 | 低 | ⭐⭐⭐ |
| **GNN（图神经网络）** | 图结构学习 | 行业关联图建模有效 | 高 | ⭐⭐⭐（需更多工程） |
| KAN | 函数逼近 | 可解释性强，金融探索中 | 中 | ⭐⭐⭐（值得关注） |
| 纯Transformer | 序列模型 | A股噪音大，效果不稳定 | 高 | ⭐⭐（慎用） |

**务实建议：**
- **短期（Phase 2）：** 保持LightGBM作为基线评判标准，不要换
- **中期（Phase 3）：** 用 Qlib Model Zoo 对比测试 TFT 和 Mamba
- **关键洞察：** 模型的提升通常来自更好的因子，而非换模型。Researcher Agent 生成更好的因子 > 换更复杂的模型
- **GNN的A股应用：** 将行业分类、供应链关联、指数成分权重建图，捕捉股票间协同效应

**Qlib Model Zoo 可直接对比的模型：**
```bash
# Qlib 内置支持的模型（可直接用于EvoQuant对比实验）
ALSTM, GATs, LSTM, MLP, TabNet, TFT, LightGBM, XGBoost, DoubleEnsemble
```

---

### Q5：如何保障每步修改都服务于性能提升（控制变量）

**实验管理框架：**

```
每次实验必须记录：
├── 实验ID（MLflow Run ID）
├── 变更内容（单一变量，如：新增情绪因子）
├── 市场状态标记（牛市/熊市/震荡）
├── 超参数快照
├── 完整评估指标（Sharpe/IC/ICIR/MaxDD/换手率）
└── 对比基线（总是与 Sharpe=2.67 的 Alpha158 基线对比）
```

**控制变量协议（每次只改一个）：**

```
✅ 正确：新增"北向资金净流入"因子，其他一切不变，观察Sharpe变化
❌ 错误：同时新增因子+换模型+改回测窗口
```

**A/B 测试因子的标准流程：**
1. Train/Valid/Test 三集严格分离（已有）
2. 新因子先在 Valid 集验证，通过后才跑 Test
3. 记录 IC、ICIR、因子换手率（过高换手=过拟合信号）
4. 市场分层测试：牛市/熊市/震荡市分别计算 IC
5. 超过 2 个标准差的异常 Sharpe 视为过拟合

**MLflow 集成（目录已存在，需激活）：**
```python
import mlflow
with mlflow.start_run(run_name=f"factor_{factor_name}"):
    mlflow.log_param("factor_expression", formula)
    mlflow.log_param("model", "LightGBM")
    mlflow.log_metric("sharpe", sharpe_ratio)
    mlflow.log_metric("ic", information_coefficient)
    mlflow.log_metric("max_drawdown", max_dd)
    mlflow.log_artifact("equity_curve.png")
```

**防止数据窥视（Look-ahead Bias）的检查清单：**
- [ ] 因子构建只使用 `t-1` 日及以前的数据
- [ ] 财务数据使用实际公告日期，非报告期末日期
- [ ] Qlib `Ref()` 的偏移量不为负

---

### Q6：Python 语言会不会限制效率？是否考虑 Rust？

**结论：Python 作为粘合层 + 关键路径用 Polars/NumPy，Rust 暂不需要**

**Python 的瓶颈分析：**

| 环节 | 瓶颈程度 | 解决方案 |
|------|---------|---------|
| LLM API 调用 | 无（网络IO主导） | 异步并发（asyncio已够） |
| Qlib 因子计算 | 中（Pandas慢） | 换 **Polars**（10-100x加速） |
| LightGBM 训练 | 无（C++内核） | 已经很快 |
| Docker沙箱执行 | 无（进程级隔离） | 正常 |
| ChromaDB 向量检索 | 中（Python层） | 可换Milvus（Rust内核）|
| Qlib 数据读取（.bin） | 低（mmap） | 已优化 |

**实际建议：**
- **立即：** 把 `format_to_qlib.py` 和数据处理中的 Pandas 换成 **Polars**，性能提升显著且改动小
- **短期：** 使用 **Numba** JIT 编译自定义因子计算函数
- **中期：** 考虑 **Nautilus Trader**（Rust核心 + Python接口）替代自制回测引擎（Phase 4实盘时再决策）
- **不建议现在：** 完整重写为 Rust——LLM Agent 的瓶颈从不在 Python 计算，而在网络IO和LLM推理时间

**参考：哪些生产级量化系统用了 Rust？**
- Nautilus Trader（开源，Rust核心 + Python接口，适合高频）
- Databento（数据平台，Rust编写）
- QuantLib（C++，Python binding，低频量化够用）

**EvoQuant 的瓶颈从来不是 Python**，而是：LLM推理时间（1-10秒/次）、回测计算时间（LightGBM训练），这两个都不是 Python 慢的问题。

---

## 第四轮讨论：AKShare MCP Server 深度研究

> 基于实际 AKShare API 调用验证（2026-03-04 实测）

### 核心结论：哪些 AKShare API 值得包装成 MCP 工具

通过实测 AKShare，以下 API 可以稳定调用并返回有效数据：

#### 第一梯队（立即包装，高价值）

| AKShare 函数 | 数据内容 | 实测状态 | 因子潜力 |
|---|---|---|---|
| `stock_hsgt_fund_flow_summary_em()` | 北向/南向资金实时净流入（按市场分类） | ✅ 稳定 | 机构情绪强信号 |
| `stock_hsgt_hist_em(symbol='北向资金')` | 北向资金历史净买入序列 | ✅ 稳定 | 时序因子基础 |
| `stock_market_fund_flow()` | 全市场主力/超大单/大单净流入 | ✅ 稳定 | 资金面截面因子 |
| `stock_hsgt_hold_stock_em(market, indicator)` | 北向持股结构变化 | ✅ 稳定 | 个股被北向买入信号 |
| `stock_research_report_em(symbol)` | 股票券商研报（标题/机构/评级/目标价） | ✅ 稳定 | 分析师情绪聚合 |
| `stock_industry_pe_ratio_cninfo(symbol, date)` | 申万/证监会行业 PE 估值 | ✅ 稳定 | 估值分位因子 |

#### 第二梯队（延后，有替代品）

| 函数 | 问题 | 替代方案 |
|---|---|---|
| `index_news_sentiment_scope()` | ❌ 接口不稳定（JSON 解析失败） | 用 Tavily/SerpAPI 替代 |
| `macro_bank_china_interest_rate()` | ❌ 超时（数据源 jin10.com 经常挂） | 直接爬取央行官网 |

### 关键设计洞察：MCP Server vs 直接调用

**为什么要包装成 MCP Server？**

```
当前 Researcher 架构（闭门造车）：
  System Prompt（静态因子字典）→ LLM → 因子假设（只有知识，没有数据）

目标架构（数据驱动）：
  System Prompt + 实时 MCP 工具调用 → LLM → 因子假设（知识 + 实时市场数据）
```

Researcher 用 `get_northbound_flow_today()` 工具发现"今日北向净流入 47 亿"，
然后提出"北向资金净流入的5日动量 × 资金余额比率"这个更有针对性的因子假设 ——
这是现有架构完全做不到的。

### `langchain-mcp-adapters` 0.1.0 正确集成方式

从源码确认（见 `deep_dive_core_references.md` §3）：

```python
# ✅ 正确：不用 async with
client = MultiServerMCPClient(connections)
tools = await client.get_tools()

# ❌ 错误：0.1.0 已删除 context manager 支持
async with MultiServerMCPClient(connections) as client:  # NotImplementedError!
    ...
```

### Researcher Agent 改造后的效果对比

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 信息来源 | 静态因子字典 | 因子字典 + 实时北向/资金流/研报 |
| 因子质量 | 通用量化因子 | 当日市场状态感知的针对性因子 |
| 可解释性 | "动量因子一般有效" | "今日北向净买入 47 亿，建议构建北向5日动量因子" |
| CIO 信任度 | 低（理论推演） | 高（有实时数据支撑） |

### 实施决策：分两期

**Period 1（给 Gemini 做）：** AKShare MCP Server 核心版
详见 `docs/specs/akshare_mcp_server_spec.md`

**Period 2（未来）：** 研报 PDF 解析 + ChromaDB 向量存储接入

---

## 第五轮讨论：架构升级路线确认

### Gemini 交付记录（2026-03-04）

**AKShare MCP Server 任务 — 全部完成 ✅**

| 交付物 | 状态 | 备注 |
|---|---|---|
| `mcp_servers/akshare_server.py` | ✅ | 7 个工具，Gemini 用 FastMCP 替代了原始 mcp Server（API 变更） |
| `src/agents/researcher.py` | ✅ | 接入 `langchain-mcp-adapters`，agentic loop 已工作 |
| `tests/test_akshare_mcp.py` | ✅ | 6/6 全绿 |
| 端到端 `orchestrator.py` | ✅ | Researcher 成功拉起 MCP Session |

**遗留问题（发现于代码审阅）：**
- `researcher.py` line 44：API Key 仍有硬编码回退值（`sk-746...`），地基任务未完全覆盖这里
- Critic 仍是纯正则解析，无结构化输出

### 下一步任务确认

用户决策：
- **B（结构化 FactorHypothesis）+ D（增强 Critic）捆绑执行** — P0，豆腐渣接缝影响开发稳定性
- **A（FactorPool 进化架构）** — 后续最重要的架构升级
- Coder 模型考虑替换为国产低价模型（GLM-4 等）

模型策略讨论：
- Researcher：Claude Sonnet（工具调用能力强）或 DeepSeek-R1（零成本本地）
- Coder：GLM-4-Flash 或 DeepSeek-Coder（低价，代码能力够）
- Critic/Validator：最简单任务，Haiku 级别即可，或纯规则不调用 LLM

---

## 第六轮讨论：进化架构 + Skills/MCP 管理体系

### Gemini 交付记录（2026-03-05）

**结构化输出 + Critic 增强任务 — 全部完成 ✅**

Researcher 已替换为 GLM-5（阿里云 DashScope 代理），结构化解析 + 多维度 Critic 已全部落地。

---

### A：FactorPool 进化架构

**核心思路：单线程爬山 → 多 Island 进化搜索**

FunSearch → EvoQuant 映射：

| FunSearch | EvoQuant |
|---|---|
| Island | 因子家族（动量族/北向族/估值族/波动率族） |
| Program | 一个 FactorHypothesis（公式 + 回测指标） |
| Signature | (Sharpe, IC, ICIR) 三元组 |
| Cluster | 相同性能区间的因子组 |
| Sampler | 从 FactorPool 选 Island → 给 Researcher 历史上下文 |
| 温度退火 | 前期探索新方向，后期精炼最优方向 |
| Island 重置 | 定期淘汰最差 Island，用新方向替代 |

**关键设计决策：串行 Island 选择（不并发）**

每大轮按 softmax 抽样激活 1 个 Island，完成 Researcher→Coder→Critic 后更新 FactorPool。
Island 竞争通过历史成绩积累体现，无需真正并发。Token 成本约 $0.003/轮，完全可控。

**ChromaDB 作为 FactorPool 持久化层**

原因：Researcher 的关键查询是"找最相似的历史失败因子+修复方法"——正好需要向量检索。

---

### B：Skills + MCP 三层能力架构

**三层分离原则：**

```
Layer 1 - Skills（行为规则，Markdown）：决定 Agent 怎么思考
Layer 2 - MCP Tools（实时执行，Python）：决定 Agent 能做什么
Layer 3 - Knowledge RAG（ChromaDB）：决定 Agent 知道什么（按需检索）
```

**Skills 目录结构（目标状态）：**
```
knowledge/skills/
├── researcher/
│   ├── alpha_generation.md      ← 已有（重命名自 agent_skills/）
│   ├── market_regime_detect.md  ← 待写
│   ├── island_evolution.md      ← 待写（FactorPool 使用规范）
│   └── ic_analysis.md           ← 待写
├── coder/
│   ├── qlib_debugging.md        ← 已有
│   └── factor_implementation.md ← 待写
└── critic/
    ├── factor_evaluation.md     ← 待写
    └── a_share_constraints.md   ← 待写（T+1/涨跌停/连板）
```

**MCP Tools 目录规划：**
```
mcp_servers/
├── akshare_server.py     ← ✅ 已完成（7个工具）
├── chromadb_server.py    ← 下一优先级（FactorPool 核心）
├── qlib_server.py        ← 触发回测、读历史指标
└── news_server.py        ← 新闻情绪（后期）
```

**FactorPool 与 Skills 的交汇点：**

`chromadb_server.py` 暴露 4 个工具：
- `get_island_best_factors(island_name, top_k)` — 该 Island 历史最优
- `get_similar_failures(formula, top_k)` — 相似失败案例+原因（error-driven RAG）
- `register_factor(hypothesis, metrics)` — 存储新因子
- `get_island_leaderboard()` — 所有 Island 排行

`knowledge/skills/researcher/island_evolution.md` 规定 Researcher 行为：
先查历史成果 → 查失败案例 → 提出改进/突破 → 禁止相关性>0.8 的重复因子

---

## 第七轮讨论：Skills-based Agent Architecture

### Gemini 交付记录（2026-03-05）

**FactorPool ChromaDB 数据层 — 全部完成 ✅**

| 交付物 | 状态 |
|---|---|
| `src/factor_pool/islands.py` | ✅ 6 个 Island |
| `src/factor_pool/pool.py` | ✅ ChromaDB 封装，含 error-driven RAG |
| `mcp_servers/chromadb_server.py` | ✅ 4 个 MCP 工具 |
| `orchestrator.py` + `researcher.py` | ✅ 已注入 FactorPool |
| `tests/test_factor_pool.py` | ✅ 6/6 全绿 |

Gemini 额外建立了 `conda evoquant` 环境（Python 3.11），后续所有依赖安装在此环境。

---

### Skills 架构核心研究结论

**三类 Skill，职责严格分离：**

| 类型 | 注入方式 | 代表文件 | 优先级 |
|---|---|---|---|
| A - Rules（硬约束） | 永久注入所有相关 Agent | `a_share_constraints.md` | P0 |
| B - Process（流程规范） | 按 Agent 角色注入 | `alpha_generation.md` | P1 |
| C - Context（上下文感知） | 按 AgentState 条件注入 | `island_evolution.md` | P1 |

**最重要的两个缺失 Skill：**

1. `a_share_constraints.md`（Type A）
   - 前视偏差规则（财务数据使用实际披露日，非报告期末）
   - T+1 对因子时效性的影响（建议持仓 ≥ 5 日）
   - 涨跌停对成交的影响（涨停板不可买入）
   - 停牌股 NaN 处理规范
   - ST 股过滤规范
   - 指数成分股点时间问题（生存偏差防护）

2. `researcher/island_evolution.md`（Type C）
   - 强制工具调用顺序（先查历史 → 再查行情 → 再提假设）
   - 创新约束（公式编辑距离、IC 相关性阈值）
   - 按 Island 的方向约束（northbound Island 必须含北向变量）
   - 失败模式解读（Sharpe 低但 IC 高 → 换手率问题；IC 低 → 换方向）

**动态注入机制：`SkillLoader`**

```python
# src/skills/loader.py
class SkillLoader:
    def load_for_researcher(self, state: AgentState) -> str:
        # Type A: 永远注入
        # Type B: 永远注入
        # Type C: current_iteration > 0 才注入 island_evolution.md
        #         有 error_message 才注入 feedback_interpretation.md
```

好处：researcher.py 的 System Prompt 构建只剩一行调用，不再是大段 f-string。

---

## 建议执行顺序

### Sprint 1（本周）— 地基
1. 创建 `.env` + `pyproject.toml` + `.gitignore`
2. 全局替换 `print()` → `logging`
3. 激活 MLflow 实验追踪
4. 构建 Docker 镜像并测试 Coder 节点

### Sprint 2（第2-3周）— 验证核心循环
5. 端到端跑通一次 Researcher → Validator → Coder → Critic
6. 将 Critic 改为结构化 JSON 输出
7. 引入 Prompt Caching 降低成本

### Sprint 3（第4周）— 信息增强
8. 集成 Tavily/SerpAPI 新闻聚合
9. 引入研报 PDF 解析 + ChromaDB 存储
10. 将情绪分值注册为 Qlib 自定义因子

### Sprint 4（第2个月）— 标准化
11. 构建三个核心 MCP Server（AKShare、Qlib、News）
12. 引入 `langchain-mcp-adapters`
13. 创建标准化 Skills 文件库

### Sprint 5（第3个月）— 竞争差异化
14. DeepSeek-R1 作为备用 Researcher 后端
15. LangGraph `interrupt()` 实现 CLI 版 CIO 审批
16. 硬编码 A 股约束到 Critic（T+1、涨跌停、停牌）
