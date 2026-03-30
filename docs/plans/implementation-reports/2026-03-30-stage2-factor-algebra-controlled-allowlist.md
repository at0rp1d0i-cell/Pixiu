# Implementation Report: controlled-run Stage 2 factor_algebra allowlist

## Consumed Sprint Contract

docs/plans/sprint-contracts/2026-03-30-stage2-factor-algebra-controlled-allowlist.md

## Generator Summary

Narrowed `controlled_run + factor_algebra + single-note` from a partial blacklist to a temporary `mean_spread` allowlist, moved the policy gate ahead of alignment, and validated the new real-surface residual on a fresh controlled-run single artifact.

## Files Touched

- `src/agents/researcher.py`
- `tests/test_stage2.py`
- `docs/overview/06_runtime-concessions.md`

## Tests Run

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_rejects_volume_confirmation_family or factor_algebra_controlled_run_single_note_injects_focus_section"`
- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_fast_feedback_rejects_disallowed_ratio_momentum_family or factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_rejects_volume_confirmation_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`

## Follow-Ups

- The next bounded Stage 2 slice should target `factor_algebra` wording/alignment recovery for `mean_spread`, not another family-policy change.
- The cleanest next experiment is likely a bounded retry path for `controlled_run + factor_algebra + single-note + alignment-only rejection`, because the blocker is now wording inside the allowed family rather than family selection itself.
- Self-evolve smoke remains blocked because `approved_notes_count` is still `0`.

## What changed

- [researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py)
  - Replaced the current controlled-run single-note family blacklist with a `mean_spread` allowlist.
  - Updated the controlled-run factor-algebra focus section to state the allowlist explicitly.
  - Moved the factor-algebra profile policy gate ahead of alignment so disallowed families are stopped as `value_density` before they can masquerade as alignment failures.

- [test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py)
  - Added controlled-run rejection coverage for `volume_confirmation`.
  - Updated the controlled-run focus-section assertions to match the allowlist policy.
  - Updated the single-note full-rejection regression to expect `value_density` under the new policy order.

- [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)
  - Updated `EXP-003` to record the current temporary `mean_spread` allowlist in controlled single-note mode.

## Why

- The prior fresh controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_125645/round_000.json) removed `ratio_momentum` as the main blocker, but immediately exposed `volume_confirmation` alignment as the next blocker.
- That meant the current single-note problem was no longer a single bad family; it was the instability of the remaining non-`mean_spread` family surface.
- A temporary allowlist is a cleaner concession than continuing to add blocker-specific family blacklists one by one.
- Concession check: `experiment_concession`; this is still a profile-specific temporary narrowing of the Stage 2 search surface.

## Verification

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_rejects_volume_confirmation_family or factor_algebra_controlled_run_single_note_injects_focus_section"`
  - Result: `3 passed, 101 deselected in 29.40s`

- `uv run pytest -q tests/test_stage2.py -k "factor_algebra_fast_feedback_rejects_disallowed_ratio_momentum_family or factor_algebra_controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_rejects_volume_confirmation_family or factor_algebra_controlled_run_single_note_injects_focus_section or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`
  - Result: `5 passed, 99 deselected in 6.40s`

- `env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum`
  - Result: completed successfully and wrote [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_140354/round_000.json)
  - Comparison against [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_125645/round_000.json):
    - `generated_count: 13 -> 14`
    - `local_retry_count: 1 -> 2`
    - `alignment: 3 -> 4`
    - `validator: 1 -> 2`
    - `novelty: 9 -> 8`
    - `factor_algebra novelty: 1 -> 0`
  - Interpretation:
    - The family-level blocker is no longer the main problem in `factor_algebra`.
    - The new factor-algebra residual is now cleanly centered on `mean_spread cannot claim return delta or acceleration`.
    - This did not unlock self-evolve smoke, but it did isolate the next blocker more precisely.

## Open items

- `approved_notes_count` remains `0`, so evolve smoke is still gated off.
- `factor_algebra` now needs a wording/alignment recovery slice rather than another family-surface slice.
- `narrative_mining` and `cross_market` still show residual waste, but the clearest next incremental gain remains inside `factor_algebra` wording recovery.
