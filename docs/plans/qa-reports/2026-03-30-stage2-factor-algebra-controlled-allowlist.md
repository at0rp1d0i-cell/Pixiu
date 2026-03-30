# QA Report

## Consumed Sprint Contract

[2026-03-30-stage2-factor-algebra-controlled-allowlist.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/sprint-contracts/2026-03-30-stage2-factor-algebra-controlled-allowlist.md)

## Consumed Implementation Report

[2026-03-30-stage2-factor-algebra-controlled-allowlist.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md)

QA validates the bounded controlled-run allowlist claims against targeted tests and the fresh controlled-run artifact.

## Environment

- `uv`
- `HOME=/tmp/pixiu-home`
- `UV_CACHE_DIR=/tmp/pixiu-uv-cache`
- `QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin`
- `PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run`
- `PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1`
- `PIXIU_LLM_DEFAULT_PROVIDER=openai`

## Scenarios Tested

- Controlled-run policy rejection for `ratio_momentum`
- Controlled-run policy rejection for `volume_confirmation`
- Controlled-run prompt-focus injection
- Controlled-run single-note stop-loss regression
- Fast-feedback compatibility regression
- Controlled-run `single` execution on `momentum`

## Evidence Summary

- Targeted tests passed:
  - `3 passed, 101 deselected`
  - `5 passed, 99 deselected`
- Controlled-run completed and emitted [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_140354/round_000.json)
- The bounded claim is supported:
  - `factor_algebra novelty: 1 -> 0`
  - `factor_algebra` sample rejections no longer center on `ratio_momentum` or `volume_confirmation`
  - the new factor-algebra residual is `mean_spread cannot claim return delta or acceleration`
- The slice does not support a stronger claim than that:
  - `approved_notes_count` remains `0`
  - `alignment: 3 -> 4`
  - `local_retry_count: 1 -> 2`

## Issues Found

- none blocking for the bounded slice

## Verification Status

passed
