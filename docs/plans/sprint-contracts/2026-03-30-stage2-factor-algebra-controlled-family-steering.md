# Sprint Contract: controlled-run Stage 2 factor_algebra family steering

## Planner

Planner owns the task plan and acceptance contract.

Lead

Implementation report path: docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md

## Generator

Generator owns implementation output only.

Implementation Worker

## Evaluator

Evaluator owns verification and writeback evidence.

Lead review + controlled-run artifact proof

## Scope

Reduce the next stable controlled-run Stage 2 blocker by steering single-note `factor_algebra` generation away from `ratio_momentum`. Allowed write set: `src/agents/researcher.py`, `tests/test_stage2.py`, `docs/overview/06_runtime-concessions.md`, `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md`. Do not modify Stage 1 runtime, Stage 3 logic, Stage 4/5 thresholds, schemas, experiment profiles, or unrelated docs.

## Acceptance Criteria

Worker must show What changed/Why/Verification/Open items, run targeted Stage 2 tests, and provide a fresh controlled-run single artifact showing whether the `factor_algebra` residual is no longer dominated by `ratio_momentum` novelty/alignment. If the blocker moves but does not disappear, the implementation report must say exactly where it moved.

Builder handoff output: docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md
