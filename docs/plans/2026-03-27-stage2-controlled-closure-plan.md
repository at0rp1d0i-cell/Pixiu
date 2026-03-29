# Plan Brief: stage2-controlled-closure

## Goal

Close the controlled-run Stage 2 path so mainline runs waste less generation budget on novelty/alignment/JSON failures and send fewer low-value candidates downstream.

## Milestone

Controlled single shows materially reduced Stage 2 waste with runtime evidence, and the dominant blocker moves from Stage 2 closure to validation/value-density follow-through.

## Modules In Scope

src/agents/researcher.py, src/agents/prefilter.py, src/formula/, tests/test_stage2.py, tests/integration/test_stage2_live.py, docs/overview/05_spec-execution-audit.md, docs/plans/current_implementation_plan.md

## Exit Criteria

A bounded Stage 2 closure slice is defined with target waste modes, allowed write set, and proof expectations suitable for Ops builder kickoff.

## Writeback Target

Create a repo-backed plan for controlled-run Stage 2 closure and move board state to plan.
