# Dispatch Packet: stage1-live-closure builder dispatch

## Role

Implementation Worker

## Logical Role

implementation-worker

## Invocation Bridge

- agent_type: worker
- model: gpt-5.4
- reasoning_effort: high

## Runtime Role Binding

- skill: .agents/skills/implementation-worker/SKILL.md
- metadata: .agents/skills/implementation-worker/agents/openai.yaml
- canonical_writeback_target: docs/plans/implementation-report-<task>.md
- canonical_writeback_command: uv run python scripts/team_state.py implementation-report --output <path> --title <title> --sprint-contract <path> --summary <summary> --files-touched <files> --tests-run <tests> --follow-ups <follow-ups>

## Objective

Implement Stage 1 live closure under default/controlled execution. Align pixiu run with doctor/preflight env truth, make blocking tool discovery deterministic for the known current Tushare-based path, update or add bounded Stage 1 live tests, and write back any required runtime/spec documentation updates tied to this closure.

## Consumed Artifacts

- docs/plans/sprint-contracts/2026-03-27-stage1-live-closure.md

## Constraints

Allowed write set: src/cli/main.py, src/core/orchestrator/_entrypoints.py, src/agents/market_analyst.py, scripts/doctor.py, scripts/experiment_preflight.py, tests/test_stage1.py, tests/integration/test_stage1_live.py, docs/overview/05_spec-execution-audit.md, docs/overview/06_runtime-concessions.md, docs/plans/current_implementation_plan.md only if strictly needed for consistency. Excluded: Stage 2/3/4/5 behavior changes, config/experiments profile redesign, broad refactors outside Stage 1 live path.

Acceptance contract:
1) pixiu run, doctor/preflight, and Stage 1 live tests agree on env truth for the current known path. 2) Controlled single no longer degrades at Stage 1 for the known current blocking-tool path. 3) Changes stay bounded to Stage 1 live closure. 4) Implementation report includes What changed / Why / Verification / Open items.

## Expected Output

Implementation report at docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Writeback Target

docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Completion Command

Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md
