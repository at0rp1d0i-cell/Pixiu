# Invocation Spec: Product review invocation

## Role

Product Reviewer

## Logical Role

product-reviewer

## Source Packet

docs/plans/review-packets/product.md

## Invocation Bridge

- agent_type: explorer
- model: gpt-5.4
- reasoning_effort: medium

## Runtime Skill

.agents/skills/product-discovery/SKILL.md

## Role Metadata

.agents/skills/product-discovery/agents/openai.yaml

## Consumed Artifacts

- docs/plans/review-packets/product.md
- docs/project/PROJECT_BRIEF.md
- docs/project/ROADMAP.md
- docs/project/ARCHITECTURE.md
- docs/project/QUALITY_BAR.md
- docs/plans/2026-03-27-stage1-live-closure-plan.md

## Expected Writeback Target

docs/plans/review-passes/product.md

## Expected Writeback Command

uv run python scripts/team_state.py review-pass --output docs/plans/review-passes/product.md --title "Product live pass" --role Product --focus "<focus>" --finding "<finding>" --auto-decision "<auto decision>" --recommendation "<recommendation>"
