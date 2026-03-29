# Sprint Contract: controlled-run Stage 2 closure

## Planner

Planner owns the task plan and acceptance contract.

Lead

Implementation report path: docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md

## Generator

Generator owns implementation output only.

Implementation Worker

## Evaluator

Evaluator owns verification and writeback evidence.

Lead review + targeted harness proof

## Scope

Close the controlled-run Stage 2 path by reducing novelty waste, improving JSON/output robustness, and shrinking approved->low_sharpe waste in the real controlled/default surface. Allowed write set: src/agents/researcher.py, src/agents/prefilter.py, src/formula/**, tests/test_stage2.py, tests/integration/test_stage2_live.py, docs/overview/05_spec-execution-audit.md, docs/plans/current_implementation_plan.md, docs/overview/06_runtime-concessions.md, docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md. Do not modify Stage 1 runtime, Stage 4/5 scoring thresholds, schema contracts, or experiment profiles unless strictly required by evidence.

## Acceptance Criteria

Worker must show What changed/Why/Verification/Open items, run targeted Stage 2 tests, and provide real runtime proof through controlled/default profile evidence or a justified bounded substitute artifact showing the dominant Stage 2 waste mix changed on the real surface.

Builder handoff output: docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md
