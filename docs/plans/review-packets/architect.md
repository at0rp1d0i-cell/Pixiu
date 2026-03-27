# Review Packet: Architect review packet

## Role

Architect

## Logical Role

architect-reviewer

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: high

## Runtime Role Binding

- skill: .agents/skills/architecture-review/SKILL.md
- metadata: .agents/skills/architecture-review/agents/openai.yaml
- canonical_writeback_target: docs/plans/review-passes/architect.md
- canonical_writeback_command: uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/architect.md --role Architect

## Objective

Assess module boundaries and architecture fit before build.

## Canonical Sources

- docs/project/PROJECT_BRIEF.md
- docs/project/ROADMAP.md
- docs/project/ARCHITECTURE.md
- docs/project/QUALITY_BAR.md

## Plan Brief

docs/plans/2026-03-27-stage1-live-closure-plan.md

## Expected Output

Return a review-pass with Role, Focus, Findings, Auto Decisions, Taste Decisions, Recommendation

## Writeback Target

docs/plans/review-passes/architect.md

## Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/architect.md --title "Architect live pass" --role Architect --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
