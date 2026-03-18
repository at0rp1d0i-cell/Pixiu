# Pixiu v2 Orchestrator 规格
Purpose: Describe the main graph, node responsibilities, and orchestration/control flow.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`../overview/03_architecture-overview.md`、`11_interface-contracts.md`
> 文件位置：`src/core/orchestrator/`（`graph.py + nodes/ + _entrypoints.py`）

---

## 1. 职责

Orchestrator 是系统的中枢，负责：
- 维护 LangGraph `StateGraph`，定义节点与边
- 调用 `IslandScheduler` 选择本轮研究方向
- 驱动五阶段漏斗顺序执行
- 在 Stage 4 以 `Coder` 为主路径，并在需要时协调 `ExplorationAgent` 的条件分支
- 触发 `interrupt()` 等待 CIO 审批
- 管理错误恢复与重试逻辑

---

## 2. LangGraph 图结构

### 节点定义

```python
# 节点名称常量
NODE_MARKET_CONTEXT    = "market_context"     # Stage 1
NODE_HYPOTHESIS_GEN    = "hypothesis_gen"     # Stage 2
NODE_SYNTHESIS         = "synthesis"          # Stage 2b
NODE_PREFILTER         = "prefilter"          # Stage 3
NODE_EXPLORATION       = "exploration"        # Stage 4a（条件执行）
NODE_NOTE_REFINEMENT   = "note_refinement"    # Stage 4a→2 反馈
NODE_CODER             = "coder"              # Stage 4b
NODE_JUDGMENT          = "judgment"           # Stage 5
NODE_PORTFOLIO         = "portfolio"          # Stage 5b
NODE_REPORT            = "report"             # Stage 5c → interrupt()
NODE_HUMAN_GATE        = "human_gate"         # interrupt() 等待点
NODE_LOOP_CONTROL      = "loop_control"       # 决定继续/结束/切换 Island
```

### 图的边与条件路由

```
START
  → market_context
  → hypothesis_gen（并行 N 个 Island）
  → synthesis
  → prefilter

prefilter
  → [如果 approved_notes 为空] → loop_control（本轮放弃，切下一轮）
  → [否则] → exploration（如果有 exploration_questions）
           → coder（如果无 exploration_questions）

exploration
  → note_refinement（将 ExplorationResult 反馈给对应 ResearchNote）
  → coder

coder
  → judgment

judgment
  → portfolio（如果有新通过因子）
  → loop_control（如果无新因子）

portfolio
  → report

report
  → human_gate（interrupt()）

human_gate
  [human_decision = "approve"]   → loop_control
  [human_decision = "redirect:X"] → hypothesis_gen（切换 Island 到 X）
  [human_decision = "stop"]      → END

loop_control
  [轮次未满 AND 无 stop 信号] → market_context（下一轮）
  [轮次已满 OR stop 信号]    → END
```

### 完整图构建代码框架

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.schemas.state import AgentState

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node(NODE_MARKET_CONTEXT, market_context_node)
    graph.add_node(NODE_HYPOTHESIS_GEN, hypothesis_gen_node)
    graph.add_node(NODE_SYNTHESIS, synthesis_node)
    graph.add_node(NODE_PREFILTER, prefilter_node)
    graph.add_node(NODE_EXPLORATION, exploration_node)
    graph.add_node(NODE_NOTE_REFINEMENT, note_refinement_node)
    graph.add_node(NODE_CODER, coder_node)
    graph.add_node(NODE_JUDGMENT, judgment_node)
    graph.add_node(NODE_PORTFOLIO, portfolio_node)
    graph.add_node(NODE_REPORT, report_node)
    graph.add_node(NODE_HUMAN_GATE, human_gate_node)
    graph.add_node(NODE_LOOP_CONTROL, loop_control_node)

    # 边定义
    graph.add_edge(START, NODE_MARKET_CONTEXT)
    graph.add_edge(NODE_MARKET_CONTEXT, NODE_HYPOTHESIS_GEN)
    graph.add_edge(NODE_HYPOTHESIS_GEN, NODE_SYNTHESIS)
    graph.add_edge(NODE_SYNTHESIS, NODE_PREFILTER)
    graph.add_conditional_edges(NODE_PREFILTER, route_after_prefilter)
    graph.add_edge(NODE_EXPLORATION, NODE_NOTE_REFINEMENT)
    graph.add_edge(NODE_NOTE_REFINEMENT, NODE_CODER)
    graph.add_edge(NODE_CODER, NODE_JUDGMENT)
    graph.add_conditional_edges(NODE_JUDGMENT, route_after_judgment)
    graph.add_edge(NODE_PORTFOLIO, NODE_REPORT)
    graph.add_conditional_edges(NODE_REPORT, route_after_report)
    graph.add_conditional_edges(NODE_HUMAN_GATE, route_after_human)
    graph.add_conditional_edges(NODE_LOOP_CONTROL, route_loop)

    return graph.compile(
        checkpointer=MemorySaver(),
        interrupt_before=[NODE_HUMAN_GATE],  # LangGraph interrupt
    )
```

---

## 3. 各节点实现规范

### `market_context_node`

```python
async def market_context_node(state: AgentState) -> AgentState:
    """
    调用 MarketAnalyst 和 LiteratureMiner，生成本轮 MarketContextMemo。
    仅在每轮开始时执行一次（不在内循环中）。
    """
    from src.agents.market_analyst import MarketAnalyst
    from src.agents.literature_miner import LiteratureMiner

    analyst = MarketAnalyst()
    miner = LiteratureMiner()

    # 并行执行
    market_data, historical_insights = await asyncio.gather(
        analyst.analyze(),
        miner.retrieve_insights(active_islands=ACTIVE_ISLANDS)
    )

    memo = MarketContextMemo(
        date=today_str(),
        northbound=market_data.northbound,
        macro_signals=market_data.macro_signals,
        hot_themes=market_data.hot_themes,
        historical_insights=historical_insights,
        suggested_islands=market_data.suggested_islands,
        market_regime=market_data.market_regime,
        raw_summary=market_data.raw_summary,
    )

    return {**state.dict(), "market_context": memo}
```

### `hypothesis_gen_node`

```python
async def hypothesis_gen_node(state: AgentState) -> AgentState:
    """
    为每个活跃 Island 并行启动一个 AlphaResearcher。
    使用 asyncio.gather 实现真正并行。
    """
    from src.agents.alpha_researcher import AlphaResearcher

    active_islands = scheduler.get_active_islands()
    tasks = [
        AlphaResearcher(island=island).generate(
            context=state.market_context,
            iteration=state.iteration,
        )
        for island in active_islands
    ]

    notes: List[FactorResearchNote] = await asyncio.gather(*tasks)
    return {**state.dict(), "research_notes": notes}
```

### `prefilter_node`

```python
async def prefilter_node(state: AgentState) -> AgentState:
    """
    三维过滤：Validator → NoveltyFilter → AlignmentChecker
    返回 approved_notes（Top K），更新 filtered_count。
    详细规格见 `22_stage-3-prefilter.md`。
    """
    ...
```

### `exploration_node`

```python
async def exploration_node(state: AgentState) -> AgentState:
    """
    仅对带有 exploration_questions 的 Note 调用 ExplorationAgent。
    这是 Stage 4 的条件分支，不是默认主路径。
    详细规格见 `23_stage-4-execution.md`。
    """
    ...
```

### `note_refinement_node`

```python
async def note_refinement_node(state: AgentState) -> AgentState:
    """
    将 ExplorationResult 反馈给 AlphaResearcher，
    让 Researcher 按需更新 final_formula。
    更新 approved_notes 中对应 Note 的 final_formula 和 status。
    """
    ...
```

### `coder_node`

```python
async def coder_node(state: AgentState) -> AgentState:
    """
    对每个 approved_note（status="ready_for_backtest"），
    调用 Coder 执行 Qlib 回测。
    串行执行（Docker 资源限制）或限并发（max_concurrent=2）。
    详细规格见 `23_stage-4-execution.md`。
    """
    ...
```

### `judgment_node`

```python
async def judgment_node(state: AgentState) -> AgentState:
    """
    对每个 BacktestReport 依次执行：
    1. Critic（阈值判断 + 失败归因）
    2. RiskAuditor（过拟合 + 相关性）
    3. FactorPool 写入
    详细规格见 `24_stage-5-judgment.md`。
    """
    ...
```

### `human_gate_node`

```python
def human_gate_node(state: AgentState) -> AgentState:
    """
    此节点本身不执行任何逻辑。
    LangGraph 在 interrupt_before=[NODE_HUMAN_GATE] 配置下，
    会在进入此节点前暂停，等待外部 .update_state() 注入 human_decision。

    外部（CLI）调用方式：
        graph.update_state(
            config,
            {"human_decision": "approve"},
            as_node=NODE_HUMAN_GATE
        )
    """
    return state  # pass-through，路由在 route_after_human 中处理
```

---

## 4. 条件路由函数

```python
def route_after_prefilter(state: AgentState) -> str:
    if not state.approved_notes:
        return NODE_LOOP_CONTROL
    has_exploration = any(
        note.exploration_questions
        for note in state.approved_notes
        if note.final_formula is None
    )
    return NODE_EXPLORATION if has_exploration else NODE_CODER

def route_after_judgment(state: AgentState) -> str:
    new_passes = [v for v in state.critic_verdicts if v.overall_passed]
    if new_passes:
        return NODE_PORTFOLIO
    return NODE_LOOP_CONTROL

def route_after_report(state: AgentState) -> str:
    return NODE_HUMAN_GATE  # 有报告则必须等待人类

def route_after_human(state: AgentState) -> str:
    decision = state.human_decision or "approve"
    if decision == "stop":
        return END
    if decision.startswith("redirect:"):
        return NODE_HYPOTHESIS_GEN  # 切换 Island 后重新生成假设
    return NODE_LOOP_CONTROL  # "approve"

def route_loop(state: AgentState) -> str:
    if state.current_round >= MAX_ROUNDS:
        return END
    return NODE_MARKET_CONTEXT
```

---

## 5. Island Scheduler 集成

```python
# IslandScheduler 在 Orchestrator 初始化时创建，全程复用
scheduler = IslandScheduler(
    islands=ACTIVE_ISLANDS,
    t_init=1.0,
    t_min=0.3,
    decay_every_n_rounds=10,
    decay_factor=0.85,
    reset_threshold_sharpe=1.5,
    reset_min_attempts=3,
)

# 在 loop_control_node 中更新调度器状态
def loop_control_node(state: AgentState) -> AgentState:
    # 更新本轮结果到 Scheduler
    for verdict in state.critic_verdicts:
        if verdict.overall_passed:
            report = next(r for r in state.backtest_reports
                         if r.factor_id == verdict.factor_id)
            scheduler.update(
                island=report.island,
                sharpe=report.metrics.sharpe
            )

    # 温度退火
    scheduler.maybe_anneal(state.current_round)

    # 重置表现差的 Island
    scheduler.maybe_reset()

    # 清空本轮状态，准备下一轮
    return AgentState(
        current_round=state.current_round + 1,
        current_island=scheduler.sample(),
        market_context=state.market_context,  # 当天只生成一次
    )
```

---

## 6. 错误处理策略

| 错误类型 | 处理方式 |
|---|---|
| Stage 1 MCP 调用失败 | 使用空 MarketContextMemo 继续（降级运行） |
| Stage 2 LLM 超时 | 重试最多 2 次，超时后跳过该 Island 本轮 |
| Stage 3 过滤后无通过 | 直接到 loop_control，不报错 |
| Stage 4 Docker 执行失败 | 写入 BacktestReport(error_message=...) 交给 Critic 处理 |
| Stage 5 全部失败 | 正常记录到 FactorPool，进入下一轮 |
| 连续 10 轮无新因子通过 | 触发告警通知，但继续运行（不 interrupt） |

---

## 7. 运行模式

```python
# src/core/orchestrator/_entrypoints.py 的入口函数

async def run_evolve(rounds: int = 20, islands: List[str] = None):
    """进化模式：多 Island 轮换，持续运行"""
    graph = build_graph()
    config = {"configurable": {"thread_id": f"evoquant_{datetime.now().isoformat()}"}}
    initial_state = AgentState(current_round=0)
    await graph.ainvoke(initial_state, config=config)

async def run_single(island: str):
    """单次模式：指定 Island，单轮调试"""
    graph = build_graph()
    config = {"configurable": {"thread_id": f"debug_{island}_{datetime.now().isoformat()}"}}
    initial_state = AgentState(current_round=0, current_island=island)
    await graph.ainvoke(initial_state, config=config)
```

---

## 8. 配置常量

当前版本已经没有单独的 `src/core/config.py`。

实际配置分散在三类位置：

- 环境变量
  - 例如 `MAX_ROUNDS`、`REPORT_EVERY_N_ROUNDS`
- schema/阈值对象
  - 例如 `src/schemas/thresholds.py` 中的 `THRESHOLDS`
- 模块级调度常量
  - 例如 `src/factor_pool/scheduler.py` 中的退火与重置参数

因此这里更应理解为“配置来源分层”，而不是“统一的 config.py 文件”。

---

## 9. 评估基准定义

**旧基准（已废弃）**：`Alpha158 + LightGBM 训练集 Sharpe = 2.67`
该数字为样本内（IS）估计，不适合作为 Agent 因子的超越目标。

**新基准（三条线，均使用样本外 OOS 估计）**：

| 基准线 | 计算方式 | 说明 |
|--------|---------|------|
| **B0：等权 CSI300** | CSI300 指数等权持有，无再平衡 | 最简单的基准，任何策略必须超越 |
| **B1：Alpha158+LightGBM OOS Sharpe** | 在测试集（2025-04-01 起）计算 | 机器学习基准，Pixiu 的主要超越目标 |
| **B2：单因子 IC > 0.035** | IC × √252 的信息比 | 单因子有效性标准，Critic 放行阈值 |

`CriticThresholds` 中的 `sharpe_threshold` 应对标 **B1 的 OOS 值**，该值需在运行基线后更新（预期约 1.5-2.0，显著低于 IS 的 2.67）。

执行方式：
```bash
# 重跑基线并记录 OOS Sharpe
uv run python -m src.core.run_baseline
# 如需收紧判断阈值，更新 src/schemas/thresholds.py 中的 THRESHOLDS 配置
```
