# Review Packet: Reviewer review packet

## Role

Reviewer

## Logical Role

code-reviewer

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: high

## Runtime Role Binding

- skill: .agents/skills/code-reviewer/SKILL.md
- metadata: .agents/skills/code-reviewer/agents/openai.yaml
- canonical_writeback_target: docs/plans/review-passes/reviewer.md
- canonical_writeback_command: uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/reviewer.md --role Reviewer

## Objective

Assess quality expectations and verification readiness before build.

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

docs/plans/review-passes/reviewer.md

## Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/reviewer.md --title "Reviewer live pass" --role Reviewer --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
