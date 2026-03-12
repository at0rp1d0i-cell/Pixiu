# AGENTS.md

Repository guidance for coding agents working in this project.

## Canonical Docs

Before making architectural decisions, read these in order:

1. `docs/README.md`
2. `docs/overview/README.md`
3. `docs/overview/architecture-overview.md`
4. `docs/overview/spec-execution-audit.md`
5. `docs/design/test-pipeline.md`
6. `docs/plans/agent_team_operating_model.md`

Do not treat `docs/archive/` as the source of truth for current implementation.

## Project State

The project has evolved from early `EvoQuant` / v1 material into `Pixiu v2`, an LLM-native alpha research funnel for A-shares.

Current realities:

- `src/schemas/` is the closest thing to the current interface truth.
- `docs/overview/spec-execution-audit.md` is the authoritative summary of what is implemented, partial, drifting, or archived.
- Stage 4 and Stage 5 are currently the highest-drift areas.
- CLI and API exist in minimum form; Web Dashboard is not implemented yet.
- Test workflow is now normalized around `docs/design/test-pipeline.md`.
- Agent-team dispatch rules live in `docs/plans/agent_team_operating_model.md`.

## Working Rules

- When specs and code disagree, first determine whether the code is ahead, behind, or drifting from spec. Record the answer in the relevant spec before large implementation changes.
- Prefer `docs/overview/` + `docs/design/` over legacy design notes.
- Treat `docs/research/` as context and historical discussion, not as implementation truth.
- Treat `docs/reference/` as supporting material only.
- Root agent keeps ownership of architecture truth, integration, and final verification.
- Dispatch `worker` agents only with explicit write sets and success criteria.
- Use `reviewer` only after a diff and at least one concrete verification result exist.
- Use `explorer` for short, evidence-driven audits only; do not leave it as a long-running background thread.

## Useful Commands

```bash
# baseline
python -m src.core.run_baseline

# single-island debug run
python -m src.core.orchestrator --mode single --island momentum

# evolve loop
python -m src.core.orchestrator --mode evolve --rounds 20

# tests
pytest -q tests -m "smoke or unit"
```

## Current Design Focus

If you are asked to advance the architecture, the recommended order is:

1. Keep docs/spec status accurate.
2. Normalize the test pipeline.
3. Converge Stage 4 on a single execution path.
4. Implement Stage 5 runtime components to match the schemas.
5. Only then expand Dashboard and data-source surface area.

## Agent Team Rules

- Prefer `root + 1-2 workers` over a large always-on team.
- Parallelize only when write sets do not overlap.
- If an agent exceeds its timebox without useful output, root should take over or split the task smaller.
- Worker outputs must include:
  - what changed
  - why
  - test results
  - changed file list
