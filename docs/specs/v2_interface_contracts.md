# Pixiu v2 接口契约（Interface Contracts）

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_architecture_overview.md`
> **所有 Agent 必须使用此处定义的 Pydantic 模型通信，禁止直接传递 dict**

---

## 0. 基础规范

### 文件位置
所有 schema 定义放在 `src/schemas/` 目录：

```
src/schemas/
├── __init__.py
├── market_context.py      # Stage 1 schemas
├── research_note.py       # Stage 2 schemas
├── exploration.py         # Stage 4a schemas
├── backtest.py            # Stage 4b schemas
├── judgment.py            # Stage 5 schemas
└── state.py               # LangGraph AgentState v2
```

### 通用基类

```python
# src/schemas/__init__.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class EvoQuantBase(BaseModel):
    """所有 EvoQuant schema 的基类"""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(default="2.0")

    class Config:
        extra = "forbid"  # 禁止额外字段，强制接口显式
```

---

## 1. Stage 1：市场上下文

### `MarketContextMemo`

```python
# src/schemas/market_context.py

class NorthboundFlow(EvoQuantBase):
    net_buy_bn: float           # 净买入（亿元）
    top_sectors: List[str]      # 资金流入最多的板块（最多5个）
    top_stocks: List[str]       # 资金流入最多的个股（最多10个）
    sentiment: str              # "bullish" | "neutral" | "bearish"

class MacroSignal(EvoQuantBase):
    signal: str                 # 信号描述
    source: str                 # 来源（"fed" | "cpi" | "pmi" | "news"）
    direction: str              # "positive" | "negative" | "neutral"
    confidence: float           # 0.0 - 1.0

class HistoricalInsight(EvoQuantBase):
    """LiteratureMiner 从 FactorPool 检索到的相关历史"""
    island: str
    best_factor_formula: str
    best_sharpe: float
    common_failure_modes: List[str]
    suggested_directions: List[str]

class MarketContextMemo(EvoQuantBase):
    date: str                                    # "2026-03-07"
    northbound: Optional[NorthboundFlow]
    macro_signals: List[MacroSignal]
    hot_themes: List[str]                        # 当日热点主题
    historical_insights: List[HistoricalInsight] # 每个 Island 一条
    suggested_islands: List[str]                 # 建议本轮重点探索的 Island
    market_regime: str                           # "trending_up" | "trending_down" | "sideways" | "volatile"
    raw_summary: str                             # 给 Researcher 读的自然语言摘要（500字以内）
```

---

## 2. Stage 2：研究假设

### `FactorResearchNote`

```python
# src/schemas/research_note.py

class ExplorationQuestion(EvoQuantBase):
    """Researcher 提出的探索性问题，由 ExplorationAgent 在 Stage 4a 执行"""
    question: str               # 自然语言问题
    suggested_analysis: str     # 建议的分析方式（"correlation", "ic_by_regime", "quantile_return"等）
    required_fields: List[str]  # 需要的数据字段

class FactorResearchNote(EvoQuantBase):
    # 标识
    note_id: str                # UUID，格式：{island}_{date}_{sequence}
    island: str                 # 所属 Island
    iteration: int              # 本 Island 的第几次迭代

    # 核心内容
    hypothesis: str             # 经济/行为金融直觉（自然语言，100-300字）
    economic_intuition: str     # 为何此因子应该有效的机制解释
    proposed_formula: str       # 初步 Qlib 公式（可能尚未精化）
    final_formula: Optional[str]  # 探索完成后的最终公式（Stage 4a 完成后填入）

    # 探索性请求（可选）
    exploration_questions: List[ExplorationQuestion]  # 空列表表示直接进回测

    # 参数
    universe: str = "csi300"
    holding_period: int = 1      # 持仓天数
    backtest_start: str = "2021-06-01"
    backtest_end: str = "2025-03-31"

    # 预期与风险
    expected_ic_min: float = 0.02
    risk_factors: List[str]      # 可能导致失败的因素

    # 元数据
    inspired_by: Optional[str]   # 启发来源（FactorPool factor_id 或论文名）
    market_context_date: str     # 对应的 MarketContextMemo 日期

    # 状态流转（由 Orchestrator 填写，Researcher 不填）
    status: str = "draft"  # "draft" | "exploring" | "ready_for_backtest" | "completed"
```

### `AlphaResearcherBatch`（单个 Island 的批量输出）

```python
class AlphaResearcherBatch(EvoQuantBase):
    """AlphaResearcher 的单次调用输出，包含 2-3 个差异化候选。

    设计原因：单次 LLM 调用生成多个候选，成本几乎等同于单个候选，
    但可显著扩大漏斗入口（从 6 个/轮 提升到 12-18 个/轮），
    使 Stage 3 过滤有实质意义。
    """
    island: str
    notes: List[FactorResearchNote]         # 2-3 个，要求差异化经济逻辑
    generation_rationale: str               # 为何选择这几个方向（供审计）
```

### `SynthesisInsight`（跨 Island 关联）

```python
class SynthesisInsight(EvoQuantBase):
    """SynthesisAgent 发现的跨 Island 关联"""
    island_a: str
    island_b: str
    note_id_a: str
    note_id_b: str
    relationship: str           # 描述两个假设的关联
    combined_hypothesis: Optional[str]  # 如果值得合并，给出合并假设
    priority: str               # "high" | "medium" | "low"
```

---

## 3. Stage 4a：探索执行

### `ExplorationRequest` / `ExplorationResult`

```python
# src/schemas/exploration.py

class ExplorationRequest(EvoQuantBase):
    request_id: str             # UUID
    note_id: str                # 对应的 FactorResearchNote
    question: ExplorationQuestion
    data_fields: List[str]      # 实际需要从 Qlib 加载的字段

class ExplorationResult(EvoQuantBase):
    request_id: str
    note_id: str
    success: bool
    script_used: str            # ExplorationAgent 生成的 Python 脚本（审计用）
    findings: str               # 自然语言总结（给 Researcher 读）
    key_statistics: Dict[str, Any]  # 关键统计数值（IC、相关性等）
    refined_formula_suggestion: Optional[str]  # 基于探索结果建议的公式修正
    error_message: Optional[str]
```

---

## 4. Stage 4b：回测执行

### `BacktestReport`

```python
# src/schemas/backtest.py

class BacktestMetrics(EvoQuantBase):
    sharpe: float
    annualized_return: float
    max_drawdown: float
    ic_mean: float
    ic_std: float
    icir: float                 # IC / IC_std
    turnover_rate: float        # 日均换手率
    win_rate: Optional[float]
    long_short_spread: Optional[float]

class BacktestReport(EvoQuantBase):
    # 标识
    report_id: str             # UUID
    note_id: str               # 对应的 FactorResearchNote
    factor_id: str             # 格式：{island}_{date}_{seq}（进入 FactorPool 的 key）
    island: str
    formula: str               # 实际回测的 Qlib 公式

    # 结果
    metrics: BacktestMetrics
    passed: bool               # 是否通过 Critic 阈值

    # 执行元数据
    execution_time_seconds: float
    qlib_output_raw: str       # 原始 stdout（调试用）
    error_message: Optional[str]
```

---

## 5. Stage 5：判断与综合

### `CriticVerdict`

```python
# src/schemas/judgment.py

class ThresholdCheck(EvoQuantBase):
    metric: str
    value: float
    threshold: float
    passed: bool

class CriticVerdict(EvoQuantBase):
    report_id: str
    factor_id: str
    overall_passed: bool

    # 逐项检查
    checks: List[ThresholdCheck]

    # 失败归因（overall_passed=False 时必填）
    failure_mode: Optional[str]   # "low_sharpe" | "low_ic" | "high_turnover" | "overfitting" | "execution_error"
    failure_explanation: str      # 自然语言解释给 Researcher 的反馈
    suggested_fix: Optional[str]  # 建议的改进方向

    # FactorPool 写入决策
    register_to_pool: bool        # 即使失败也写入（用于 error-driven RAG）
    pool_tags: List[str]          # ["passed", "failed:low_ic", "island:momentum"] 等
```

### `RiskAuditReport`

```python
class CorrelationFlag(EvoQuantBase):
    existing_factor_id: str
    correlation: float
    flag_reason: str  # "too_similar" | "opposite" | "complement"

class RiskAuditReport(EvoQuantBase):
    factor_id: str
    overfitting_score: float      # 0.0（无过拟合风险）~ 1.0（高风险），基于 IS/OOS Sharpe 比值
    overfitting_flag: bool        # overfitting_score > 0.4
    correlation_flags: List[CorrelationFlag]
    recommendation: str           # "approve" | "approve_with_caution" | "reject"
    audit_notes: str
```

### `PortfolioAllocation`

```python
class FactorWeight(EvoQuantBase):
    factor_id: str
    island: str
    weight: float               # 0.0 - 1.0，所有 weight 之和 = 1.0
    rationale: str              # 为何给此权重

class PortfolioAllocation(EvoQuantBase):
    allocation_id: str
    timestamp: str
    factor_weights: List[FactorWeight]
    expected_portfolio_sharpe: float
    expected_portfolio_ic: float
    diversification_score: float  # 因子间平均相关性（越低越好）
    total_factors: int
    notes: str
```

### `CIOReport`

```python
class CIOReport(EvoQuantBase):
    """触发 interrupt()，等待人类 CIO 审批"""
    report_id: str
    period: str                 # "2026-03-07 第42轮进化"

    # 本轮摘要
    total_factors_tested: int
    new_factors_approved: int
    best_new_factor: Optional[str]  # factor_id
    best_new_sharpe: Optional[float]

    # 组合状态
    current_portfolio: PortfolioAllocation
    portfolio_change_summary: str   # 本轮对组合的改变

    # 值得关注的发现
    highlights: List[str]           # 3-5条要点，给 CIO 快速阅读
    risks: List[str]                # 风险提示

    # 全文报告（Markdown 格式）
    full_report_markdown: str

    # 等待 CIO 操作
    suggested_actions: List[str]    # ["approve_portfolio", "redirect:momentum", "pause"]
    requires_human_decision: bool = True
```

---

## 6. LangGraph 状态（AgentState v2）

```python
# src/schemas/state.py

class AgentState(EvoQuantBase):
    """LangGraph 全局状态，在节点间传递"""

    # 当前上下文
    current_round: int = 0
    current_island: str = "momentum"
    iteration: int = 0

    # Stage 1 输出
    market_context: Optional[MarketContextMemo] = None

    # Stage 2 输出
    research_notes: List[FactorResearchNote] = Field(default_factory=list)
    synthesis_insights: List[SynthesisInsight] = Field(default_factory=list)

    # Stage 3 输出（过滤后）
    approved_notes: List[FactorResearchNote] = Field(default_factory=list)
    filtered_count: int = 0  # 被过滤掉的数量

    # Stage 4 输出
    exploration_results: List[ExplorationResult] = Field(default_factory=list)
    backtest_reports: List[BacktestReport] = Field(default_factory=list)

    # Stage 5 输出
    critic_verdicts: List[CriticVerdict] = Field(default_factory=list)
    risk_audit_reports: List[RiskAuditReport] = Field(default_factory=list)
    portfolio_allocation: Optional[PortfolioAllocation] = None
    cio_report: Optional[CIOReport] = None

    # 人机交互
    awaiting_human_approval: bool = False
    human_decision: Optional[str] = None  # "approve" | "redirect:xxx" | "stop"

    # 错误处理
    last_error: Optional[str] = None
    error_stage: Optional[str] = None

    # 兼容 v1（临时，迁移完成后删除）
    # factor_hypothesis: Optional[dict] = None  # DEPRECATED
    # backtest_metrics: Optional[dict] = None   # DEPRECATED
```

---

## 7. 阈值配置（集中管理）

```python
# src/schemas/thresholds.py

class CriticThresholds(EvoQuantBase):
    """可通过环境变量覆盖的阈值配置"""
    min_sharpe: float = 2.67          # 基线 Sharpe
    min_ic_mean: float = 0.02
    min_icir: float = 0.30
    max_turnover_rate: float = 0.50
    max_overfitting_score: float = 0.40
    min_novelty_threshold: float = 0.30  # AST 相似度低于此值才通过 Novelty Filter
    stage3_top_k: int = 5             # Stage 3 最多放行多少个候选进入回测

THRESHOLDS = CriticThresholds()  # 全局单例
```

---

## 8. 禁止事项

- **禁止**：任何 Agent 直接修改另一个 Agent 创建的 schema 对象内部字段
- **禁止**：在 Agent 内部 hardcode 任何阈值数值，所有阈值从 `THRESHOLDS` 读取
- **禁止**：Agent 之间通过 `dict` 或裸 `str` 传递结构化数据
- **禁止**：`BacktestReport` 以外的任何方式返回回测结果（禁止字符串解析）
- **允许**：Agent 可以在 schema 的 Optional 字段中放 `None`，表示该信息暂不可用
