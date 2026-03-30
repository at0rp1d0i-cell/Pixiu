# QA Report

## Consumed Sprint Contract

[2026-03-30-stage2-factor-algebra-controlled-family-steering.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/sprint-contracts/2026-03-30-stage2-factor-algebra-controlled-family-steering.md)

## Consumed Implementation Report

[2026-03-30-stage2-factor-algebra-controlled-family-steering.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md)

QA validates the bounded controlled-run family-steering claims against the worktree verification output and the fresh controlled-run artifact.

## Environment

- `uv`
- `HOME=/tmp/pixiu-home`
- `UV_CACHE_DIR=/tmp/pixiu-uv-cache`
- `QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin`
- `PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run`
- `PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1`
- `PIXIU_LLM_DEFAULT_PROVIDER=openai`

## Scenarios Tested

- Controlled-run policy rejection unit test for paused `ratio_momentum`
- Controlled-run prompt-focus injection unit test
- Existing single-note stop-loss regression
- Fast-feedback compatibility regression for ratio-momentum family steering
- Controlled-run `single` execution on `momentum`

## Evidence Summary

- Targeted tests passed:
  - `3 passed, 100 deselected`
  - `4 passed, 99 deselected`
- Controlled-run finished successfully and emitted a fresh artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_125645/round_000.json)
- The bounded claim is supported:
  - `generated_count: 15 -> 13`
  - `local_retry_count: 3 -> 1`
  - `stage2.rejection_counts_by_filter.novelty: 11 -> 9`
  - `stage2.rejection_counts_by_filter.validator: 3 -> 1`
  - `stage2.rejection_counts_by_filter_and_subspace.novelty.factor_algebra: 3 -> 1`
- The slice does not support a stronger claim than that:
  - `approved_notes_count` remains `0`
  - `factor_algebra alignment: 1 -> 3`
  - the real blocker moved to `factor_algebra|volume_confirmation|...` alignment

## Issues Found

- none blocking for the bounded slice

## Verification Status

passed
