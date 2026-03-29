# Dispatch Packet: controlled-run Stage 2 closure builder dispatch

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

Implementation Worker

## Consumed Artifacts

- docs/plans/sprint-contracts/2026-03-27-stage2-controlled-closure.md

## Constraints

Close the controlled-run Stage 2 path by reducing novelty waste, improving JSON/output robustness, and shrinking approved->low_sharpe waste in the real controlled/default surface. Allowed write set: src/agents/researcher.py, src/agents/prefilter.py, src/formula/**, tests/test_stage2.py, tests/integration/test_stage2_live.py, docs/overview/05_spec-execution-audit.md, docs/plans/current_implementation_plan.md, docs/overview/06_runtime-concessions.md, docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md. Do not modify Stage 1 runtime, Stage 4/5 scoring thresholds, schema contracts, or experiment profiles unless strictly required by evidence.

Acceptance contract:
Worker must show What changed/Why/Verification/Open items, run targeted Stage 2 tests, and provide real runtime proof through controlled/default profile evidence or a justified bounded substitute artifact showing the dominant Stage 2 waste mix changed on the real surface.

## Expected Output

Implementation report at docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md

## Writeback Target

docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md

## Completion Command

Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md
