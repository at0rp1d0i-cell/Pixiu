Status: active
Owner: codex

# 2026-03-24 A-Share Validation Protocol V1 Implementation

## Scope

本轮进入 `validation protocol v1` 的第一刀 runtime 语义切换。

目标：

- 保持已有 schema 脚手架不回退
- 把 `IS pass -> candidate` 变成当前默认 runtime 语义
- 只让显式 `oos_passed=True` 的对象进入 `promote`
- 保持 `FactorPool / Portfolio / Report` 兼容新决策层级

## Validation Mode

- `Mode`: fast feedback
- `Command`: `uv run pytest -q tests/test_schemas.py tests/test_stage5.py tests/test_factor_pool.py`
- `Profile`: N/A
- `Proof`:
  - `candidate` 默认路径通过
  - `oos_passed=True -> promote` 路径通过
  - `FactorPool` 不把 candidate 误记为 passed

## Task 1

### Task

把 `Critic` 默认通过语义改成 `candidate-first`。

### Files

- `src/agents/judgment/_scoring.py`
- `src/agents/judgment/critic.py`
- `tests/test_stage5.py`

### Notes

- 无 OOS 的 deterministic pass 先变 `candidate`
- `oos_passed=True` 时才允许 `promote`

## Task 2

### Task

保持 `FactorPool / ReportWriter / Portfolio` 对新决策层级兼容。

### Files

- `src/agents/judgment/report_writer.py`
- `src/factor_pool/factor_writer.py`
- `tests/test_stage5.py`
- `tests/test_factor_pool.py`

### Notes

- `promote` 仍代表正式批准
- `candidate` 可以入池，但不能进入 passed query / portfolio

## Task 3

### Task

补兼容性测试，证明新语义不会打断当前主链。

### Files

- `tests/test_schemas.py`
- `tests/test_stage5.py`
- `tests/test_factor_pool.py`

### Notes

- 同时覆盖 `candidate` 和 `promote` 两条路径
- 不在本轮引入 walk-forward runtime

## Explicit Non-Goals

- 不修改 `src/agents/judgment/portfolio_manager.py`
- 不引入 walk-forward runtime
- 不实现 OOS metrics 真实生成
- 不实现 `Stage 4` 自动填充 discovery/OOS 窗口

## Exit Criteria

满足以下条件，本轮结束：

- `candidate-first` 已成为默认 runtime 行为
- `oos_passed=True -> promote` 路径保留
- `candidate` 不会混入正式 passed factors
- 主线程 review 通过后再进入下一轮 `OOSReport / walk-forward` 实现

## Next Slice

下一刀只做 `Stage 4` 的最小真实 OOS 路径。

### Chosen Contract

- `BacktestReport.metrics` 在存在 validation split 时表示 `discovery` 指标
- 新增 `metrics_scope="discovery"` 以避免语义含糊
- 新增 `oos_metrics` 承载 holdout 指标
- 新增 `oos_degradation` 作为 discovery vs OOS 的最小退化信号
- `oos_passed` 由 `Stage 4` 真实计算，不再手工注入

### Minimal Runtime Rule

- 若回测区间足够长，则使用 `最后 12 个月` 作为 OOS
- 其余较早窗口作为 discovery
- 若区间不足以安全切分，则保留 `oos_window=None`、`oos_passed=None`
- 阈值资格判断统一由 `Coder` 依据 canonical `THRESHOLDS` 计算；模板只产出 metrics 和 split 事实

### Validation Mode

- `Mode`: fast feedback
- `Command`: `uv run pytest -q tests/test_stage4.py tests/test_stage5.py -k "oos or validation or coder"`
- `Proof`:
  - `Coder` 能解析 discovery/OOS 输出
  - `BacktestReport` 带真实 `oos_passed`
  - `Critic` 在真实 `Coder` 输出上走 `candidate/promote` 分流
