# Invocation Spec: Architect review invocation

## Role

Architect Reviewer

## Logical Role

architect-reviewer

## Source Packet

docs/plans/review-packets/architect.md

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: high

## Runtime Skill

.agents/skills/architecture-review/SKILL.md

## Role Metadata

.agents/skills/architecture-review/agents/openai.yaml

## Consumed Artifacts

- docs/plans/review-packets/architect.md
- docs/project/PROJECT_BRIEF.md
- docs/project/ROADMAP.md
- docs/project/ARCHITECTURE.md
- docs/project/QUALITY_BAR.md
- docs/plans/2026-03-27-stage1-live-closure-plan.md

## Expected Writeback Target

docs/plans/review-passes/architect.md

## Expected Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/architect.md --title "Architect live pass" --role Architect --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
