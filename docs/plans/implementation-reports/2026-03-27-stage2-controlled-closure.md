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

## Open items

- This slice proves the new controlled-run stop-loss and value-density behavior with targeted Stage 2 tests only.
- A full controlled/default runtime artifact was attempted earlier, but that path remains expensive and noisy because of live provider latency/retries; this report therefore uses the bounded substitute allowed by the sprint contract.
- The next slice should verify whether these guarded retries materially reduce real controlled-run `local_retry_count` / `novelty waste` on a fresh runtime artifact, without widening scope beyond Stage 2 closure.
