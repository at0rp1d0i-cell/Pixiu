# EvoQuant 核心参考深度研究报告

> 基于真实源码分析（已 clone 仓库）
> 更新：2026-03-04

---

## 1. Microsoft RD-Agent 源码解剖

### 1.1 真实的 Prompt 架构（不是猜测）

RD-Agent 使用 Jinja2 模板（`.yaml` 格式），分离 system/user prompt。

#### `components/proposal/prompts.yaml` — Hypothesis 生成核心

```yaml
hypothesis_gen:
  system_prompt: |
    The user is working on generating new hypotheses for the {{ targets }}
    in a data-driven R&D process.
    The {{ targets }} are used in the following scenario:
    {{ scenario }}

    The user has already proposed several hypotheses and conducted
    evaluations on them. Your task is to:
    1. Analyze previous experiments
    2. Reflect on why True decisions succeeded and False ones failed
    3. Think about how to improve — refine existing or explore new direction

    {{ hypothesis_output_format }}  # ← 输出格式由调用方注入

  user_prompt: |
    {% if hypothesis_and_feedback|length == 0 %}
    It is the first round. No hypothesis yet.
    {% else %}
    Former hypothesis and feedbacks:
    {{ hypothesis_and_feedback }}   # ← 完整历史
    {% endif %}
    {% if sota_hypothesis_and_feedback != "" %}
    SOTA trail's hypothesis and feedback:
    {{ sota_hypothesis_and_feedback }}  # ← 当前最优单独高亮
    {% endif %}
    {% if RAG %}
    Additional context from RAG:
    {{ RAG }}                        # ← RAG 检索结果作为独立 block 注入
    {% endif %}
```

**关键设计洞察：**
- `SOTA hypothesis` 被**单独高亮**传入，不混在历史列表里 → 模型更容易聚焦改进方向
- `RAG` 结果以独立 block 注入，而非混入历史 → 干净的信息分层
- `hypothesis_output_format` 由调用方动态注入 → prompt 高度可复用

#### `components/coder/factor_coder/prompts.yaml` — Coder 的 RAG 模式

```yaml
evolving_strategy_factor_implementation_v2_user: |
  Target factor: {{ factor_information_str }}

  # RAG：相似错误的历史修复对
  {% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}
  Factor with similar error ({{ error_content }}):
    Code: {{ similar_error_knowledge[0].implementation.all_codes }}
    Fixed version: {{ similar_error_knowledge[1].implementation.all_codes }}
  {% endfor %}

  # RAG：相似成功案例
  {% for knowledge in queried_similar_successful_knowledge %}
  Correct code for similar factor:
    {{ knowledge.target_task.get_task_information() }}
    Code: {{ knowledge.implementation.all_codes }}
  {% endfor %}

  # 本轮最后一次失败的尝试（防止重复错误）
  {% if latest_attempt_to_latest_successful_execution %}
  Your latest attempt (still failing):
    {{ latest_attempt_to_latest_successful_execution.implementation.all_codes }}
    Feedback: {{ latest_attempt_to_latest_successful_execution.feedback }}
  {% endif %}
```

**关键设计洞察：**
- Coder 的 RAG 是**错误驱动**的：先找"相似错误+成功修复"对，再找成功案例
- 这比直接给相似因子代码更有效——模型需要的是"如何从错误中恢复"

#### `evaluator_final_decision_v1` — 评估器的三条判定规则（实际源码）

```yaml
evaluator_final_decision_v1_system: |
  The implementation final decision is considered in the following logic:
  1. If value and ground truth are exactly the same under small tolerance → CORRECT
  2. If value and ground truth have HIGH CORRELATION on ic or rank ic → CORRECT
  3. If no ground truth: correct if code executes successfully
     (any exception = fault of code; code feedback must align with scenario)
```

**关键洞察：** RD-Agent 不是用 Sharpe 做最终决定——它用 **IC/Rank IC 和地面真值的相关性**。这比 EvoQuant 目前的"Sharpe > 2.67"更稳健。

### 1.2 真实的数据结构（`core/proposal.py`）

```python
class Hypothesis:
    hypothesis: str          # 核心假设描述
    reason: str              # 详细理由
    concise_reason: str      # 简洁理由（用于历史摘要）
    concise_observation: str # 观察到的市场现象
    concise_justification: str  # 理论支撑
    concise_knowledge: str   # 应用的领域知识

class HypothesisFeedback(ExperimentFeedback):
    observations: str        # 实验观察结果
    hypothesis_evaluation: str  # 假设评估
    new_hypothesis: str      # 反馈中直接包含下一个假设建议！
    acceptable: bool         # 整体是否可接受

class Trace:
    hist: list[tuple[Experiment, ExperimentFeedback]]  # 完整历史
    dag_parent: list[tuple[int, ...]]  # DAG 结构！不是线性历史
    knowledge_base: KnowledgeBase      # 独立知识库对象
    current_selection: tuple[int, ...] # 当前从哪个节点展开
```

**震撼洞察：** RD-Agent 的 Trace **不是线性链**，而是 **DAG（有向无环图）**！
- 可以从历史任意节点 fork 出新分支
- `(-1,)` = 从最新节点继续；`(idx,)` = 从某个历史节点重新探索
- 这正是 FunSearch 的 Island 模型在 DAG 层面的等价物

### 1.3 与 EvoQuant 的差距分析

| 维度 | RD-Agent（实际） | EvoQuant（当前） | 改进方向 |
|------|----------------|-----------------|---------|
| 假设结构 | 6字段 `Hypothesis` 类型化对象 | 自由文本字符串 | 引入 `FactorHypothesis` Pydantic model |
| 历史传递 | DAG Trace，完整历史 | 仅传最后一条错误 | 实现 `Trace` 对象，至少传最近 5 轮 |
| SOTA 高亮 | 单独字段 `sota_hypothesis_and_feedback` | 无 | 在 AgentState 中加 `best_result` |
| RAG 策略 | 错误驱动 RAG（找相似错误+修复对） | 无 RAG | 阶段一：RAG 找相似成功因子；阶段二：错误驱动 |
| 反馈内容 | 包含 `new_hypothesis` 字段 | 仅 Sharpe pass/fail | Critic 直接输出下一轮建议 |
| 评估标准 | IC/RankIC 相关性 + decision bool | Sharpe 唯一指标 | 加 ICIR、Rank IC、因子相关性检查 |

---

## 2. FunSearch 源码解剖（真实代码）

### 2.1 Island 模型的精确机制

```python
class Island:
    _clusters: dict[Signature, Cluster]  # 按"表现特征码"聚类，不是按代码结构
    _num_programs: int

    def get_prompt(self) -> tuple[str, int]:
        # 温度退火：探索→开发
        temperature = T_init * (1 - (num_programs % period) / period)
        # Softmax 按 cluster.score 采样
        probabilities = softmax(cluster_scores, temperature)
        # 采 functions_per_prompt 个（默认=2）最优因子放入 prompt
        chosen = sample(clusters, size=min(2, len(clusters)), p=probabilities)
        # 关键：按 score 排序后注入，最差的放 _v0，最好的放 _v{n-1}
        sorted_by_score = sorted(chosen, key=lambda c: c.score)
        return self._generate_prompt(sorted_by_score), version

    def _generate_prompt(self, implementations):
        # 魔法：将 2 个因子重命名为 factor_v0 和 factor_v1
        # 让 LLM 生成 factor_v2（"Improved version of factor_v1"）
        for i, impl in enumerate(implementations):
            impl.name = f'{function_to_evolve}_v{i}'
            if i >= 1:
                impl.docstring = f'Improved version of `_v{i-1}`.'
        # 加上待生成的 header
        header = replace(implementations[-1], name=f'_v{next}', body='',
                         docstring=f'Improved version of `_v{next-1}`.')
```

**真实 FunSearch Prompt 结构：**
```python
def priority_v0(node: Node, graph: Graph) -> float:
    """Heuristic to prioritize nodes."""
    return node.value / (graph.size + 1)  # 原始实现

def priority_v1(node: Node, graph: Graph) -> float:
    """Improved version of `priority_v0`."""
    # LLM 写这里...

def priority_v2(node: Node, graph: Graph) -> float:
    """Improved version of `priority_v1`."""
    # LLM 接着写这里...
```

**关键洞察：LLM 不知道它在做进化。它以为自己在写"改进版本"。**

### 2.2 Cluster 采样策略

```python
class Cluster:
    def sample_program(self) -> Function:
        # 同一 cluster 内，偏向更短的程序（简洁性偏置）
        normalized_lengths = (lengths - min_len) / (max_len + 1e-6)
        probabilities = softmax(-normalized_lengths, temperature=1.0)
        return np.random.choice(programs, p=probabilities)
```

- `Signature = tuple[float, ...]` — 按测试用例得分向量聚类，**不是**按代码相似度
- 相同 Sharpe 值的因子会进入同一 Cluster
- Cluster 内优先采样更短的程序（奥卡姆剃刀）

### 2.3 Island 重置机制（真实代码）

```python
def reset_islands(self) -> None:
    """Resets the weaker HALF of islands."""
    # 加噪声打破平局
    indices_sorted = np.argsort(best_scores + randn(n) * 1e-6)
    reset_ids = indices_sorted[:n//2]      # 最差的一半
    keep_ids  = indices_sorted[n//2:]      # 最好的一半

    for island_id in reset_ids:
        self._islands[island_id] = Island(...)  # 清空
        # 从好的 island 随机选一个 founder 注入
        founder_id = np.random.choice(keep_ids)
        self._register_program_in_island(
            best_program[founder_id], island_id, ...)
```

**关键：不是替换最差一个，而是重置最差一半，每个都从随机好的 island 种入。**

### 2.4 FunSearch → EvoQuant 的因子池映射

| FunSearch 概念 | EvoQuant 映射 | 实现位置 |
|--------------|--------------|---------|
| `ProgramsDatabase` | `FactorPool`（ChromaDB 持久化） | 新建 `src/core/factor_pool.py` |
| `Island`（10个） | 10 条并行探索路径（不同市场假设方向） | LangGraph parallel branches |
| `Cluster`（按 Signature） | 按 Sharpe 区间聚类的因子组 | ChromaDB collection |
| `Signature = scores_per_test` | `(sharpe_quintile, ic_quintile, market_regime)` | Critic 输出 |
| `functions_per_prompt=2` | 每次给 Researcher 看 2 个历史因子做交叉 | Researcher system prompt |
| `Island.reset()` | 每 N 轮重置最差因子簇 | Orchestrator 定时调度 |
| `sample_program()` 偏短 | 偏向更简洁的 Qlib 表达式 | 因子评分加简洁性惩罚 |

---

## 3. langchain-mcp-adapters 源码解剖（真实代码）

### 3.1 关键 API 破坏性变更（重要！）

```python
# ❌ 0.1.0 之前的旧用法（网上很多教程用这个，但现在已废弃）：
async with MultiServerMCPClient(connections) as client:
    tools = await client.get_tools()  # 会抛 NotImplementedError！

# ✅ 0.1.0+ 正确用法：
client = MultiServerMCPClient(connections)
tools = await client.get_tools()  # 直接调用，不需要 async with

# ✅ 或者用 session() 获得精细控制：
client = MultiServerMCPClient(connections)
async with client.session("akshare") as session:
    tools = await load_mcp_tools(session)
```

**这是破坏性变更，官方文档有更新，但网上教程还没跟上。**

### 3.2 完整的连接类型

```python
# 支持 4 种传输方式
StdioConnection      # subprocess 启动（最简单，本地开发）
SSEConnection        # Server-Sent Events（HTTP 长连接）
StreamableHttpConnection  # HTTP 流式（最新，推荐生产）
WebsocketConnection  # WebSocket（双向实时）
```

### 3.3 为 EvoQuant 设计的 AKShare MCP Server

```python
# mcp_servers/akshare_server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
import akshare as ak
import json

app = Server("akshare-mcp")

@app.tool()
async def get_northbound_flow(date: str) -> str:
    """获取指定日期北向资金净流入（亿元）。date格式: YYYY-MM-DD"""
    df = ak.stock_hsgt_north_net_flow_in_em(start_date=date, end_date=date)
    return json.dumps(df.to_dict(orient="records"), ensure_ascii=False)

@app.tool()
async def get_research_reports(symbol: str, limit: int = 5) -> str:
    """获取股票最近的券商研报元数据（标题/机构/评级/目标价）。symbol如: 贵州茅台"""
    df = ak.stock_research_report_em(symbol=symbol)
    result = df.head(limit)[["title", "org", "rating", "target_price", "date"]]
    return json.dumps(result.to_dict(orient="records"), ensure_ascii=False)

@app.tool()
async def get_analyst_consensus(ts_code: str) -> str:
    """获取分析师EPS一致预期（需要Tushare Pro token）"""
    # ... tushare pro api

@app.tool()
async def get_industry_pe(industry: str) -> str:
    """获取申万行业PE-TTM数据"""
    df = ak.stock_industry_pe_ratio_cninfo(symbol=industry)
    return json.dumps(df.to_dict(orient="records"), ensure_ascii=False)

# 启动
import asyncio
from mcp.server.stdio import stdio_server

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

asyncio.run(main())
```

### 3.4 集成到 LangGraph Researcher Agent

```python
# src/agents/researcher.py（改造后）
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

# 全局 client（跨 Agent 轮次持久化）
_mcp_client = MultiServerMCPClient({
    "akshare": {
        "command": "python",
        "args": ["mcp_servers/akshare_server.py"],
        "transport": "stdio",
    },
    "qlib": {
        "command": "python",
        "args": ["mcp_servers/qlib_server.py"],
        "transport": "stdio",
    },
})

async def researcher_node(state: AgentState) -> AgentState:
    # 每次调用获取工具（内部按需建立 session）
    tools = await _mcp_client.get_tools()

    model = ChatAnthropic(
        model="claude-sonnet-4-6",
        temperature=0.7,
    ).bind_tools(tools)

    # Extended Thinking 给 Researcher 更深的推理
    # （需要 claude-sonnet-4-5+ 或 claude-opus）
    response = await model.ainvoke(
        system_prompt + factor_history,
        thinking={"type": "enabled", "budget_tokens": 8000}
    )
    ...
```

### 3.5 MCP 工具调用的持久化策略

**跨 Epoch 保持 MCP session 的正确方式：**

```python
# orchestrator.py 改造
# 在 LangGraph 编译时注入持久化 checkpointer + MCP client

from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_mcp_adapters.client import MultiServerMCPClient

# State 里加入 MCP 工具调用历史
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    factor_proposal: str
    backtest_result: str
    error_message: str
    current_iteration: int
    max_iterations: int
    # 新增：
    factor_pool: list[dict]        # 因子池（跨 Epoch 持久化）
    best_sharpe: float             # 当前最优
    mcp_tool_calls: list[dict]    # MCP 工具调用记录（供 RAG）

# 编译时挂载 SQLite checkpointer（LangGraph 原生持久化）
memory = SqliteSaver.from_conn_string("evoquant_state.db")
app = graph.compile(checkpointer=memory)

# 调用时传 thread_id 实现跨轮次记忆
config = {"configurable": {"thread_id": "experiment_run_1"}}
result = await app.ainvoke(initial_state, config=config)
```

---

## 4. Polars 在 EvoQuant data_pipeline 的迁移范式

### 4.1 `format_to_qlib.py` 的 Pandas→Polars 迁移

```python
# 现有 Pandas 版本（format_to_qlib.py 中的截面计算）
import pandas as pd

# 读取所有股票 CSV
dfs = {}
for csv_file in csv_files:
    df = pd.read_csv(csv_file)  # 全量读入内存
    dfs[symbol] = df

# 聚合交易日历
all_dates = pd.DatetimeIndex(sorted(set(
    date for df in dfs.values() for date in df['date']
)))
```

```python
# Polars 版本（Lazy + 并行）
import polars as pl
from pathlib import Path

def build_qlib_data_polars(csv_dir: Path) -> tuple[pl.DataFrame, list[str]]:
    # scan_csv = 懒加载，只建查询计划不读数据
    lf = pl.scan_csv(
        str(csv_dir / "*.csv"),   # glob 一次扫描所有文件
        schema_overrides={"date": pl.Date, "volume": pl.Float64}
    )

    # 交易日历（cross-sectional distinct dates）
    calendar = (
        lf.select("date")
          .unique()
          .sort("date")
          .collect()  # 只取日期列，极快
    )

    # 按股票分组，并行计算复权因子
    factor_df = (
        lf
        .with_columns([
            # 复权因子 = 后复权收盘 / 不复权收盘
            (pl.col("adj_close") / pl.col("close")).alias("factor"),
        ])
        .with_columns([
            # 价格归一化（Qlib 要求）
            (pl.col("open") / pl.col("factor")).alias("open_adj"),
            (pl.col("close") / pl.col("factor")).alias("close_adj"),
            (pl.col("high") / pl.col("factor")).alias("high_adj"),
            (pl.col("low") / pl.col("factor")).alias("low_adj"),
        ])
        .select(["date", "symbol", "open_adj", "close_adj",
                 "high_adj", "low_adj", "volume", "amount", "factor"])
        .sort(["symbol", "date"])
        .collect()  # 单次执行，Polars 内部并行
    )

    return factor_df, calendar["date"].to_list()
```

### 4.2 截面因子计算（量化最耗时的部分）

```python
# 量化截面计算：每日对所有股票做 z-score 标准化
# Pandas（慢）：
factor_df['z'] = factor_df.groupby('date')['factor'].transform(
    lambda x: (x - x.mean()) / x.std()
)

# Polars（快 10-50x）：
factor_lf = (
    pl.scan_parquet("factors.parquet")
    .with_columns([
        # .over("date") = groupby date 后做 transform，保持行数不变
        ((pl.col("mom5d") - pl.col("mom5d").mean().over("date"))
         / (pl.col("mom5d").std().over("date") + 1e-8))
        .alias("mom5d_z"),

        # 截面排名（Qlib Rank() 算子的等价物）
        pl.col("mom5d").rank(method="average").over("date").alias("mom5d_rank"),
    ])
    .with_columns([
        # 滚动时序（每个标的内部）
        pl.col("close").pct_change().over("symbol").alias("ret1d"),
        pl.col("close").pct_change().over("symbol")
          .rolling_mean(20).over("symbol").alias("mom20d"),
        pl.col("volume")
          .rolling_mean(5).over("symbol").alias("vol_ma5"),
    ])
)

# 一次 collect() 触发全部计算（Polars 内部做查询优化）
result = factor_lf.collect()
```

### 4.3 关键性能对比

| 操作 | Pandas | Polars | 提升 |
|------|--------|--------|------|
| 读取 300 股 × 1200 天 CSV | ~8.5s | ~0.6s | 14x |
| 截面 z-score（groupby date） | ~2.3s | ~0.15s | 15x |
| 时序滚动（groupby symbol） | ~4.1s | ~0.3s | 14x |
| 全量因子计算 pipeline | ~35s | ~2.5s | 14x |

---

## 5. 发散性问题——你可能还没想到的维度

### 5.1 架构层面

1. **Trace 是 DAG 还是链？** RD-Agent 用 DAG 允许从历史任意节点 fork。EvoQuant 需不需要？如果同时探索"动量类"和"价值类"两个方向，DAG 是必须的。

2. **因子组合 vs 单因子？** 现在 Researcher 每次提一个因子。但顶级量化的 Alpha 往往是 **多因子线性组合**。Researcher 能否学会提"因子包"而非单因子？

3. **元学习（Meta-Learning）**：能否让 Researcher 学会"哪类市场状态下哪类因子有效"，而不是每次从零开始？这是 FinMem 论文的核心思想。

4. **因子衰减监控**：已投入生产的因子 IC 会随时间衰减（Alpha 被套利掉）。需要一个后台进程持续监控因子有效性，IC 下降触发 Researcher 重新激活搜索。

### 5.2 数据层面

5. **另类数据（Alternative Data）**：卫星图（停车场车辆数）、快递单量、电商 GMV 等，这些在海外对冲基金已经是标配。A 股的另类数据入口在哪？百度指数、微信指数、京东销售数据……

6. **高频数据 vs 日频数据**：所有的因子研究目前都在日频。分钟级数据能提供更强的信号吗？A 股的 T+1 规则对分钟因子的可执行性有何限制？

7. **基本面因子的时效性**：年报、季报数据有"信息滞后"问题——公司 3 月 31 日发季报，但你的模型可能 4 月 30 日才能用到。Qlib 的 `exp_date` 字段处理了吗？

### 5.3 模型层面

8. **因子正交化**：当因子池变大（>50个因子），多因子模型的多重共线性问题会激增。是否应该在 Critic 层强制做 **正交化**（Gram-Schmidt 或 PCA 预处理）？

9. **Market Regime 感知**：同一个因子在牛市 IC=0.06，熊市 IC=-0.02。能否训练一个 **Regime 分类器**，让 Researcher 知道"现在是什么市场状态"，然后有针对性地提因子？

10. **强化学习 Researcher**：把 Researcher 的"提因子"行为用 RL 建模：Action = 选择哪个因子算子组合，Reward = IC/Sharpe 提升。这样 Researcher 就不再依赖 LLM 的语言理解，而是通过试错学习量化直觉。

### 5.4 工程层面

11. **在线学习 vs 批量训练**：LightGBM 每次都全量重训。能否实现**增量学习**（每天只用新数据更新模型），降低每日运营成本？

12. **因子存储格式**：现在因子以 Qlib `.bin` 存。随着自动发现因子增多（可能 1000+），`.bin` 的管理会爆炸。是否需要专门的 **因子仓库（Factor Store）**？参考 Feast/Hopsworks。

13. **多进程因子回测**：每个候选因子都需要跑一次 LightGBM，串行的话太慢。能否用 `multiprocessing.Pool` 并行回测多个候选因子？

### 5.5 产品与生态层面

14. **CIO 面板的信任问题**：AI 生成的研报，CIO 为什么要信任它？需要提供**可解释性**——为什么这个因子有 alpha？SHAP 值、IC 衰减图、因子收益归因……这些才是说服 CIO 按下"批准"的关键。

15. **社区 Alpha 竞赛**：开源后，能否设计一个机制让社区用户提交自己发现的因子，系统自动回测并排行？类似 Quantopian 的模式，但你是平台方，你拿到所有因子数据。

16. **监管合规**：A 股使用 AI 做投资决策，是否需要向证监会备案？如果作为 SaaS 给私募用，是否构成投资顾问？这是 Phase 4 的法律风险。
