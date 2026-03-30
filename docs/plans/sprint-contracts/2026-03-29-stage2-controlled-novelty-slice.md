# Sprint Contract: controlled-run Stage 2 novelty slice

## Planner

Planner owns the task plan and acceptance contract.

Lead

Implementation report path: docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md

## Generator

Generator owns implementation output only.

Implementation Worker

## Evaluator

Evaluator owns verification and writeback evidence.

Lead review + controlled/default artifact proof

## Scope

Reduce controlled-run Stage 2 novelty waste on the real surface, prioritizing the highest-waste subspaces shown in data/experiment_runs/20260329_224455/round_000.json. Allowed write set: src/agents/researcher.py, src/agents/prefilter.py, src/formula/**, tests/test_stage2.py, tests/integration/test_stage2_live.py, docs/overview/05_spec-execution-audit.md, docs/plans/current_implementation_plan.md, docs/overview/06_runtime-concessions.md, docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md. Do not modify Stage 1 runtime, Stage 4/5 thresholds, schema contracts, experiment profiles, or unrelated docs.

## Acceptance Criteria

Worker must show What changed/Why/Verification/Open items, run targeted Stage 2 novelty-focused tests, and provide controlled/default runtime evidence showing the novelty-heavy rejection mix changed on the real surface or a precise explanation of the residual blocker.

Builder handoff output: docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md
