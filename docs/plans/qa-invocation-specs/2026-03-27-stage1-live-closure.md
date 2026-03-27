# Invocation Spec: Stage1 live closure QA QA dispatch invocation

## Role

QA Runner

## Logical Role

qa-runner

## Source Packet

docs/plans/qa-packets/2026-03-27-stage1-live-closure.md

## Invocation Bridge

- agent_type: worker
- model: gpt-5.4
- reasoning_effort: medium

## Runtime Skill

.agents/skills/qa-runner/SKILL.md

## Role Metadata

.agents/skills/qa-runner/agents/openai.yaml

## Consumed Artifacts

- docs/plans/qa-packets/2026-03-27-stage1-live-closure.md
- docs/plans/sprint-contracts/2026-03-27-stage1-live-closure.md
- docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Expected Writeback Target

docs/plans/qa-reports/2026-03-27-stage1-live-closure.md

## Expected Writeback Command

Return QA findings by writing the QA report to docs/plans/qa-reports/2026-03-27-stage1-live-closure.md
