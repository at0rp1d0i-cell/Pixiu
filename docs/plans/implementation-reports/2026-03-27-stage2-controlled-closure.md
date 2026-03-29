# Implementation Report: controlled-run Stage 2 closure

## Consumed Sprint Contract

docs/plans/sprint-contracts/2026-03-27-stage2-controlled-closure.md

## Generator Summary

Bounded Stage 2 closure slice: extend single-note local full-rejection stop-loss to `controlled_run` and carry low-value family gating from `fast_feedback` into the controlled surface so known low-value families and non-recoverable full rejections stop wasting extra retries.

## Files Touched

- `src/agents/researcher.py`
- `tests/test_stage2.py`

## Tests Run

- `uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_low_value_family_as_value_density or controlled_run_single_note_full_rejection_skips_retry"`
- `uv run pytest -q tests/test_stage2.py -k "fast_feedback_retry_bans_volume_confirmation_after_repeated_alignment_failures or fast_feedback_validator_full_rejection_still_retries or controlled_run_rejects_low_value_family_as_value_density or controlled_run_single_note_full_rejection_skips_retry"`
- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai uv run python scripts/doctor.py --mode core`
- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai uv run python scripts/run_experiment_harness.py --profile config/experiments/default.json --json`

## Follow-Ups

- Verify on a fresh controlled/default runtime artifact whether the new guards materially reduce `local_retry_count` and `novelty waste`.
- Continue the next Stage 2 closure slice on JSON/output robustness and approved-to-low-sharpe value density.

## What changed

- [src/agents/researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py)
  - Added `_CONTROLLED_RUN_NONRETRY_FILTERS` and `_is_controlled_run_profile()`.
  - Generalized the retry stop-loss helper from fast-feedback-only to `_should_skip_stage2_retry()`.
  - Enabled controlled-run stop-loss when `PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run` and `PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1`, so single-note local full rejections on non-recoverable filters (`alignment / novelty / anti_collapse / value_density / grounding`) do not burn an extra retry.
  - Extended the historical `low_value family` gate from `fast_feedback` to `controlled_run`, so known low-sharpe factor families are rejected as `value_density` on the controlled surface as well.

- [tests/test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py)
  - Added `test_factor_algebra_controlled_run_rejects_low_value_family_as_value_density`.
  - Added `test_factor_algebra_controlled_run_single_note_full_rejection_skips_retry`.

## Why

- The current controlled-run Stage 2 waste is dominated by local full rejections that were still triggering retry, even though the retry had no realistic chance to recover value.
- Recent controlled-run evidence showed the dominant waste mix was still novelty/alignment-heavy before any candidate reached Stage 3/4 in a useful way.
- The smallest bounded fix was:
  1. stop retrying controlled-run single-note local full rejections on clearly non-recoverable filters; and
  2. push existing low-value family memory from fast-feedback into the controlled surface.

This keeps scope inside Stage 2 local generation/prescreen logic and avoids touching Stage 1, Stage 4/5 thresholds, schema contracts, or experiment profiles.

## Verification

- `uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_low_value_family_as_value_density or controlled_run_single_note_full_rejection_skips_retry"`
  - Result: `2 passed, 97 deselected in 4.37s`
- `uv run pytest -q tests/test_stage2.py -k "fast_feedback_retry_bans_volume_confirmation_after_repeated_alignment_failures or fast_feedback_validator_full_rejection_still_retries or controlled_run_rejects_low_value_family_as_value_density or controlled_run_single_note_full_rejection_skips_retry"`
  - Result: `4 passed, 95 deselected in 30.26s`
- `env HOME=/tmp/pixiu-home ... uv run python scripts/doctor.py --mode core`
  - Result: blocking data + blocking API checks passed; doctor no longer blocked by the read-only home cache path once `HOME` was redirected to `/tmp/pixiu-home`
- `env HOME=/tmp/pixiu-home ... uv run python scripts/run_experiment_harness.py --profile config/experiments/default.json --json`
  - Result: command timed out later in the run, but a real controlled/default artifact was written at `data/experiment_runs/20260329_224455/round_000.json`
  - Runtime evidence from `round_000.json`:
    - `generated_count = 18`
    - `delivered_count = 0`
    - `local_retry_count = 0`
    - `rejection_counts_by_filter = {"novelty": 16, "alignment": 2}`
  - Runtime log evidence showed the new stop-loss firing on the controlled surface for `factor_algebra`, `narrative_mining`, and `cross_market`

## Open items

- This slice now has both targeted test proof and one real controlled/default artifact showing `local_retry_count = 0`, but the run still timed out later because the broader controlled surface remains expensive and noisy under live provider latency.
- The next slice should target the remaining dominant wastes exposed by `round_000.json`: `novelty` and `alignment`, plus broader JSON/output robustness.
