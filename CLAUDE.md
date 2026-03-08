# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

**EvoQuant** 是一个自主 AI 量化研究平台，面向中国 A 股市场（沪深 300/500）。核心思路是用 LLM 多智能体协作替代人类量化研究员，自动提出 Alpha 因子假设、编写回测代码、评估结果并迭代优化，直到跑赢基线策略。人类角色从研究员转变为 CIO（首席投资官），只需审批 AI 生成的研究报告。

底层量化引擎基于 **Microsoft Qlib**，使用 Alpha158 因子库 + LightGBM 作为数据骨干和竞争基线。

## 常用命令

```bash
# 环境激活（必须先做）
conda activate evoquant
cd EvoQuant

# 1. 下载沪深 300 日线数据（AKShare）
python -m src.data_pipeline.data_downloader

# 2. 转换为 Qlib 二进制格式
python -m src.data_pipeline.format_to_qlib

# 3. 跑 Alpha158+LightGBM 基线（确立 Sharpe=2.67 目标）
python -m src.core.run_baseline

# 4. 单次实验（单 Island，调试用）
python -m src.core.orchestrator --mode single --island momentum

# 5. 进化大循环（多 Island，正式搜索）
python -m src.core.orchestrator --mode evolve --rounds 20

# 6. 跑测试套件
python -m pytest tests/ -v

# 7. 前端 CIO 审批面板（Phase 3，待开发）
cd frontend && npm install && npm run dev
```

## 架构

### LangGraph 智能体循环

```
IslandScheduler（softmax 选方向）
    ↓
START → [Researcher] → [Validator] → [Coder] → [Critic] → FactorPool 注册
              ↑___________(内循环，最多 3 次)_______________|
外循环：多 Island 轮换，温度退火，Island 重置
```

- **Researcher**（`src/agents/researcher.py`）：DeepSeek-reasoner，调用 AKShare + ChromaDB MCP 工具获取实时数据和历史因子，输出结构化 `FactorHypothesis` JSON。由 `SkillLoader` 动态注入行为规范。
- **Validator**（`src/agents/validator.py`）：括号匹配 + A 股硬约束检查（禁止 Ref 负偏移、非法字段名、Log 安全）。
- **Coder**（`src/agents/coder.py`）：GLM-5，在 Docker 沙箱（`evoquant-coder:latest`）中执行，输出 `BACKTEST_METRICS_JSON`。
- **Critic**（`src/agents/critic.py`）：多维评估 Sharpe > 2.67 AND IC > 0.02 AND ICIR > 0.3 AND 换手率 < 50%。把失败原因写入 `error_message` 反馈给 Researcher。
- **FactorPool**（`src/factor_pool/pool.py`）：ChromaDB 持久化，6 个 Island 分组，支持 error-driven RAG 检索相似失败案例。
- **IslandScheduler**（`src/factor_pool/scheduler.py`）：softmax 采样选 Island，温度退火（T: 1.0→0.3），best_sharpe < 1.5 且 ≥ 3 次触发重置。
- **共享状态**（`src/agents/state.py`）：`AgentState` 包含 `factor_hypothesis`（结构化）、`backtest_metrics`（结构化）、`island_name`、兼容旧字段 `factor_proposal`。

### Qlib 基线配置

- 训练集：2021-06-01 ~ 2024-06-30 | 验证集：2024-07-01 ~ 2025-03-31 | 测试集：2025-04-01 ~ 2026-02-24
- 每日选前 50 只股票等权配置，约 0.2% 往返手续费
- 基线 Sharpe：**2.67**

### 数据管线（`src/data_pipeline/`）

| 文件 | 作用 |
|---|---|
| `data_downloader.py` | 通过 AKShare/Yahoo 下载沪深 300 OHLCV 日线 |
| `format_to_qlib.py` | 将原始 CSV 转为 Qlib 原生二进制 `.bin` 格式 |
| `news_sentiment_spider.py` | 抓取金十/东方财富 RSS 宏观新闻（Researcher 的 Layer 3 上下文） |

### MCP Servers（`mcp_servers/`）

| Server | 工具数 | 主要功能 |
|---|---|---|
| `akshare_server.py` | 7 | 北向资金、主力资金流、北向持股、券商研报、行业 PE、个股资金排行 |
| `chromadb_server.py` | 4 | FactorPool 查询：Island 最优、相似失败、排行榜、全局统计 |

### Skills 系统（`knowledge/skills/`）

三类 Skill，由 `src/skills/loader.py` 的 `SkillLoader` 动态注入：

| 类型 | 文件 | 注入条件 |
|---|---|---|
| A - 硬约束 | `constraints/a_share_constraints.md` | 永久（T+1/涨跌停/停牌/生存偏差） |
| A - 硬约束 | `constraints/qlib_formula_syntax.md` | 永久（合法算子列表） |
| B - 流程 | `researcher/alpha_generation.md` | 永久 |
| C - 上下文 | `researcher/island_evolution.md` | iteration > 0 时 |
| C - 上下文 | `researcher/feedback_interpretation.md` | 有 error_message 时 |

### FactorPool Island 定义

6 个研究方向：`momentum`（动量）、`northbound`（北向资金）、`valuation`（估值）、`volatility`（波动率）、`volume`（量价）、`sentiment`（情绪）

数据库路径：`data/factor_pool_db/`

### Docker 沙箱（`docker/`）

`Dockerfile.coder` 构建 Coder 执行环境（`evoquant-coder:latest`，1.94GB）：
- Python 3.12 + Qlib + Node.js + GLM/Claude Code CLI
- 只读挂载 `data/qlib_bin/`，可写 `src/sandbox_workspace/`
- 无外网访问（仅允许 LLM API 端点）

## 四阶段路线图

| 阶段 | 代号 | 目标 | 状态 |
|---|---|---|---|
| 1 | Skateboard | 数据管线 + Alpha158/LightGBM 基线 | ✅ 完成（Sharpe 2.67） |
| 2 | Bicycle | LangGraph + Island 进化 + MCP + FactorPool | ⚠️ 80%（端到端实验中） |
| 3 | Car | React CIO 审批面板 + LangGraph interrupt() | 规划中 |
| 4 | Self-Driving | QMT/Ptrade 券商 API 实盘对接 | 未来 |

## 环境与依赖

- **conda 环境**: `evoquant`（Python 3.11）—— 所有命令在此环境下运行
- **核心依赖**: `pyqlib>=0.9.7`、`langgraph`、`langchain-anthropic`、`langchain-mcp-adapters`、`akshare`、`chromadb`、`lightgbm`、`fastmcp`、`langchain-openai`
- **LLM 配置**（`.env`）：Researcher=DeepSeek-reasoner（官方API），Coder=GLM-5（阿里云DashScope代理）
- **数据**: `EvoQuant/data/qlib_bin/`（Qlib 二进制，沪深300日线）
- **测试**: `python -m pytest tests/ -v`（32/32 通过）

## 目录结构

```
EvoQuant/
├── src/
│   ├── agents/          # Researcher、Validator、Coder、Critic + schemas + state
│   ├── core/            # orchestrator.py（LangGraph + Island 进化）、run_baseline.py
│   ├── factor_pool/     # FactorPool（ChromaDB）、islands.py、scheduler.py
│   ├── skills/          # SkillLoader（动态 Skill 注入）
│   ├── data_pipeline/   # 数据下载、Qlib 格式转换
│   └── sandbox/         # Claude Code 适配器
├── mcp_servers/         # AKShare MCP Server、ChromaDB MCP Server
├── knowledge/
│   ├── factors/         # quant_factors_dictionary.md（Alpha 因子参考）
│   └── skills/          # A 股约束、Qlib 语法、Island 进化、失败解读
├── data/
│   ├── qlib_bin/        # Qlib 二进制数据（沪深300日线）
│   └── factor_pool_db/  # ChromaDB 持久化数据库
├── docs/
│   ├── research/        # strategy_discussion.md（研究讨论记录）
│   └── specs/           # Gemini 实施规格文档
├── tests/               # pytest 测试套件（32 个测试）
├── docker/              # Coder 沙箱 Dockerfile
├── frontend/            # React + Vite CIO 面板（待开发）
└── mlruns/              # MLflow 实验追踪
```
