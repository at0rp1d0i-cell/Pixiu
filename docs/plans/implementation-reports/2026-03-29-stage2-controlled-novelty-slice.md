# Implementation Report: controlled-run Stage 2 novelty slice

## Consumed Sprint Contract

docs/plans/sprint-contracts/2026-03-29-stage2-controlled-novelty-slice.md

## Generator Summary

Reduced controlled-run novelty churn by prefiltering symbolic-mutation candidates against existing pool formulas and same-batch duplicates before note creation, then validated the change on a fresh controlled-run single-round artifact.

## Files Touched

- `src/agents/researcher.py`
- `tests/test_stage2.py`

## Tests Run

- `uv run pytest -q tests/test_stage2.py -k "symbolic_mutation_prefilters_candidates_against_existing_factor_pool or symbolic_mutation_prefilters_same_batch_near_duplicates or alpha_researcher_symbolic_path_runs_local_prescreen"`
- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`

## Follow-Ups

- The next Stage 2 slice should target the remaining novelty-heavy subspaces after this cut, especially `factor_algebra`, `narrative_mining`, and `cross_market`.
- Controlled-run still has `approved_count = 0`; after novelty waste falls further, the next bottleneck remains downstream alignment/value-density rather than retry churn.

## What changed

- [src/agents/researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py)
  - Added `_filter_symbolic_mutation_candidates()` to drop symbolic mutations that are already near-duplicates of existing factor-pool formulas before note creation.
  - Added same-batch duplicate suppression for symbolic-mutation candidates so one repeated formula does not fan out into multiple near-identical notes.
  - Short-circuits the symbolic path when all candidates are removed by this novelty prefilter and records the outcome in logs.

- [tests/test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py)
  - Added coverage for filtering symbolic mutations against existing pool formulas.
  - Added coverage for same-batch symbolic duplicate suppression.

## Why

- The fresh controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260329_224455/round_000.json) showed Stage 2 novelty as the dominant waste: `novelty = 16`, with `symbolic_mutation = 9` as the largest subspace contributor.
- The smallest bounded fix was to cut duplicate churn before symbolic mutations even become notes, instead of widening Stage 3/5 logic or changing experiment profiles.
- This keeps the change inside Stage 2 local generation and does not touch Stage 1, schema contracts, validation thresholds, or profile settings.

## Verification

- `uv run pytest -q tests/test_stage2.py -k "symbolic_mutation_prefilters_candidates_against_existing_factor_pool or symbolic_mutation_prefilters_same_batch_near_duplicates or alpha_researcher_symbolic_path_runs_local_prescreen"`
  - Result: `3 passed, 98 deselected in 11.85s`

- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`
  - Result: completed successfully and wrote [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114038/round_000.json)
  - Controlled-run comparison against the previous baseline [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260329_224455/round_000.json):
    - `generated_count: 18 -> 14`
    - `novelty: 16 -> 11`
    - `symbolic_mutation novelty: 9 -> 3`
    - `alignment: 2 -> 1`
    - `local_retry_count: 0 -> 2`
    - `validator: 0 -> 2`
  - Interpretation:
    - This slice materially reduced novelty waste, especially in `symbolic_mutation`.
    - It did not close Stage 2 by itself; controlled-run still generates no approved candidates and still carries residual novelty/alignment/validator waste in other subspaces.
    - The new residuals are concentrated in `factor_algebra`, `narrative_mining`, and validator failures rather than duplicate symbolic mutations.

## Open items

- `local_retry_count` rose from `0` to `2` in the fresh controlled-run artifact, so retry churn is not uniformly solved across all subspaces.
- `approved_count` remains `0`, so the next slice should continue on novelty/alignment in the remaining subspaces before revisiting downstream value-density.
