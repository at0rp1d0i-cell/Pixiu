# Pixiu v2 Interface Contracts

> 版本：2.1
> 角色：定义 Pixiu 的当前对象边界和跨 plane 契约
> 前置依赖：`../overview/architecture-overview.md`、`authority-model.md`

---

## 1. 设计原则

接口契约的重点不是“把所有 schema 逐行列出来”，而是先冻结系统级对象边界。

当前需要回答的核心问题是：

1. 哪些对象构成系统主链
2. 各对象分别服务哪个 plane
3. 当前运行时应朝哪组对象收敛

## 2. Canonical Object Set

当前建议冻结的核心对象如下：

| Object | Plane | 作用 |
|---|---|---|
| `Hypothesis` | Cognitive | 表达市场机制假设、适用/失效 regime、启发来源 |
| `StrategySpec` | Cognitive -> Execution | 表达可执行因子语义与参数边界 |
| `FilterReport` | Execution Sandbox | 表达 Stage 3 的 gate 结果和淘汰原因 |
| `BacktestRun` | Execution Sandbox | 表达一次确定性执行任务的元信息 |
| `EvaluationReport` | Artifact & Knowledge | 表达结构化执行结果和核心指标 |
| `FailureConstraint` | Knowledge | 表达失败被压缩后的硬约束 |
| `CriticVerdict` | Knowledge / Evaluation | 表达结构化裁决、reason codes 和 decision |
| `FactorPoolRecord` | Knowledge | 表达进入知识平面的稳定记录模型 |
| `RunRecord` / `RunSnapshot` | Control Plane | 表达运行态与外部读模型 |
| `CIOReport` | Product Access | 表达人机交互与审批入口 |

## 3. Canonical Objects

### `Hypothesis`

回答“为什么值得测”。

```python
class Hypothesis(BaseModel):
    hypothesis_id: str
    island: str
    mechanism: str
    economic_rationale: str
    candidate_driver: str | None = None
    applicable_regimes: list[str] = []
    invalid_regimes: list[str] = []
    inspirations: list[str] = []
    failure_priors: list[str] = []
```

### `StrategySpec`

回答“到底测什么”。

```python
class StrategySpec(BaseModel):
    spec_id: str
    hypothesis_id: str
    factor_expression: str
    universe: str
    benchmark: str
    freq: str
    holding_period: int | None = None
    required_fields: list[str]
    parameter_notes: dict[str, str] = {}
```

### `FilterReport`

表达 Stage 3 的硬 gate 结果。

```python
class FilterReport(BaseModel):
    report_id: str
    note_id: str
    passed: bool
    validator_passed: bool
    novelty_passed: bool
    alignment_passed: bool
    rejection_reasons: list[str] = []
```

### `BacktestRun`

表达一次确定性执行任务的元信息，不含裁决。

```python
class BacktestRun(BaseModel):
    run_id: str
    note_id: str
    spec_id: str | None = None
    factor_expression: str
    engine: str
    template_version: str
    universe: str
    benchmark: str
    start_date: str
    end_date: str
    status: str
```

### `EvaluationReport`

表达 Stage 4 的结构化结果，是 Stage 5 的直接输入。

```python
class EvaluationReport(BaseModel):
    report_id: str
    backtest_run_id: str
    note_id: str
    status: str
    failure_stage: str | None = None
    failure_reason: str | None = None
    metrics: dict[str, float | None]
    artifact_refs: dict[str, str]
```

### `FailureConstraint`

这是 Stage 5 最值得沉淀的对象之一。

```python
class FailureConstraint(BaseModel):
    constraint_id: str
    source_note_id: str
    category: str
    summary: str
    reason_codes: list[str]
    applicable_regimes: list[str] = []
    invalid_regimes: list[str] = []
```

### `CriticVerdict`

表达结构化裁决。

```python
class CriticVerdict(BaseModel):
    verdict_id: str
    report_id: str
    note_id: str
    decision: str
    score: float
    passed_checks: list[str]
    failed_checks: list[str]
    reason_codes: list[str]
    summary: str
```

### `FactorPoolRecord`

表达进入知识平面的稳定记录对象。

```python
class FactorPoolRecord(BaseModel):
    factor_id: str
    note_id: str
    formula: str
    hypothesis: str
    economic_rationale: str
    verdict_id: str
    decision: str
    score: float
    metrics: dict[str, float | None]
    tags: list[str] = []
```

### `RunRecord` / `RunSnapshot`

表达控制平面的稳定读模型。

```python
class RunRecord(BaseModel):
    run_id: str
    mode: str
    status: str
    current_round: int
    current_stage: str
    started_at: str
    finished_at: str | None = None
    last_error: str | None = None

class RunSnapshot(BaseModel):
    run_id: str
    approved_notes_count: int
    backtest_reports_count: int
    verdicts_count: int
    awaiting_human_approval: bool
    updated_at: str
```

### `CIOReport`

表达外部审批与人机交互对象。

```python
class CIOReport(BaseModel):
    report_id: str
    run_id: str
    summary: str
    highlights: list[str]
    risks: list[str]
    artifact_refs: dict[str, str]
    suggested_actions: list[str]
```

## 4. Runtime Bridge

当前运行时尚未完全按这组对象落地，因此仍存在少量桥接对象。

### `FactorResearchNote`

当前仍是 Stage 2 到 Stage 4 的主要桥接对象。

它目前兼任了三类职责：

- hypothesis 表达
- candidate formula 表达
- exploration bridge

长期应将这些职责拆分给：

- `Hypothesis`
- `StrategySpec`
- `ExplorationRequest`

### `BacktestReport`

当前运行时仍使用 `BacktestReport` 作为 Stage 4 产物。

它实际上在承载两层语义：

- `BacktestRun`
- `EvaluationReport`

设计上应逐步把执行元信息与评估结果分离。

### 现有 `CriticVerdict`

当前运行时中的 `CriticVerdict` 已开始靠近目标形态，但仍保留少量兼容字段：

- `overall_passed`
- `failure_mode`
- `register_to_pool`
- `pool_tags`

这类兼容字段。

新消费方应优先依赖：

- `decision`
- `score`
- `passed_checks`
- `failed_checks`
- `reason_codes`

### `AgentState`

`AgentState` 仍是 graph 内部的工作状态对象。

它不是对外契约，不应直接暴露给：

- CLI
- API
- Dashboard

这些入口应优先读取控制平面的 `RunRecord / RunSnapshot / ArtifactRecord`。

## 5. Object Flow

当前推荐的对象流如下：

```text
MarketContextMemo
  -> Hypothesis / FactorResearchNote
  -> StrategySpec / final_formula
  -> FilterReport
  -> BacktestRun
  -> EvaluationReport / BacktestReport
  -> CriticVerdict
  -> FailureConstraint + FactorPoolRecord
  -> CIOReport
```

## 6. Design Direction

当前对象集的收敛方向应保持稳定：

1. 上游把 `Hypothesis / StrategySpec` 做实
2. 中游把 `FilterReport / BacktestRun / EvaluationReport` 做成主链对象
3. 下游把 `FailureConstraint / FactorPoolRecord / CIOReport` 做成知识和审批对象

实现偏差与当前落地状态，请统一查看 `../overview/spec-execution-audit.md`。
