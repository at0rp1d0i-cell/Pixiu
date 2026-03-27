# Dispatch Packet: Stage1 live closure QA QA dispatch

## Role

QA Runner

## Logical Role

qa-runner

## Invocation Bridge

- agent_type: worker
- model: gpt-5.4
- reasoning_effort: medium

## Runtime Role Binding

- skill: .agents/skills/qa-runner/SKILL.md
- metadata: .agents/skills/qa-runner/agents/openai.yaml
- canonical_writeback_target: docs/plans/qa-report-<task>.md
- canonical_writeback_command: uv run python scripts/ops_loop.py qa --title <title> --sprint-contract-path <path> --implementation-report-path <path> --qa-report-path <path> --environment <environment> --scenario <scenario> --verification-status <passed|failed>

## Objective

Validate the bounded task against the sprint contract and implementation report.

## Consumed Artifacts

- docs/plans/sprint-contracts/2026-03-27-stage1-live-closure.md
- docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Constraints

Environment: local uv + repo env truth

Scenarios:
- Stage 1 live closure targeted verification: unit Stage 1 coverage, live Tushare blocking-core path, doctor/preflight, and controlled single entry reaching Stage 2 without Stage 1 degradation.

## Expected Output

QA report at docs/plans/qa-reports/2026-03-27-stage1-live-closure.md

## Writeback Target

docs/plans/qa-reports/2026-03-27-stage1-live-closure.md

## Completion Command

Return QA findings by writing the QA report to docs/plans/qa-reports/2026-03-27-stage1-live-closure.md
