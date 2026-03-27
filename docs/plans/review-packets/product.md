# Review Packet: Product review packet

## Role

Product

## Logical Role

product-reviewer

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: medium

## Runtime Role Binding

- skill: .agents/skills/product-discovery/SKILL.md
- metadata: .agents/skills/product-discovery/agents/openai.yaml
- canonical_writeback_target: docs/plans/review-passes/product.md
- canonical_writeback_command: uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/product.md --role Product

## Objective

Assess milestone fit and scope pressure before build.

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

docs/plans/review-passes/product.md

## Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/product.md --title "Product live pass" --role Product --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
