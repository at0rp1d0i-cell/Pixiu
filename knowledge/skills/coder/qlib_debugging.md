# Qlib Backtest Debugging Guide

## Common Errors

### 1. Formula Syntax Errors
- Unmatched parentheses: check bracket counts
- Unknown operators: only use operators in the approved whitelist
- Invalid field references: only `$close`, `$open`, `$high`, `$low`, `$volume`, `$factor`, `$amount`, `$vwap` are always available

### 2. Data Issues
- `KeyError` on field: the field is not available in the dataset
- `NaN` in output: formula produces undefined values (e.g., division by zero, Log(0))
- Empty result: universe filter is too restrictive or date range has no data

### 3. Runtime Errors
- `Ref($field, -N)`: negative offset = future data leak, use positive offsets only
- `Log(x)` without protection: always use `Log(x + 1)` or `Log(Abs(x) + 1)`
- Division by zero: use `Div(a, Max(b, 1e-8))` pattern

### 4. Performance Issues
- Very long window (>60 days) on daily data: consider if the economic logic supports it
- Nested operators deeper than 5 levels: simplify the expression
- Multiple correlated factors: check NoveltyFilter for redundancy

## Backtest Result Interpretation
- `sharpe < 0`: factor direction may be inverted, try negating
- `ic_mean ~ 0`: no predictive power, rethink the mechanism
- `turnover > 50%`: signal is too noisy, add smoothing (Mean/EMA)
- `max_drawdown > 30%`: factor is regime-dependent, declare applicable_regimes
