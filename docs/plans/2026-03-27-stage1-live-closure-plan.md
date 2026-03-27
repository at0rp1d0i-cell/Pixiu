# Plan Brief: stage1-live-closure

## Goal

Close Stage 1 live behavior under default/controlled execution so pixiu run no longer degrades because of env truth or blocking tool discovery drift.

## Milestone

A controlled single can enter Stage 2 with non-degraded live market context, and Stage 1 live checks become a bounded, testable slice under team-lead.

## Modules In Scope

src/cli/main.py, src/core/orchestrator/_entrypoints.py, src/agents/market_analyst.py, scripts/doctor.py, scripts/experiment_preflight.py, tests/test_stage1.py, tests/integration/test_stage1_live.py, docs/overview/05_spec-execution-audit.md, docs/overview/06_runtime-concessions.md

## Exit Criteria

pixiu run, doctor/preflight, and Stage 1 live tests agree on env truth and blocking tool discovery; controlled single no longer degrades at Stage 1 for the known current path.

## Writeback Target

Create a bounded mainline-ready plan for Stage 1 live closure so Ops can later kick off build with a sprint contract and implementation report path.
