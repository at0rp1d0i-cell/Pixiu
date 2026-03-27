# Sprint Contract: stage1-live-closure

## Planner

Planner owns the task plan and acceptance contract.

Lead selected Stage 1 live closure as the next bounded mainline slice because controlled single still degrades before meaningful Stage 2 evaluation. This build must close env truth and blocking tool discovery across pixiu run, doctor, and preflight. Write the implementation report to docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md.

Implementation report path: docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Generator

Generator owns implementation output only.

Implement Stage 1 live closure under default/controlled execution. Align pixiu run with doctor/preflight env truth, make blocking tool discovery deterministic for the known current Tushare-based path, update or add bounded Stage 1 live tests, and write back any required runtime/spec documentation updates tied to this closure.

## Evaluator

Evaluator owns verification and writeback evidence.

Verification must include repo-backed evidence from targeted Stage 1 tests plus real runtime commands that prove pixiu run, doctor/preflight, and Stage 1 live checks agree on env truth and blocking tool discovery. No unrelated Stage 2/validation feature work.

## Scope

Allowed write set: src/cli/main.py, src/core/orchestrator/_entrypoints.py, src/agents/market_analyst.py, scripts/doctor.py, scripts/experiment_preflight.py, tests/test_stage1.py, tests/integration/test_stage1_live.py, docs/overview/05_spec-execution-audit.md, docs/overview/06_runtime-concessions.md, docs/plans/current_implementation_plan.md only if strictly needed for consistency. Excluded: Stage 2/3/4/5 behavior changes, config/experiments profile redesign, broad refactors outside Stage 1 live path.

## Acceptance Criteria

1) pixiu run, doctor/preflight, and Stage 1 live tests agree on env truth for the current known path. 2) Controlled single no longer degrades at Stage 1 for the known current blocking-tool path. 3) Changes stay bounded to Stage 1 live closure. 4) Implementation report includes What changed / Why / Verification / Open items.

Builder handoff output: docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md
