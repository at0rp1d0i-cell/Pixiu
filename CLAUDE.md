# CLAUDE.md

> Pixiu v2.0 — LLM-native Alpha Research OS for A-Shares

## 项目定义

Pixiu 是一个面向中国 A 股市场的 alpha research OS，通过 5 阶段 pipeline 持续生成、筛选、执行、淘汰并沉淀 alpha hypotheses。

核心产物不是投资建议，而是：可执行的 research objects、可回放的 evaluation artifacts、可沉淀的 failure constraints。

### 第一性定义

Pixiu = Alpha Research Infrastructure / Research Operating System

- 因子不是最终产品，是最小可执行假设单元（research object / compressed hypothesis）
- 投资建议是"消费 research 产物"的一种下游形式，不是 Pixiu 存在的唯一理由
- 系统最稀缺的能力：持续进化的 alpha hypothesis economy
  - 新假设不断生成，坏假设被快速淘汰
  - 失败经验变成约束，好假设被压缩成 reusable objects
  - regime knowledge 不断累积，系统越来越擅长"少犯旧错"

### 架构灵魂

- 上游极强探索（Stage 1-2）
- 中游严格收缩（Stage 3）
- 下游只输出可审计对象（Stage 4-5）
- **不要扩大 execution power，要扩大 hypothesis space**
- **不要把 Pixiu 定义成投顾团队，要把它定义成 alpha research infrastructure**

## 技术栈

- Python 3.12, uv (环境管理), LangChain / LangGraph, qlib, LightGBM
- FastAPI (API), Typer + Rich (CLI)
- akshare / baostock (数据), ChromaDB (向量), MLflow (实验跟踪)
- Docker (Stage 4 回测隔离执行)

## 环境管理

```bash
# 环境初始化（uv 管理全部依赖）
uv sync --dev

# 激活虚拟环境（如需手动）
source .venv/bin/activate

# 添加依赖
uv add <package>

# 添加开发依赖
uv add --group dev <package>

# 锁定依赖
uv lock
```

关键文件：`pyproject.toml`（依赖声明）、`uv.lock`（锁定版本）、`.python-version`（Python 版本）

## 5 阶段主链

| Stage | 职责 | 核心模块 | 输出 |
|-------|------|----------|------|
| 1 — Market Context | 宽扫描，建立市场上下文 | `src/agents/market_analyst.py` | `MarketContextMemo` |
| 2 — Hypothesis Expansion | 系统扩张研究假设空间（5 子空间） | `src/agents/researcher.py` | `FactorResearchNote` → `Hypothesis/StrategySpec` |
| 3 — Prefilter | 昂贵回测前做硬 gate | `src/agents/prefilter.py` | `FilterReport` |
| 4 — Execution | 确定性执行，可 replay | `src/execution/coder.py` | `BacktestReport` |
| 5 — Judgment | 结构化判断，沉淀约束 | `src/agents/judgment.py` | `CriticVerdict`, `CIOReport` |

### Stage 2 — Hypothesis Expansion Engine（五子空间）

Stage 2 的核心升级方向：把"智能性"从 execution layer 搬回 hypothesis layer。

#### 1. Factor Algebra Search
定义可组合的 algebra，做受约束组合搜索：
- price-volume / fundamental / event-derived primitives
- temporal transforms, cross-sectional operators
- regime switches
- 让 hypothesis space 系统化，而非"让模型口头想因子"

#### 2. Symbolic Factor Mutation
把"想法改进"变成显式 mutation operator：
- add/remove operator, swap temporal horizon
- change normalization, alter interaction term
- impose sparsity / monotonicity / stability prior

#### 3. Cross-Market Pattern Mining
不抄因子，抄逻辑骨架：
- 美股 / 港股 / 商品 / 利率 / 汇率的 pattern transfer
- 传导的是 market mechanism analogies（如"库存周期—上游定价—中游利润传导"）

#### 4. Economic Narrative Mining
A 股 alpha 大量藏在叙事层而非 price signal：
- 政策口径、产业链叙事、市场预期错位
- 公告语言风格、卖方一致预期与现实偏差
- 产出：candidate mechanism, latent driver hypothesis, event-to-factor mapping

#### 5. Regime Conditional Factors
因子不是"好"或"坏"，而是 regime-dependent：
- 生成 factor + applicable regime + invalid regime + switching rule hypothesis
- 直接改变 Stage 3/4 的评估方式

### 因子的广义定义

因子不只是"能不能赚钱"，更是：
- 它代表了什么市场机制假设
- 它在什么 regime 下有效 / 无效
- 它和哪些旧因子冗余 / 互补
- 它为什么失败，失败后留下什么约束
- 它能否作为更高阶 strategy component 的 building block

未来方向：factor families, conditional ensembles, factor graphs, mechanism bundles

## 关键路径

- Schema 真相：`src/schemas/`
- 主编排：`src/core/orchestrator/`（graph.py + nodes/ + _context.py）
- 控制平面：`src/control_plane/state_store.py`
- Factor 沉淀：`src/factor_pool/pool.py`
- Stage 5 canonical runtime：`src/agents/judgment.py`

## 文档体系

优先级从高到低：

1. `docs/overview/` — 项目全貌、当前状态
2. `docs/design/` — 有效设计展开层
3. `docs/plans/` — 执行计划和工程债
4. `docs/reference/` — 外部参考资料
5. `docs/research/` — 历史讨论
6. `docs/archive/` — 已过时文档，仅供追溯

当设计与代码不一致时，以 `docs/overview/spec-execution-audit.md` 的结论为准。

## 常用命令

```bash
# 环境同步
uv sync --dev

# 测试（默认入口）
uv run pytest -q tests -m "smoke or unit"

# 本地集成测试
uv run pytest -q tests -m integration

# baseline 运行
uv run python -m src.core.run_baseline

# 单岛调试
uv run python -m src.core.orchestrator --mode single --island momentum

# 演化循环
uv run python -m src.core.orchestrator --mode evolve --rounds 20

# CLI
uv run pixiu --help

# API 启动
uv run uvicorn src.api.server:app --reload
```

## 当前优先级

1. **Stage 2 升级**：将 Stage 2 从 note generation 升级为真正的 Hypothesis Expansion Engine（五子空间）
2. **Richer contracts**：收紧 `BacktestReport / CriticVerdict / FactorPoolRecord` 合约
3. **控制平面**：扩展到稳定的数据面（审计 trail、读模型）
4. **测试闭环**：补齐 live / e2e 测试
5. **产品层**：Dashboard 和数据源扩展

---

## AI Team 设计

### 核心原则

- **扩大 hypothesis space，不扩大 execution power**
- 设计讨论和 brainstorming 永远留在 coordinator，不外包
- 默认拓扑：`coordinator + 1-2 workers`，不搞大团队常驻
- 并行仅在写集不重叠时允许

### 角色定义

| 角色 | 身份 | 模型 | 职责边界 |
|------|------|------|----------|
| **Coordinator** | Claude (主对话) | Claude Opus | 持有架构真相、设计讨论、brainstorming、任务拆分、集成验证、最终裁决 |
| **codex** | Codex CLI worker | — | 边界明确的代码实现：单模块开发、重构、debug、单组测试编写 |
| **coworker** | Codex CLI reviewer | GPT-5.4 xhigh | 项目设计审阅、代码实现 review、spec 一致性审计、跨文件质量检查 |

### Coordinator 专属（不可外包）

- 架构决策和跨模块判断
- Schema / contract 设计变更
- Stage 间接口定义
- spec-execution-audit 更新
- 集成验证和最终验收
- 与用户的设计讨论和 brainstorming

### 任务派发格式

每次给 worker 的任务必须包含：

```
- Task：一句话目标
- Context：相关文件路径或代码片段
- Constraints：不能动什么、必须用什么
- Output：交付什么文件、什么格式
- Done When：验收标准（1-3 条）
```

### 任务路由表

| 任务类型 | 路由 | 说明 |
|----------|------|------|
| 单 Stage 模块实现 | → codex | 写集明确，单模块边界 |
| 单组测试补齐 | → codex | 给定 test file + 验收标准 |
| Bug fix（单文件） | → codex | 给定复现路径 |
| 重构（单模块） | → codex | 给定重构目标和约束 |
| 跨文件 spec 一致性审计 | → coworker | 读多文件，产出审计报告 |
| 设计文档审阅 | → coworker | 给定设计文档，检查完整性和一致性 |
| 代码实现 review | → coworker | 给定模块/diff，产出 review 意见 |
| 跨 Stage 质量检查 | → coworker | 检查接口对齐、contract 合规 |
| Schema 设计变更 | coordinator 自持 | 影响多 Stage 的核心决策 |
| 架构讨论 / brainstorming | coordinator 自持 | 不可外包 |
| 跨模块集成 | coordinator 自持 | 涉及多写集 |

### 时间盒

| 角色 | 时限 | 超时处理 |
|------|------|----------|
| codex worker | 20-40 min | coordinator 接管或拆小 |
| coworker reviewer | 10-20 min | 缩小审阅范围 |
| explorer（短审计） | 5-10 min | 直接收结论 |
| reviewer（diff 审查） | 5-10 min | 直接收结论 |

### Worker 输出要求

每次 worker 完成任务必须返回：

1. **改了什么** — 文件列表 + 变更摘要
2. **为什么** — 决策理由
3. **验证结果** — 跑了什么命令、什么结果
4. **未完成项** — 如有，明确列出

没有验证结果，不能宣称任务完成。

### 卡死处理

- heartbeat 超过 5 分钟未更新 → 判定异常
- 进程存活 = hung → kill + restart
- 进程消失 = crashed → 查日志决定是否重试
- Worker 超时无有效产出 → coordinator 直接接管或重切任务

### 典型协作模式

**模式 A：Coordinator 独立完成**
适用于：设计讨论、schema 变更、小幅修改、集成工作

**模式 B：Coordinator + 1 codex**
适用于：单 Stage 模块实现 + coordinator 做集成验证

**模式 C：Coordinator + codex + coworker 并行**
适用于：codex 实现代码 + coworker 同时做设计/代码 review，coordinator 最终合并

**模式 D：Coordinator + 2 codex 并行**
适用于：两个写集不重叠的实现任务（如 Stage 3 测试 + Stage 5 测试）

**模式 E：Coordinator + coworker 审阅**
适用于：阶段性 review — coworker 审阅设计或实现，coordinator 据此做决策

## 开发规范

- 语言：中文交流，代码和文件名用英文
- 环境管理：统一使用 uv，不使用 pip / conda / poetry
- Schema 变更必须先更新 `src/schemas/`，再改运行时
- 新增模块必须有对应的 smoke/unit 测试
- PR 前必须通过 `uv run pytest -q tests -m "smoke or unit"`
- 不要绕过 prefilter 硬 gate（Stage 3 存在的意义）
- 不要在执行层加"聪明"逻辑，智能属于 Stage 2
