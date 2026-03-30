# QA Report

## Consumed Sprint Contract

[2026-03-29-stage2-controlled-novelty-slice.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/sprint-contracts/2026-03-29-stage2-controlled-novelty-slice.md)

## Consumed Implementation Report

[2026-03-29-stage2-controlled-novelty-slice.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md)

QA validates the bounded novelty-slice claims against the current worktree verification output and runtime artifact evidence.

## Environment

- `uv`
- `HOME=/tmp/pixiu-home`
- `UV_CACHE_DIR=/tmp/pixiu-uv-cache`
- `QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin`
- `PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run`
- `PIXIU_LLM_DEFAULT_PROVIDER=openai`

## Scenarios Tested

- Targeted Stage 2 pytest coverage for symbolic-mutation novelty prefiltering
- Controlled-run `single` execution on `momentum`
- Baseline-vs-current artifact comparison:
  - baseline [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260329_224455/round_000.json)
  - current [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114038/round_000.json)

## Evidence Summary

- Targeted tests passed: `3 passed, 98 deselected`
- Controlled-run finished successfully and emitted a fresh artifact
- Stage 2 artifact delta supports the bounded claim:
  - `generated_count: 18 -> 14`
  - `stage2.rejection_counts_by_filter.novelty: 16 -> 11`
  - `stage2.rejection_counts_by_filter_and_subspace.novelty.symbolic_mutation: 9 -> 3`
- The slice does not support a stronger claim than that:
  - `approved_notes_count` remains `0`
  - `local_retry_count: 0 -> 2`
  - validator rejections appear in `symbolic_mutation` and `narrative_mining`

## Issues Found

- none blocking for the bounded slice

## Verification Status

passed
