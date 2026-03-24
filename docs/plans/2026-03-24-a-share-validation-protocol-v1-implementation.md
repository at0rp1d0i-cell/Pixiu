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
