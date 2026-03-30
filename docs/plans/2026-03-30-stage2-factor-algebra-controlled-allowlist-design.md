**Date:** 2026-03-30
**Status:** Approved for implementation

# Stage 2 Controlled-Run Factor Algebra Allowlist Design

## Goal

把 `controlled_run + factor_algebra + single-note` 的 family steering 从“逐个暂停 blocker family”收敛成一个更明确的临时 allowlist：当前只允许 `mean_spread`。

目标不是永久收缩 `factor_algebra` 表达面，而是在受控单注模式下先把当前最不稳定的 family surface 切掉，争取尽快得到非零的 Stage 2 漏斗。

## Why Now

上一刀 [20260330_125645/round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_125645/round_000.json) 已经把 `ratio_momentum` 从当前 blocker 位置挪开，但新 blocker 立即变成了 `volume_confirmation` alignment：

- `factor_algebra novelty: 3 -> 1`
- `factor_algebra alignment: 1 -> 3`
- sample rejections 反复命中 `factor_algebra|volume_confirmation|$close|$volume|mul|rank`

这说明当前 single-note controlled-run 的问题不是某一个孤立 family，而是整个非 `mean_spread` surface 还不够稳定。

## Alternatives

### Option 1: 再暂停 `volume_confirmation`

优点：

- 改动最小

缺点：

- 继续走 blacklist/打补丁路径
- 下一轮很可能再撞到 `volatility_state`

### Option 2: 对齐到 controlled single-note allowlist

做法：

- 在 `controlled_run + factor_algebra + single-note` 下，仅允许 `mean_spread`
- 其他 family 一律在本地预筛记为 `value_density`
- prompt 同步改成 allowlist 口径

优点：

- 比 blacklist 更稳定
- 与当前 fast-feedback 已验证过的 family surface 一致
- 仍然是有界 profile concession，不碰 schema 和 Stage 3

缺点：

- 受控单注模式的 research surface 更窄

### Option 3: 放宽 retry，让对齐失败后再试一次

优点：

- 保留更多 family surface

缺点：

- 会重新扩大 LLM 消耗
- 当前主线已经把 single-note full rejection stop-loss 收紧，不适合这轮反向放宽

## Chosen Now

选择 **Option 2**。

也就是：

> `controlled_run + factor_algebra + single-note` 当前只允许 `mean_spread`，把这条明确写进 prompt 和本地 policy rejection。

## Concession Check

Concession check: `experiment_concession`，需要更新 [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)。

理由：

- 这是 profile-specific temporary allowlist
- 它只服务于当前受控单注闭环
- 不代表正式 Stage 2 research surface 已经收缩

## Success Criteria

- fresh controlled-run artifact 中 `factor_algebra alignment` 不再主要由 `volume_confirmation` 驱动
- `factor_algebra` 的 sample rejections 不再主要命中 `ratio_momentum` 或 `volume_confirmation`
- 若 `approved_notes_count` 仍为 `0`，至少 residual 要明确转移到 `narrative/cross_market` 或更下游层面
