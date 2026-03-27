# Task Brief: workflow-reset

## Objective

Reset Pixiu development to a branch-based Lead -> Ops -> Specialists workflow with bounded briefs, review gates, QA/docs sync expectations, and merge/PR discipline.

## Scope

Define the repo-backed workflow contract for branching, briefs, sprint contracts, implementation reports, review passes, QA/docs sync preparation, and merge/PR expectations. Keep this at workflow/doc/orchestration level, not business-runtime feature work.

## Constraints

Do not start build work. Do not use this task to change Stage 1/2/validation behavior. Align with current team runtime scripts and canonical docs. Keep it compatible with private collaboration infrastructure in this repo.

## Relevant Decisions

Lead is the single visible entrypoint; Ops owns bounded execution packets; Specialists do implementation/review/QA/docs. Branch-based work requires bounded briefs and verification before merge/PR.

## Expected Output

A branch-ready task package for codifying the branch/brief/review/QA/docs/merge flow, including file targets, acceptance criteria, and excluded work.

## Writeback Target

This brief will be used to start a dedicated workflow-reset branch after approval.
