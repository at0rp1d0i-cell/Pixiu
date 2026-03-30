**Date:** 2026-03-30
**Status:** Approved for implementation

# Stage 2 Controlled-Run Factor Algebra Family Steering Design

## Goal

在 `controlled_run` 的 `factor_algebra` 单注模式里，先把当前最稳定的坏家族挡掉，减少 `ratio_momentum` 这类已知重复/低价值 family 持续占用 Stage 2 配额。

这刀不是做通用 Stage 2 生成重构，而是做一个有界的 `family steering` slice，目标是尽快把 `controlled single` 从稳定卡死的 `factor_algebra novelty/alignment` 残差里拉出来。

## Why Now

截至 `2026-03-30`，`symbolic_mutation` novelty slice 已经落地，最新 controlled-run artifacts：

- [20260329_224455/round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260329_224455/round_000.json)
- [20260330_113329/round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_113329/round_000.json)
- [20260330_114204/round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114204/round_000.json)

显示出一个稳定残差：

- `factor_algebra novelty = 3`
- `factor_algebra alignment = 1`
- rejection sample 持续命中 `factor_algebra|ratio_momentum|...`
- 同类样本同时出现：
  - 与历史因子重复
  - `ratio_momentum should not be described as a mean spread`

所以当前最小下一刀不是修 Stage 3，也不是先扩 `narrative/cross_market`，而是把 `factor_algebra` 的 family steering 从 `fast_feedback` 外推到 `controlled_run`。

## Alternatives

### Option 1: 扩大 legacy family 识别

做法：

- 增强历史公式反推 family/gene 的能力
- 让 anti-collapse / value-density 更早识别老公式语义

优点：

- 更正式
- 长期更通用

缺点：

- 当前 slice 太重
- 需要扩展多个 legacy 公式模式，验证面会迅速膨胀

### Option 2: controlled-run 单注模式下暂停当前主 blocker family

做法：

- 复用现有 `fast_feedback` family steering 机制
- 在 `controlled_run + factor_algebra + requested_note_count=1` 下，对当前稳定主 blocker 的 `ratio_momentum` 做 profile-level pause
- 同时给 prompt 一个明确 focus section，而不是只靠 anti-collapse 提示

优点：

- 最小改动
- 直接命中当前最稳定的 residual
- 与当前主线 Phase 3 目标一致：把 family steering 外推到 controlled run

缺点：

- 这是 experiment concession，不是最终生成架构
- 只解决当前 blocker，不解决所有 family 识别问题

### Option 3: 先转去修 narrative/cross_market

优点：

- 能碰到 validator 残差

缺点：

- 当前 residual 在 rerun 间波动更大
- 不是最稳定的主 blocker

## Chosen Now

选择 **Option 2**。

也就是：

> 在 `controlled_run` 的 `factor_algebra` 单注模式里，临时暂停 `ratio_momentum` family，并给 prompt 加上更明确的 controlled-run family focus。

## Scope

In scope:

- `src/agents/researcher.py`
- `tests/test_stage2.py`
- `docs/overview/06_runtime-concessions.md`

Out of scope:

- `narrative_mining` / `cross_market`
- 通用 legacy family reverse parser
- Stage 3 规则
- Stage 4/5 阈值
- schema 变更

## Behavior

### Rule 1: Controlled-run single-note family pause

当满足下面条件时：

- `PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run`
- `subspace_hint == factor_algebra`
- `PIXIU_STAGE2_REQUESTED_NOTE_COUNT == 1`

若生成结果命中 `transform_family=ratio_momentum`，则本地预筛直接记为：

- `value_density`

原因文案要明确表明：

- `controlled_run` 当前暂停 `ratio_momentum`
- 这是因为它是当前 single-note residual blocker

### Rule 2: Controlled-run focus section

在第一次生成 prompt 就加入一个明确的 controlled-run focus section：

- 当前 single-note controlled-run 优先 `mean_spread`
- 暂停 `ratio_momentum`
- 不要把 `ratio_momentum` 的相对强弱叙事写成 `mean_spread`

它的目标不是完全替代 anti-collapse，而是把 profile-level steering 从 soft hint 变成明确约束。

## Concession Check

Concession check: `experiment_concession`，需要更新 [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)。

理由：

- 这是 profile-specific temporary family pause
- 它是为了受控实验闭环而接受的运行时让步
- 不是最终的通用 Stage 2 生成设计

## Testing

### Validation Mode

- `controlled_run`

### Commands

```bash
uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_ratio_momentum or controlled_run_single_note_full_rejection_skips_retry"
env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum
```

### Proof Artifact

- `data/experiment_runs/{run_id}/round_000.json`

成功标准：

- `factor_algebra` 不再把 `ratio_momentum` 作为当前 single-note 主 blocker
- `factor_algebra` 的 `novelty/alignment` residual 至少有一项下降
- 若 `approved_notes_count` 仍为 `0`，也必须明确看到 residual 从 `ratio_momentum` 转移
