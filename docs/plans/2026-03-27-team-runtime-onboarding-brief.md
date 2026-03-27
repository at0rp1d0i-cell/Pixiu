# Task Brief: team-runtime-onboarding

## Objective

Bring the private collaboration runtime into this private repo as a repo-managed, reproducible layer without mixing it into Pixiu business runtime.

## Scope

Track and normalize .agents/skills/team-lead and specialist skills, .codex/config.toml, .codex/roles, .codex/role_bridge.toml, ops/, and bridge/runtime scripts needed for Lead -> Ops -> Specialists execution. Keep business/runtime code out of scope.

## Constraints

Treat this as private collaboration infrastructure. Preserve official skill root conventions (.agents/skills). Do not change Pixiu product/runtime behavior. Do not rewrite architecture docs beyond what is needed to explain the private collaboration layer. Keep write set bounded to .agents, .codex, ops, scripts/*team/lead/ops/role*, and minimal docs/status/docs/project references if required.

## Relevant Decisions

Pixiu remains the business/runtime system; team runtime is repo-managed private collaboration infrastructure. Skills stay under .agents/skills; .codex remains config/roles/bridge/docs.

## Expected Output

A branch-ready task package describing the exact files to onboard, acceptance criteria, verification checks, and what remains explicitly out of scope.

## Writeback Target

This brief will be the entry artifact for a dedicated implementation branch and later builder kickoff.
