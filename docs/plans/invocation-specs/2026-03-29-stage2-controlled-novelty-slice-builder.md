# Invocation Spec: controlled-run Stage 2 novelty slice builder dispatch invocation

## Role

Implementation Worker

## Logical Role

implementation-worker

## Source Packet

docs/plans/dispatch-packets/2026-03-29-stage2-controlled-novelty-slice-builder.md

## Invocation Bridge

- agent_type: worker
- model: gpt-5.4
- reasoning_effort: high

## Runtime Skill

.agents/skills/implementation-worker/SKILL.md

## Role Metadata

.agents/skills/implementation-worker/agents/openai.yaml

## Consumed Artifacts

- docs/plans/dispatch-packets/2026-03-29-stage2-controlled-novelty-slice-builder.md
- docs/plans/sprint-contracts/2026-03-29-stage2-controlled-novelty-slice.md

## Expected Writeback Target

docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md

## Expected Writeback Command

Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md
