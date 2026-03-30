# Sprint Contract: controlled-run Stage 2 factor_algebra allowlist

## Planner

Lead

Implementation report path: docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md

## Generator

Implementation Worker

## Evaluator

Lead review + controlled-run artifact proof

## Scope

Narrow `controlled_run + factor_algebra + single-note` to a temporary `mean_spread` allowlist. Allowed write set: `src/agents/researcher.py`, `tests/test_stage2.py`, `docs/overview/06_runtime-concessions.md`, `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md`. Do not modify Stage 1, Stage 3, Stage 4/5 thresholds, schemas, or unrelated docs.

## Acceptance Criteria

The slice must show exact test evidence plus a fresh controlled-run artifact proving that `factor_algebra` is no longer mainly failing on `ratio_momentum` or `volume_confirmation` in single-note mode. If self-evolve smoke is still blocked, the report must identify the new blocker exactly.
