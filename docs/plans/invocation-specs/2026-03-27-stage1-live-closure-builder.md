# Invocation Spec: stage1-live-closure builder dispatch invocation

## Role

Implementation Worker

## Logical Role

implementation-worker

## Source Packet

docs/plans/dispatch-packets/2026-03-27-stage1-live-closure-builder.md

## Invocation Bridge

- agent_type: worker
- model: gpt-5.4
- reasoning_effort: high

## Runtime Skill

.agents/skills/implementation-worker/SKILL.md

## Role Metadata

.agents/skills/implementation-worker/agents/openai.yaml

## Consumed Artifacts

- docs/plans/dispatch-packets/2026-03-27-stage1-live-closure-builder.md
- docs/plans/sprint-contracts/2026-03-27-stage1-live-closure.md

## Expected Writeback Target

docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md

## Expected Writeback Command

Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-27-stage1-live-closure.md
