# Implementation Report: controlled-run Stage 2 factor_algebra family steering

## Consumed Sprint Contract

docs/plans/sprint-contracts/2026-03-30-stage2-factor-algebra-controlled-family-steering.md

## Generator Summary

Extended the existing factor-algebra profile steering pattern into `controlled_run + single-note` so the current blocker family `ratio_momentum` is paused locally before it keeps burning controlled Stage 2 budget, then validated the effect on a fresh controlled-run single artifact.

## Files Touched

- `src/agents/researcher.py`
- `tests/test_stage2.py`
- `docs/overview/06_runtime-concessions.md`

## Tests Run

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_fast_feedback_rejects_disallowed_ratio_momentum_family or factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`

## Follow-Ups

- The next bounded Stage 2 slice should target `factor_algebra` alignment on `volume_confirmation`, because the current blocker moved there immediately after `ratio_momentum` was paused.
- `narrative_mining` and `cross_market` novelty residuals still exist, but they are no longer the sharpest next blocker inside `factor_algebra`.
- Self-evolve smoke is still blocked for now because `approved_notes_count` remains `0` on the fresh controlled-run artifact.

## What changed

- [researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py)
  - Added a bounded helper for `controlled_run + factor_algebra + single-note`.
  - Injected a controlled-run focus section into the first-attempt factor-algebra prompt.
  - Generalized the existing factor-algebra profile policy rejection hook so it can reject paused families in `controlled_run`, not only in `fast_feedback`.
  - Paused `ratio_momentum` for the current controlled single-note path and recorded it as `value_density`.

- [test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py)
  - Added a controlled-run policy rejection test for paused `ratio_momentum`.
  - Added a prompt-injection test for the controlled-run focus section.
  - Kept the existing single-note stop-loss regression in the targeted verification set.

- [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)
  - Recorded the new controlled-run single-note family pause under `EXP-003` as an explicit `experiment_concession`.

## Why

- The latest pre-change controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114204/round_000.json) showed a stable `factor_algebra` blocker centered on `ratio_momentum`:
  - `factor_algebra novelty = 3`
  - `factor_algebra alignment = 1`
  - sample rejections repeatedly hit `factor_algebra|ratio_momentum|...`
- The smallest valid next slice was to externalize the existing fast-feedback family-steering pattern into the bounded controlled-run single-note path rather than reopening Stage 3 or inventing a broader legacy-family parser.
- Concession check: `experiment_concession`; this belongs in the runtime ledger because it is a profile-specific temporary family pause, not the final Stage 2 architecture.

## Verification

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
  - Result: `3 passed, 100 deselected in 52.79s`

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_fast_feedback_rejects_disallowed_ratio_momentum_family or factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
  - Result: `4 passed, 99 deselected in 13.53s`

- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`
  - Result: completed successfully and wrote [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_125645/round_000.json)
  - Comparison against the prior controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114204/round_000.json):
    - `generated_count: 15 -> 13`
    - `local_retry_count: 3 -> 1`
    - `novelty: 11 -> 9`
    - `validator: 3 -> 1`
    - `factor_algebra novelty: 3 -> 1`
    - `factor_algebra alignment: 1 -> 3`
  - Interpretation:
    - The `ratio_momentum` blocker was removed from the current controlled single-note path.
    - The next blocker immediately moved to `factor_algebra|volume_confirmation|...` alignment mismatch.
    - This is a valid bounded slice because it changed the real residual mix instead of only changing unit-test behavior.

## Open items

- `approved_notes_count` remains `0`, so this slice does not yet unlock self-evolve smoke.
- `factor_algebra` is still the next best target, but the problem has shifted from `ratio_momentum` novelty/alignment to `volume_confirmation` alignment.
- `narrative_mining` and `cross_market` novelty residuals remain visible and should be revisited after the next factor-algebra alignment slice.
