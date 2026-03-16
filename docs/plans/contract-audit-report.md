# Contract Audit Report: BacktestReport / CriticVerdict / FactorPoolRecord

> 审计日期：2026-03-16
> 审计范围：三大核心 schema 的双轨字段、跨 Stage 合约断裂、语义重复
> 审计方法：静态代码分析（schema 定义 + 运行时读写追踪）

---

## 1. 字段清单

### 1.1 BacktestMetrics (`src/schemas/backtest.py:33-45`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `sharpe` | `float` | [active] | Stage 5 judgment.py:26,131; pool.py:397; cio_report_renderer.py:55 |
| 2 | `annualized_return` | `float` | [active] | coder.py:183 写入; pool.py:203 (v1 register) 读取 |
| 3 | `annual_return` | `Optional[float]` | [duplicate] | **语义重复 `annualized_return`**。coder.py:184 赋值为 `raw.get("annualized_return")`，即与 `annualized_return` 完全相同值。仅 cio_report_renderer.py:56 读取 |
| 4 | `max_drawdown` | `float` | [active] | judgment.py:57,135; pool.py:399,425 |
| 5 | `ic_mean` | `float` | [active] | judgment.py:38; pool.py:398 |
| 6 | `ic_std` | `float` | [orphan] | **定义于 L39，运行时从未被任何消费者读取**。coder.py:187 写入，但下游（judgment.py, pool.py, cio_report_renderer.py）均不使用 |
| 7 | `icir` | `float` | [active] | judgment.py:43; pool.py:399 |
| 8 | `turnover_rate` | `float` | [duplicate] | **与 `turnover` 语义重复**。judgment.py:26 做 fallback: `turnover if turnover is not None else turnover_rate`。coder.py:189,198 写入。RiskAuditor (judgment.py:239) 直接读 `turnover_rate` |
| 9 | `turnover` | `Optional[float]` | [duplicate] | 与 `turnover_rate` 语义重复。coder.py:190 赋值为 `raw.get("turnover_rate", 0.0)`，即同源。judgment.py:26,128 优先读此字段 |
| 10 | `coverage` | `Optional[float]` | [optional-but-critical] | **标记为 Optional 但 Stage 5 实际依赖**。judgment.py:27 fallback 为 1.0; judgment.py:63 用于 threshold check; pool.py:400,426 写入 |
| 11 | `win_rate` | `Optional[float]` | [orphan] | **定义于 L44，运行时从未读取**。coder.py 也未写入此字段 |
| 12 | `long_short_spread` | `Optional[float]` | [orphan] | **定义于 L45，运行时从未读写** |

### 1.2 BacktestReport (`src/schemas/backtest.py:47-70`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `report_id` | `str` | [active] | coder.py:39,50; judgment.py:196; pool.py:389,415 |
| 2 | `run_id` | `Optional[str]` | [orphan] | **标记为 Optional，coder.py:50,125 写入但下游从未读取**。api/server.py:125 读 `report.run_id` 但那是 RunRecord 不是 BacktestReport |
| 3 | `note_id` | `str` | [active] | judgment.py:198; pool.py:389; factor_pool_writer.py:39 |
| 4 | `factor_id` | `str` | [active] | judgment.py:186,197; pool.py:387,406 |
| 5 | `island` | `str` | [active] | judgment.py:186,225,298; pool.py:390,410 |
| 6 | `island_id` | `Optional[str]` | [duplicate] | **与 `island` 语义完全重复**。coder.py:208,244 赋值 `island_id=note.island`（与 `island` 同值）。仅 cio_report_renderer.py:37 和 factor_pool_writer.py:38,69 使用（兼容层，非主路径） |
| 7 | `formula` | `str` | [active] | judgment.py:226,376,390; pool.py:390 |
| 8 | `metrics` | `BacktestMetrics` | [active] | 被 judgment.py 全面使用 |
| 9 | `passed` | `bool` | [active] | coder.py:194-200 写入; orchestrator.py:370,585; pool.py:434 |
| 10 | `status` | `Literal[...]` | [active] | judgment.py:156; coder.py:212 |
| 11 | `failure_stage` | `Optional[str]` | [active] | judgment.py:157; coder.py:213 |
| 12 | `failure_reason` | `Optional[str]` | [active] | coder.py:214 写入; 下游不直接读取但作为诊断信息保留 |
| 13 | `execution_time_seconds` | `float` | [active] | coder.py:215 写入 |
| 14 | `qlib_output_raw` | `str` | [orphan] | **coder.py:139,161,216 写入，但 Stage 5 和 pool 从未读取**。纯调试字段 |
| 15 | `error_message` | `Optional[str]` | [optional-but-critical] | **Optional 但 Stage 5 判断逻辑核心依赖**。judgment.py:69,142,163,237 多处读取，驱动 failure_mode 和 decision |
| 16 | `execution_meta` | `Optional[ExecutionMeta]` | [optional-but-critical] | **Optional 但 cio_report_renderer.py:45-49 直接 `.` 访问无 None 保护**，会在 `execution_meta=None` 时 crash |
| 17 | `factor_spec` | `Optional[FactorSpecSnapshot]` | [active] | judgment.py:376-378 有 None 保护; pool.py:390 有 None 保护; cio_report_renderer.py:38-40 **无 None 保护** |
| 18 | `artifacts` | `Optional[ArtifactRefs]` | [optional-but-critical] | **Optional 但 cio_report_renderer.py:76-82 直接 `.` 访问无 None 保护** |

### 1.3 ExecutionMeta (`src/schemas/backtest.py:6-16`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `engine` | `Literal["qlib"]` | [active] | cio_report_renderer.py:48 读取 |
| 2 | `engine_version` | `str` | [orphan] | **定义于 L8，运行时从未读取** |
| 3 | `template_version` | `str` | [active] | cio_report_renderer.py:48; coder.py:277 写入 |
| 4 | `universe` | `str` | [active] | cio_report_renderer.py:45 |
| 5 | `benchmark` | `str` | [active] | cio_report_renderer.py:46 |
| 6 | `freq` | `str` | [orphan] | **定义于 L12，运行时从未读取** |
| 7 | `start_date` | `date` | [active] | cio_report_renderer.py:47 |
| 8 | `end_date` | `date` | [active] | cio_report_renderer.py:47 |
| 9 | `runtime_seconds` | `float` | [active] | cio_report_renderer.py:49 |
| 10 | `timestamp_utc` | `datetime` | [orphan] | **定义于 L16，运行时从未读取**。coder.py:276 写入 |

### 1.4 FactorSpecSnapshot (`src/schemas/backtest.py:19-22`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `formula` | `str` | [active] | judgment.py:376; pool.py:390; factor_pool_writer.py:40; cio_report_renderer.py:38 |
| 2 | `hypothesis` | `str` | [active] | judgment.py:377; pool.py:391; factor_pool_writer.py:41; cio_report_renderer.py:39 |
| 3 | `economic_rationale` | `str` | [active] | judgment.py:378; pool.py:392; factor_pool_writer.py:42; cio_report_renderer.py:40 |

### 1.5 ArtifactRefs (`src/schemas/backtest.py:25-30`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `stdout_path` | `Optional[str]` | [active] | cio_report_renderer.py:76 读取 |
| 2 | `stderr_path` | `Optional[str]` | [active] | cio_report_renderer.py:77 读取 |
| 3 | `script_path` | `Optional[str]` | [active] | cio_report_renderer.py:78 读取 |
| 4 | `raw_result_path` | `Optional[str]` | [orphan] | **定义于 L29，coder.py 从未写入**。cio_report_renderer.py:79 有条件读取但永远为 None |
| 5 | `equity_curve_path` | `Optional[str]` | [orphan] | **定义于 L30，coder.py 从未写入**。cio_report_renderer.py:81 有条件读取但永远为 None |

### 1.6 CriticVerdict (`src/schemas/judgment.py:12-35`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `verdict_id` | `str` | [active] | pool.py:393,416; factor_pool_writer.py:44 |
| 2 | `report_id` | `str` | [active] | judgment.py:196 写入 |
| 3 | `factor_id` | `str` | [active] | judgment.py:197,345,404,413; orchestrator.py:522 |
| 4 | `note_id` | `Optional[str]` | [optional-but-critical] | **Optional 但 pool.py:389 通过 report.note_id 获取而非从 verdict 读**。judgment.py:198 写入 |
| 5 | `overall_passed` | `bool` | [active] | judgment.py:267,332-333; orchestrator.py:416,430,521,569 |
| 6 | `decision` | `Optional[str]` | [optional-but-critical] | **Optional 但下游 pool.py:395, cio_report_renderer.py:66 直接 `.upper()` 调用无 None 保护**。judgment.py:200 始终写入非 None 值 |
| 7 | `score` | `float` | [active] | pool.py:396,419; cio_report_renderer.py:67; judgment.py:405,414; factor_pool_writer.py:78 |
| 8 | `checks` | `List[ThresholdCheck]` | [active] | judgment.py:201 写入; 下游不直接迭代但结构化保留 |
| 9 | `passed_checks` | `List[str]` | [active] | judgment.py:202,182; cio_report_renderer.py:68 |
| 10 | `failed_checks` | `List[str]` | [active] | judgment.py:203,183; cio_report_renderer.py:69 |
| 11 | `failure_mode` | `Optional[str]` | [active] | judgment.py:345,404; orchestrator.py:410; pool.py:427 |
| 12 | `failure_explanation` | `Optional[str]` | [orphan] | **judgment.py:206 写入，但下游从未读取**。summary 字段已涵盖此信息 |
| 13 | `suggested_fix` | `Optional[str]` | [orphan] | **judgment.py:207 写入，但下游从未读取** |
| 14 | `summary` | `str` | [active] | judgment.py:208,191-192; cio_report_renderer.py:71 |
| 15 | `reason_codes` | `List[str]` | [active] | judgment.py:209,414; pool.py:428; factor_pool_writer.py:74; cio_report_renderer.py:70 |
| 16 | `register_to_pool` | `bool` | [active] | orchestrator.py:416; judgment.py:210 |
| 17 | `pool_tags` | `List[str]` | [active] | judgment.py:211; pool.py:404 |

### 1.7 FactorPoolRecord (`src/schemas/factor_pool.py:6-22`)

| # | 字段 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | `factor_id` | `str` | [active] | pool.py:387,406; factor_pool_writer.py:38 |
| 2 | `note_id` | `str` | [active] | pool.py:389,413; factor_pool_writer.py:39 |
| 3 | `formula` | `str` | [active] | pool.py:390,408,414,509 |
| 4 | `hypothesis` | `str` | [active] | pool.py:391,415,507 |
| 5 | `economic_rationale` | `str` | [active] | pool.py:392,416,508 |
| 6 | `backtest_report_id` | `str` | [active] | pool.py:393,415 |
| 7 | `verdict_id` | `str` | [active] | pool.py:394,417 |
| 8 | `decision` | `str` | [active] | pool.py:395,418,519,530 |
| 9 | `score` | `float` | [active] | pool.py:396,419,521 |
| 10 | `sharpe` | `Optional[float]` | [optional-but-critical] | **Optional 但 pool.py:521 使用 `record.sharpe or 0.0` 做 fallback**，下游排序和筛选依赖此字段 |
| 11 | `ic_mean` | `Optional[float]` | [optional-but-critical] | 同上，pool.py:522 |
| 12 | `icir` | `Optional[float]` | [optional-but-critical] | 同上，pool.py:523 |
| 13 | `turnover` | `Optional[float]` | [optional-but-critical] | 同上，pool.py:524 |
| 14 | `max_drawdown` | `Optional[float]` | [optional-but-critical] | 同上，pool.py:525 |
| 15 | `coverage` | `Optional[float]` | [optional-but-critical] | 同上，pool.py:526 |
| 16 | `tags` | `List[str]` | [active] | pool.py:404,528 |

**注意**: `FactorPoolRecord` 的 `created_at` 字段继承自 `PixiuBase`（`src/schemas/__init__.py:8`），schema 文件中未显式定义。pool.py:403 和 factor_pool_writer.py:53 显式赋值 `created_at=datetime.utcnow()`，pool.py:527 读取 `record.created_at.isoformat()`。

---

## 2. 跨 Stage 合约检查

### 2.1 Stage 4 (coder.py) 写入 BacktestReport 的字段

**成功路径** (`coder.py:202-221`, `_parse_result`):

写入全部字段：`report_id`, `run_id`, `note_id`, `factor_id`, `island`, `island_id`, `formula`, `metrics`(完整), `passed`, `status`, `failure_stage`, `failure_reason`, `execution_time_seconds`, `qlib_output_raw`, `error_message`, `execution_meta`, `factor_spec`, `artifacts`

**失败路径** (`coder.py:237-267`, `_failure_report`):

同样写入全部字段，`metrics` 全部置零，`passed=False`, `status="failed"`。

**Orchestrator 异常捕获路径** (`orchestrator.py:346-363`):

缺少 `run_id`, `island_id`, `execution_meta`, `factor_spec`, `artifacts` -- 这些字段为 Optional 所以不 crash，但导致下游兼容层 (`cio_report_renderer.py`) 会 NullPointer。

### 2.2 Stage 5 (judgment.py) 从 BacktestReport 读取的字段

| 消费者 | 读取的 BacktestReport 字段 |
|--------|---------------------------|
| `_build_threshold_checks` (L24-65) | `metrics.sharpe`, `metrics.ic_mean`, `metrics.icir`, `metrics.turnover`, `metrics.turnover_rate`, `metrics.max_drawdown`, `metrics.coverage` |
| `_diagnose_failure` (L68-111) | `error_message` |
| `_score_report` (L126-138) | `metrics.sharpe`, `metrics.ic_mean`, `metrics.icir`, `metrics.turnover`, `metrics.turnover_rate`, `metrics.max_drawdown`, `metrics.coverage` |
| `_build_reason_codes` (L141-159) | `error_message`, `status`, `failure_stage` |
| `_decide` (L162-169) | `status`, `error_message` |
| `Critic.evaluate` (L175-212) | `report_id`, `factor_id`, `note_id`, `island` |
| `RiskAuditor.audit` (L221-256) | `factor_id`, `island`, `formula`, `error_message`, `metrics.turnover_rate` |
| `PortfolioManager.rebalance` (L265-309) | `factor_id`, `island`, `metrics.sharpe`, `metrics.ic_mean` |
| `ReportWriter.generate_cio_report` (L315-364) | `factor_id`, `metrics.sharpe`, `factor_spec.formula`, `factor_spec.hypothesis`, `factor_spec.economic_rationale` |
| `ReportWriter._render_markdown` (L366-417) | 同上 + `formula` (fallback) |

### 2.3 Factor Pool (pool.py) 从 BacktestReport + CriticVerdict 读取的字段写入 FactorPoolRecord

**`register_factor`** (`pool.py:376-444`):

| 从 BacktestReport 读 | 从 CriticVerdict 读 | 写入 FactorPoolRecord / metadata |
|---|---|---|
| `factor_id` | `verdict_id` | `factor_id`, `verdict_id` |
| `note_id` | `decision` | `note_id`, `decision` |
| `report_id` | `score` | `backtest_report_id`, `score` |
| `island` | `overall_passed` | `island` (metadata) |
| `formula` | `failure_mode` | `formula` |
| `factor_spec.formula` | `reason_codes` | `formula` (优先 factor_spec) |
| `factor_spec.hypothesis` | `pool_tags` | `hypothesis`, `tags` |
| `factor_spec.economic_rationale` | | `economic_rationale` |
| `metrics.sharpe` | | `sharpe` |
| `metrics.ic_mean` | | `ic_mean` |
| `metrics.icir` | | `icir` |
| `metrics.turnover` / `turnover_rate` | | `turnover` |
| `metrics.max_drawdown` | | `max_drawdown` |
| `metrics.coverage` | | `coverage` |
| `passed` | | `parse_success` (metadata, 向后兼容) |

### 2.4 合约断裂分析

#### "写了但没人读"

| 字段 | 写入位置 | 说明 |
|------|---------|------|
| `BacktestMetrics.ic_std` | coder.py:187 | Stage 5 和 pool 均不使用，ICIR 已由 qlib 直接输出 |
| `BacktestMetrics.win_rate` | 从未写入 | schema 定义了但 coder 也没赋值 |
| `BacktestMetrics.long_short_spread` | 从未写入 | 同上 |
| `BacktestReport.run_id` | coder.py:50,125 | 下游无消费者 |
| `BacktestReport.qlib_output_raw` | coder.py:139,161,216 | 纯调试字段，下游不读 |
| `ExecutionMeta.engine_version` | 未写入（使用默认值 "unknown"） | 下游不读 |
| `ExecutionMeta.freq` | 未写入（使用默认值 "day"） | 下游不读 |
| `ExecutionMeta.timestamp_utc` | coder.py:276 | 下游不读 |
| `ArtifactRefs.raw_result_path` | 未写入 | cio_report_renderer.py:79 有条件读但永远 None |
| `ArtifactRefs.equity_curve_path` | 未写入 | 同上 |
| `CriticVerdict.failure_explanation` | judgment.py:206 | summary 已涵盖，下游不读 |
| `CriticVerdict.suggested_fix` | judgment.py:207 | 下游不读 |

#### "想读但没人写"（潜在运行时断裂）

| 消费者 | 期望字段 | 风险 |
|--------|---------|------|
| `cio_report_renderer.py:45-49` | `report.execution_meta.universe` 等 | **直接 `.` 访问**，orchestrator 异常路径不写 `execution_meta`，会 AttributeError |
| `cio_report_renderer.py:38-40` | `report.factor_spec.formula` 等 | **直接 `.` 访问**，orchestrator 异常路径不写 `factor_spec`，会 AttributeError |
| `cio_report_renderer.py:76-78` | `report.artifacts.stdout_path` 等 | **直接 `.` 访问**，orchestrator 异常路径不写 `artifacts`，会 AttributeError |
| `cio_report_renderer.py:66` | `verdict.decision.upper()` | **直接 `.upper()` 调用**，`decision` 为 Optional，若为 None 会 AttributeError |

---

## 3. 双轨体系（v1 vs v2 schema）

项目存在两套并行的 schema 体系：

| 层面 | v1（legacy） | v2（canonical） |
|------|-------------|----------------|
| BacktestMetrics | `src/agents/schemas.py:34-51` (字段: `ic`, `turnover`, `win_rate`, `parse_success`, `raw_log_tail`) | `src/schemas/backtest.py:33-45` (字段: `ic_mean`, `turnover_rate`, `turnover`, `coverage`, `long_short_spread`) |
| Critic | `src/agents/critic.py` (兼容 shim) | `src/agents/judgment.py` (canonical) |
| FactorPool 写入 | `pool.register()` 使用 `FactorHypothesis` + legacy `BacktestMetrics` | `pool.register_factor()` 使用 v2 `BacktestReport` + `CriticVerdict` |
| FactorPoolRecord 写入 | N/A | `pool.register_factor()` + `pool.register_factor_v2()` (两个入口!) |

**关键问题**: `pool.register_factor()` (pool.py:376-444) 的 metadata dict 包含 **重复 key**:
- `"sharpe"` 出现两次 (L419 和 L436)
- `"icir"` 出现两次 (L421 和 L436)
- `"turnover"` 出现三次 (L423, L424, L437)

Python dict 后写覆盖前写，这意味着 L419-L425 的值会被 L434-L437 的"向后兼容"值覆盖。目前恰好值相同不会出错，但这是隐性 bug。

---

## 4. 收口建议

### P0 -- 运行时断裂风险（会 crash）

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| P0-1 | `cio_report_renderer.py` 直接访问 `report.execution_meta.*`, `report.factor_spec.*`, `report.artifacts.*` 无 None 保护 | cio_report_renderer.py:37-82 | 添加 None guard 或将 `execution_meta`, `factor_spec`, `artifacts` 从 Optional 改为 required（推荐后者，因为 coder.py 主路径和失败路径均写入） |
| P0-2 | `cio_report_renderer.py:66` 调用 `verdict.decision.upper()`, `decision` 为 `Optional[str]` | cio_report_renderer.py:66 | `CriticVerdict.decision` 应从 `Optional[str]` 改为 `str`（judgment.py 始终写入非 None 值） |
| P0-3 | `pool.register_factor()` metadata dict 有重复 key（sharpe, icir, turnover 各出现两次） | pool.py:409-438 | 删除 L433-L437 的"向后兼容"重复行，或合并为单一 metadata 构建 |

### P1 -- 语义重复字段，应合并

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| P1-1 | `BacktestMetrics.turnover` vs `turnover_rate` 双轨 | backtest.py:41-42 | **删除 `turnover`，统一用 `turnover_rate`**。理由：(1) `turnover_rate` 是 required 字段，`turnover` 是 Optional；(2) coder.py:189-190 给两者赋相同值；(3) judgment.py 已有 fallback 逻辑，说明共识是 `turnover_rate` 为主 |
| P1-2 | `BacktestMetrics.annual_return` vs `annualized_return` 双轨 | backtest.py:35-36 | **删除 `annual_return`**。理由：coder.py:184 赋值为 `raw.get("annualized_return")` 即同源；仅 cio_report_renderer.py:56（兼容层）读取 |
| P1-3 | `BacktestReport.island_id` vs `island` 双轨 | backtest.py:53-54 | **删除 `island_id`**。理由：coder.py:208,244 赋值 `island_id=note.island`（与 `island` 同值）；仅兼容层（cio_report_renderer.py:37, factor_pool_writer.py:38,69）使用 |
| P1-4 | `CriticThresholds.max_turnover` vs `max_turnover_rate` | thresholds.py:9 | **删除 `max_turnover`**（L9 注释说是"兼容旧 critic / 测试命名"，judgment.py 只用 `max_turnover_rate`） |

### P2 -- Orphan 字段，建议删除

| # | 字段 | 位置 | 建议 |
|---|------|------|------|
| P2-1 | `BacktestMetrics.ic_std` | backtest.py:39 | 删除。ICIR 由 qlib 直接算出，`ic_std` 从未被消费 |
| P2-2 | `BacktestMetrics.win_rate` | backtest.py:44 | 删除。coder.py 未写入，Stage 5 不读 |
| P2-3 | `BacktestMetrics.long_short_spread` | backtest.py:45 | 删除。从未读写 |
| P2-4 | `BacktestReport.run_id` | backtest.py:50 | 保留但考虑改为 required（用于未来审计追踪）。当前下游无消费者 |
| P2-5 | `BacktestReport.qlib_output_raw` | backtest.py:66 | 保留为调试字段，但考虑移入 `ArtifactRefs`（语义更准确） |
| P2-6 | `ExecutionMeta.engine_version` | backtest.py:8 | 删除或实际写入 qlib 版本 |
| P2-7 | `ExecutionMeta.freq` | backtest.py:12 | 删除。coder.py 不写入，下游不读 |
| P2-8 | `ExecutionMeta.timestamp_utc` | backtest.py:16 | 删除。`PixiuBase.created_at` 已提供时间戳 |
| P2-9 | `ArtifactRefs.raw_result_path` | backtest.py:29 | 保留预留位，但标注为 future |
| P2-10 | `ArtifactRefs.equity_curve_path` | backtest.py:30 | 同上 |
| P2-11 | `CriticVerdict.failure_explanation` | judgment.py:28 | 删除。`summary` 已涵盖 |
| P2-12 | `CriticVerdict.suggested_fix` | judgment.py:29 | 删除。下游不读 |

### P2 -- Optional 应改为 Required

| # | 字段 | 位置 | 建议 |
|---|------|------|------|
| P2-13 | `BacktestMetrics.coverage` | backtest.py:43 | 改为 required (`float`)，默认值 1.0。judgment.py:27 已做 fallback 处理说明 None 不是有效语义 |
| P2-14 | `BacktestReport.error_message` | backtest.py:67 | 保持 Optional（None 表示无错误，有明确语义） |
| P2-15 | `CriticVerdict.decision` | judgment.py:18 | 改为 `str`（非 Optional）。judgment.py 始终写入非 None 值 |
| P2-16 | `CriticVerdict.note_id` | judgment.py:16 | 改为 `str`（非 Optional）。judgment.py:198 始终从 report.note_id 写入 |
| P2-17 | `FactorPoolRecord.sharpe` 等 6 个指标字段 | factor_pool.py:16-21 | 改为 required (`float`)，默认 0.0。pool.py 调用方始终提供值，`or 0.0` fallback 说明 None 不是有效语义 |

---

## 5. 风险总结

| 风险等级 | 数量 | 说明 |
|---------|------|------|
| P0 (会 crash) | 3 | cio_report_renderer 无 None 保护; pool metadata 重复 key |
| P1 (语义混乱) | 4 | turnover/turnover_rate, annual_return/annualized_return, island/island_id, max_turnover/max_turnover_rate |
| P2 (tech debt) | 17 | orphan 字段 12 个, Optional 应改 required 5 个 |

总计 **24 个待修复项**。建议按 P0 -> P1 -> P2 顺序逐步收口。P0 问题影响运行时稳定性，应在下一个 commit 中修复。P1 语义重复会随代码演进持续产生混乱，建议在一个专项 PR 中统一清理。P2 可分散在日常开发中逐步消除。
