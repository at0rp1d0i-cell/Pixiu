# Pixiu v2 Stage 4→5 Golden Path
Purpose: Define the single deterministic Stage 4→5 closure path that current runtime and tests should converge on.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 创建：2026-03-09
> 目的：把 Stage 4 执行层和 Stage 5 判断层压缩成一条可实现、可测试、可回归的唯一真路径。
> 适用范围：当前 runtime 收口、集成测试和最小 CIO 验收链。
> 关联规格：`11_interface-contracts.md`、`12_orchestrator.md`、`23_stage-4-execution.md`、`24_stage-5-judgment.md`、`14_factor-pool.md`、`16_test-pipeline.md`

---

## 0. 结论

当前最该钉死的不是完整 Stage 5 全图，而是下面这条 deterministic 闭环：

```text
FactorResearchNote.final_formula
→ Stage 3 pass
→ Stage 4 deterministic backtest
→ BacktestReport
→ Stage 5 deterministic verdict
→ FactorPool writeback
→ CIOReport (minimal)
```

唯一原则：

> Stage 5 不负责“理解” Stage 4，它只消费一个严格定义好的 `BacktestReport`。

如果 Stage 4 输出仍像日志堆，Stage 5 就会被迫靠临场解释补洞，系统无法稳定回归。

---

## 1. 本轮不做什么

以下内容不纳入当前 golden path：

- `ExplorationAgent`
- `RiskAuditor` 的复杂相关性矩阵和过拟合诊断全量版
- `PortfolioManager` 的跨因子组合优化
- Dashboard 前端展示
- Reflection system
- OOS / generalization 的完整生命周期
- 多 Island 协同决策
- 人类审批复杂分支

本轮只做最小闭环：

- 输入：一个已通过 Stage 3 的 `FactorResearchNote`
- 处理：compile、backtest、parse、critic、writeback、report
- 输出：`BacktestReport`、`CriticVerdict`、`FactorPoolRecord`、最小 `CIOReport`

---

## 2. 唯一真路径

### Step 1. 接收唯一输入文档

Stage 4 唯一合法输入是：

```python
FactorResearchNote
```

其中唯一允许进入执行层的公式字段是：

```python
final_formula: str
```

约束：

- 执行层不能再读 exploration 草稿和自然语言描述来“猜公式”
- 进入 Stage 4 的只能是 Stage 3 已验证的最终表达式
- Stage 4 不承担研究和修正，只承担执行

### Step 2. deterministic compile

`Coder` 的本质应视为一个 deterministic executor。

输入：

- `FactorResearchNote.final_formula`
- `universe`
- `date_range`
- 运行时固定模板

输出：

```python
class BacktestReport(BaseModel):
    report_id: str
    run_id: str
    note_id: str
    factor_id: str
    formula: str
    metrics: BacktestMetrics
    artifacts: ArtifactRefs
    error_message: Optional[str]
```

必须 deterministic 的部分：

- 模板文件固定
- 模板渲染逻辑固定
- artifact 落盘规则固定
- stdout/stderr 采集位置固定
- 解析器版本固定

当前阶段禁止：

- 用 LLM 生成执行脚本
- 在运行时临时改模板
- 根据错误信息自动修脚本
- 从自由文本恢复参数

### Step 3. 执行与原始产物落盘

执行后必须显式分成两类产物：

- `raw artifacts`
  - stdout
  - stderr
  - rendered script
- `structured summary`
  - `BacktestMetrics`
  - `status / failure_reason`
  - `execution_meta`

Stage 5 只能消费结构化摘要，不能直接读 raw log。

### Step 4. 解析成唯一标准文档

Stage 4 的唯一标准输出应为：

```python
class BacktestReport(BaseModel):
    report_id: str
    run_id: str
    note_id: str
    island_id: str

    status: Literal["success", "failed", "partial"]
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None

    execution_meta: ExecutionMeta
    factor_spec: FactorSpecSnapshot
    metrics: BacktestMetrics
    artifacts: ArtifactRefs
```

---

## 3. `BacktestReport` 最小充分字段集

### 3.1 `execution_meta`

```python
class ExecutionMeta(BaseModel):
    engine: Literal["qlib"]
    engine_version: str
    template_version: str
    universe: str
    benchmark: str
    freq: str
    start_date: date
    end_date: date
    runtime_seconds: float
    timestamp_utc: datetime
```

任何 verdict 都必须绑定执行上下文，否则指标含义不可比较。

### 3.2 `factor_spec`

```python
class FactorSpecSnapshot(BaseModel):
    formula: str
    hypothesis: str
    economic_rationale: str
```

这样 FactorPool 和 CIOReport 才能保留“结果对应哪个研究想法”的语义锚点。

### 3.3 `metrics`

第一版只锁以下最小判定指标：

```python
class BacktestMetrics(BaseModel):
    sharpe: Optional[float] = None
    annual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    ic_mean: Optional[float] = None
    icir: Optional[float] = None
    turnover: Optional[float] = None
    coverage: Optional[float] = None
```

这一版先不强塞：

- 分层收益全明细
- 行业中性前后对照
- rolling stats
- 复杂风险暴露
- bootstrap 置信区间

### 3.4 `artifacts`

```python
class ArtifactRefs(BaseModel):
    stdout_path: str
    stderr_path: str
    script_path: str
    raw_result_path: Optional[str] = None
    equity_curve_path: Optional[str] = None
```

这些字段主要服务排障和审计，不直接给 Stage 5 判定逻辑使用。

---

## 4. Stage 5 deterministic MVP

当前 Stage 5 的 deterministic/template MVP 已经收缩成四个组件：

1. `Critic`
2. `RiskAuditor`
3. `PortfolioManager`
4. `ReportWriter` 的 deterministic 模板版

也就是说，当前主链已经是：

`BacktestReport -> CriticVerdict / RiskAuditReport -> PortfolioAllocation -> CIOReport`

不做的是更复杂的相关性矩阵、组合优化求解和 richer narrative synthesis。

### 4.1 `CriticVerdict`

```python
class CriticVerdict(BaseModel):
    verdict_id: str
    report_id: str
    note_id: str

    decision: Literal["promote", "archive", "reject", "retry"]
    score: float
    passed_checks: list[str]
    failed_checks: list[str]

    summary: str
    reason_codes: list[str]
```

状态约束：

- `promote`：通过最小门槛，进入候选池或后续流程
- `archive`：执行有效但不够好，留档
- `reject`：策略质量明显不达标
- `retry`：执行、解析或判定异常，允许重试

### 4.2 判定顺序

判定顺序必须固定：

1. 完整性检查
2. 硬阈值检查
3. 加权评分

不要先看分数，再补完整性。

### 4.3 阈值配置

阈值必须外置成配置，不允许埋在逻辑里：

```python
class CriticThresholds(BaseModel):
    min_sharpe: float = 0.8
    min_ic_mean: float = 0.02
    min_icir: float = 0.3
    max_turnover: float = 0.5
    max_drawdown: float = 0.25
    min_coverage: float = 0.7
```

这些默认值只是收口初稿，最终口径要根据实际 universe 和回测配置校准。

### 4.4 `reason_codes`

第一版直接枚举：

- `LOW_SHARPE`
- `LOW_IC`
- `LOW_ICIR`
- `HIGH_TURNOVER`
- `HIGH_DRAWDOWN`
- `LOW_COVERAGE`
- `EXECUTION_FAILED`
- `PARSE_INCOMPLETE`
- `JUDGE_INCOMPLETE`

实现偏差和当前兼容层，请统一查看 `../overview/05_spec-execution-audit.md`。

---

## 5. `FactorPool` 写回口径

第一版 `FactorPool` 不要变成全量日志仓。

建议写回最小结构：

```python
class FactorPoolRecord(BaseModel):
    factor_id: str
    note_id: str
    formula: str
    hypothesis: str
    economic_rationale: str

    backtest_report_id: str
    verdict_id: str
    decision: str
    score: float

    sharpe: Optional[float]
    ic_mean: Optional[float]
    icir: Optional[float]
    turnover: Optional[float]
    max_drawdown: Optional[float]
    coverage: Optional[float]

    created_at: datetime
    tags: list[str] = []
```

不在第一版写入：

- 长段自然语言失败分析
- LLM 反思摘要
- 多轮研究轨迹
- 风险归因全文

FactorPool 第一职责是结果索引和可检索元数据，不是垃圾填埋场。

---

## 6. `CIOReport` 的最小版

第一版 `CIOReport` 是 round-level 审批材料，不是单因子详报。

```markdown
# CIO Review: round-{current_round}

## Summary
- Tested factors:
- Approved factors:
- Best factor:
- Best Sharpe:

## Best Factor
- Formula:
- Hypothesis:
- Economic rationale:

## Portfolio
- Total factors:
- Expected portfolio Sharpe:
- Expected portfolio IC:

## Failures
- factor_id: failure_mode

## Decisions
- factor_id: decision / score / reason_codes
```

第一版报告先模板化，不让 LLM 自由发挥。

---

## 7. orchestrator 收口方式

当前编排层即使保留 12 节点主图，也应该明确一条最小主链：

```text
coder
→ judgment
→ portfolio
→ report
→ human_gate
```

每个节点约束：

 - `coder` 产出 `BacktestReport`
 - `judgment` 产出 `CriticVerdict` 与 `RiskAuditReport`，并负责 pool / constraint 写回
 - `portfolio` 基于本轮通过因子生成最小 allocation
 - `report` 生成 `CIOReport`
 - `human_gate` 显式挂起等待人类审批

当前 active orchestrator 仍以 `12_orchestrator.md` 和实际 `src/core/orchestrator/` 代码为准；这里强调的是 Stage 4 -> 5 的最小收口意图，而不是重新定义另一套运行时对象。

如果需要补一个最小状态视图，也应直接围绕当前对象来写：

- `backtest_reports`
- `critic_verdicts`
- `risk_audit_reports`
- `portfolio_allocation`
- `cio_report`
- `awaiting_human_approval`
- `errors`

state 必须保持瘦身，否则 orchestrator 很快会退化成状态泥潭。

---

## 8. 错误分类

错误分类至少分为四类：

### A. compile failure

例如：

- `final_formula` 不可渲染
- 模板参数缺失
- config 生成失败

记录建议：

```text
failure_stage = "compile"
decision = "retry" 或 "reject"
```

### B. run failure

例如：

- subprocess 非零退出
- sandbox 崩溃
- Qlib 运行异常

记录建议：

```text
failure_stage = "run"
decision = "retry"
```

### C. parse failure

例如：

- stdout JSON 不完整
- metrics 缺失
- schema 验证失败

记录建议：

```text
failure_stage = "parse"
decision = "retry"
```

### D. judge failure

例如：

- 阈值配置缺失
- 判定对象不完整
- score 计算失败

记录建议：

```text
failure_stage = "judge"
decision = "retry"
```

如果所有异常都只写成 `failed`，后续稳定性分析和失败分布会失真。

---

## 9. 测试钉法

这条 golden path 的测试要围绕闭环，而不是堆很多彼此孤立的单测。

### 9.1 单元测试

- compile tests
  - formula → template render
  - config 生成
  - 输出路径规则
- parser tests
  - 原始执行结果 → `BacktestReport`
  - 缺字段时报错
  - 错误分类正确
- critic tests
  - 给定固定 metrics，verdict 稳定
  - 阈值边界行为正确
  - score 计算 deterministic

### 9.2 集成测试

至少锁一条主链：

```text
FactorResearchNote fixture
→ compile
→ mock runner output
→ parse BacktestReport
→ critic verdict
→ factor pool writeback
→ report render
```

当前状态：

- 该主链已由 `tests/test_stage45_golden_path.py` 锁定
- 当前测试通过的是 mock runner + stub pool 版本，属于 deterministic integration，而不是带真实 Docker / Qlib / Chroma 的 e2e

### 9.3 最小 E2E smoke test

等 runner 稳定后再补：

```text
真实模板 + 最小 sandbox + 最小 mock/cheap dataset
```

第一版不追求金融意义上的真实回测，先追求主路径真的能跑通。

---

## 10. 验收标准

满足以下条件，才算 Stage 4→5 闭环收口：

1. `FactorResearchNote.final_formula` 能被唯一消费
2. compile / runner 不依赖 LLM
3. 回测产物能稳定解析成 `BacktestReport`
4. `BacktestReport` 字段足以支持 deterministic 判定
5. `CriticVerdict` 不依赖自由文本推理即可生成
6. `FactorPool` 写回结构固定且可重复
7. 最小 `CIOReport` 可产出
8. 至少有 1 条集成测试锁住整条链

额外硬条件：

> 同一输入在相同配置下重复运行，除时间戳和路径等非本质字段外，`CriticVerdict.decision` 与 `score` 必须稳定一致。

---

## 11. 实施顺序

### Milestone 1. 钉死 `BacktestReport`

- schema 定义
- parser 定义
- raw artifacts / structured report 分离
- 执行失败分类

### Milestone 2. 钉死 deterministic `Critic`

- threshold config
- rule engine
- score function
- reason codes

### Milestone 3. 钉死 `FactorPool` 写回

- 写回 schema
- upsert / insert 逻辑
- report / verdict 关联

### Milestone 4. 钉死 `CIOReport` 模板

- deterministic markdown renderer
- artifact refs 展示
- passed / failed checks 展示

### Milestone 5. 补最小集成测试

- 从 note 输入
- 到 report / verdict / persist / report 输出
- 锁住整条 golden path

---

## 已做决策

- 当前 Stage 4→5 先走 deterministic MVP，不做更复杂的 judgment / optimization / narrative 扩展栈。
- `BacktestReport` 是 Stage 4→5 的唯一判定边界。
- 当前 Stage 5 MVP 已包含 `Critic -> RiskAuditor -> PortfolioManager -> ReportWriter`。
- `FactorPool` 第一版只存结果摘要、可检索元信息和 artifact 引用。

## 未决问题

- `BacktestMetrics` 的默认阈值应按哪个 universe / benchmark / date range 标定。
- `FactorPool` 最终采用 insert 还是 upsert 作为默认写入策略。
- `BacktestReport` 是否需要在第一版就携带 `annual_return` 之外的更多收益拆解指标。

## 验收映射

- 规格实现验收以 `16_test-pipeline.md` 中的 unit / integration / smoke 分层为准。
- 本文档对应的最小验收产物应包括：`BacktestReport` fixture、`CriticVerdict` fixture、FactorPool 写回集成测试、模板化 `CIOReport` 样例。
