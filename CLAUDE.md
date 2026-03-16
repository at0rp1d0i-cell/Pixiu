# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Pixiu（貔貅）是一个 LLM-native 的 Alpha 研究平台，专为中国 A 股市场设计。它不是模拟人类量化团队，而是围绕 LLM 的优势重新设计研究流程——通过 5 阶段漏斗实现高吞吐量的假设生成、过滤和回测。

核心设计原则：**扩大 hypothesis space，不扩大 execution power**。

## 文档体系

在修改代码前，必须先阅读以下文档（按顺序）：

1. `docs/README.md` - 文档入口和目录结构
2. `docs/overview/architecture-overview.md` - 系统架构总览
3. `docs/overview/spec-execution-audit.md` - 设计与实现的对齐状态
4. `docs/design/` - 各模块的详细设计文档

**重要规则**：
- `docs/overview/` + `docs/design/` 是当前架构真相
- `docs/archive/` 仅保留历史材料，不指导当前实现
- 当设计与代码不一致时，先查 `spec-execution-audit.md`，再决定改设计还是改代码

## 核心架构

### 5 阶段研究漏斗

| Stage | 职责 | 主要输出 |
|-------|------|---------|
| Stage 1 | 市场扫描 | `MarketContextMemo` |
| Stage 2 | 假设扩展（6 个并行 Island） | `FactorResearchNote` (12-18 个候选) |
| Stage 3 | 三维前置过滤 | 通过的候选（默认 Top-5） |
| Stage 4 | 确定性执行（Docker + Qlib） | `BacktestReport` |
| Stage 5 | 结构化判断 | `CriticVerdict`, `CIOReport` |

### 6 个研究 Island

- `momentum` - 动量因子
- `northbound` - 北向资金
- `valuation` - 估值因子
- `volatility` - 波动率
- `volume` - 成交量
- `sentiment` - 市场情绪

每个 Island 有独立的 `AlphaResearcher`、失败历史和 softmax 调度。

### 关键目录结构

```
src/
├── schemas/          # 核心数据契约（当前接口真相）
├── agents/           # LLM 驱动的研究组件
│   ├── judgment.py   # Stage 5 canonical runtime
│   ├── researcher.py # Stage 2 假设生成
│   └── prefilter.py  # Stage 3 过滤链
├── execution/        # Stage 4 确定性执行
│   ├── coder.py      # 模板填充 + Qlib 执行
│   └── docker_runner.py
├── control_plane/    # 状态管理和编排
│   └── state_store.py
├── core/
│   ├── orchestrator.py  # LangGraph 主编排
│   └── run_baseline.py  # 基准测试
├── factor_pool/      # 因子池和 Island 调度
├── cli/              # 命令行接口
└── api/              # FastAPI 服务

tests/                # 测试套件
docs/
├── overview/         # 项目全貌和当前状态
├── design/           # 详细设计文档
├── plans/            # 执行计划和工程债
└── archive/          # 历史文档（不再指导实现）
```

## 常用命令

### 环境设置

```bash
# 创建环境
conda create -n pixiu python=3.11
conda activate pixiu
pip install -e .

# 配置凭证
cp .env.example .env
# 编辑 .env 设置 RESEARCHER_MODEL, RESEARCHER_API_KEY 等
```

### 数据准备

```bash
# 下载 A 股数据（沪深 300）
python -m src.data_pipeline.data_downloader
python -m src.data_pipeline.format_to_qlib
```

### 运行系统

```bash
# 运行基准测试（建立 benchmark）
python -m src.core.run_baseline

# 单 Island 调试模式
python -m src.core.orchestrator --mode single --island momentum

# 完整演化循环
python -m src.core.orchestrator --mode evolve --rounds 20
```

### CLI 工具

```bash
pixiu status           # 查看系统状态
pixiu factors --top 10 # 查看 Top 因子
pixiu approve          # 审批因子
```

### 测试

```bash
# 默认开发测试（smoke + unit）
pytest -q tests -m "smoke or unit"

# 本地集成测试
pytest -q tests -m "integration and not live and not e2e"

# Live 数据联通测试（需要外部服务）
pytest -q tests -m live

# 端到端测试（需要完整环境）
pytest -q tests -m e2e

# 运行特定测试文件
pytest tests/test_schemas.py -v
```

**测试分层**：
- `smoke` - 快速冒烟测试，无外部依赖（< 30 秒）
- `unit` - 单元测试，可用 mock
- `integration` - 本地集成测试
- `live` - 依赖外部服务（不阻塞 merge）
- `e2e` - 端到端测试（不阻塞 merge）

**Merge Gate**：只要求通过 `smoke + unit`。

## 关键设计决策

### 1. Coder 是确定性的（零 LLM 调用）

因子公式填入标准 Qlib 回测模板，通过 Docker 子进程执行。回测关键路径上没有 LLM。

### 2. 错误驱动的 RAG

失败原因存入 ChromaDB。下次 `AlphaResearcher` 调用时检索相似失败案例作为负样本。失败积累成知识。

### 3. 文档驱动的接口

所有 Agent 通过类型化的 Pydantic schemas 通信（`FactorResearchNote`, `BacktestReport`, `CriticVerdict` 等）。不传递 dict。

### 4. 人类保持在环内（最小化）

系统自主运行 Stage 1-4。人类收到 `CIOReport` 后选择：`approve`、`redirect:<island>` 或 `stop`。

## 当前实现状态

### 已实现
- ✅ Stage 4→5 最小闭环
- ✅ `state_store` 控制平面 MVP
- ✅ 核心 schemas 和接口契约
- ✅ 测试管线（smoke/unit/integration）
- ✅ CLI/API 最小实现

### 进行中
- 🔄 Stage 2 升级为 `Hypothesis Expansion Engine`
- 🔄 Richer contracts 迁移（新旧字段双轨期）
- 🔄 控制平面扩展

### 计划中
- ⏳ Web Dashboard
- ⏳ Live/E2E 测试稳定化
- ⏳ 多市场扩展（港股、美股、期货、加密货币）

## 开发规则

### 代码修改前
1. 先读 `docs/overview/spec-execution-audit.md` 确认模块状态
2. 阅读对应的 `docs/design/` 设计文档
3. 查看 `src/schemas/` 了解接口契约
4. 理解现有代码再建议修改

### 兼容性注意事项
- `src/agents/judgment.py` 是 Stage 5 的 canonical runtime
- `src/agents/critic.py`、`factor_pool_writer.py`、`cio_report_renderer.py` 是兼容层
- 修改核心逻辑时优先改 `judgment.py`，保持兼容层同步

### 测试要求
- 修改代码必须补充对应层级测试
- 触及 `execution/factor_pool/orchestrator` 至少跑一组 `integration`
- 不要把实验脚本放在 `tests/` 下

### 文档同步
- 修改架构时同步更新 `docs/design/` 对应文档
- 如果设计与实现分歧，先更新 `spec-execution-audit.md`

## 环境变量

当前 MVP 运行时读取的关键变量：

```bash
# LLM 配置
RESEARCHER_MODEL=gpt-4
RESEARCHER_BASE_URL=https://api.openai.com/v1
RESEARCHER_API_KEY=sk-...

OPENAI_MODEL=gpt-4
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-...

# 系统配置
MAX_ROUNDS=20
ACTIVE_ISLANDS=momentum,northbound,valuation,volatility,volume,sentiment
REPORT_EVERY_N_ROUNDS=5
MAX_CONCURRENT_BACKTESTS=3
PIXIU_STATE_STORE_PATH=./state_store

# 可选集成
TUSHARE_TOKEN=...           # Tushare Pro（基本面数据）
TAVILY_API_KEY=...          # Tavily（新闻检索）
FUNDAMENTAL_FIELDS_ENABLED=false
```

## 学术基础

Pixiu 的架构基于以下论文：

- **AlphaAgent** (arXiv:2502.16789) - 三维前置过滤设计
- **RD-Agent** (Microsoft, arXiv:2505.15155) - 文档驱动接口原则
- **QuantaAlpha** (arXiv:2602.07085) - 探索 Agent 设计
- **CogAlpha** (arXiv:2511.18850) - 多 Agent 质量层级
- **QuantAgent** (Huawei, arXiv:2402.03755) - 双循环 Island 演化

## 许可证

AGPL-3.0 - 个人使用、学术研究和开源项目免费。如作为网络服务部署（SaaS），必须开源修改。商业许可可联系获取。
