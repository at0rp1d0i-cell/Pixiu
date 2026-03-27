# Invocation Spec: Reviewer review invocation

## Role

Code Reviewer

## Logical Role

code-reviewer

## Source Packet

docs/plans/review-packets/reviewer.md

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: high

## Runtime Skill

.agents/skills/code-reviewer/SKILL.md

## Role Metadata

.agents/skills/code-reviewer/agents/openai.yaml

## Consumed Artifacts

- docs/plans/review-packets/reviewer.md
- docs/project/PROJECT_BRIEF.md
- docs/project/ROADMAP.md
- docs/project/ARCHITECTURE.md
- docs/project/QUALITY_BAR.md
- docs/plans/2026-03-27-stage1-live-closure-plan.md

## Expected Writeback Target

docs/plans/review-passes/reviewer.md

## Expected Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/reviewer.md --title "Reviewer live pass" --role Reviewer --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
