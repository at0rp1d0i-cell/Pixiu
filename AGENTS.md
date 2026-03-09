# AGENTS.md

Repository guidance for coding agents working in this project.

## Canonical Docs

Before making architectural decisions, read these in order:

1. `docs/README.md`
2. `docs/specs/README.md`
3. `docs/specs/v2_architecture_overview.md`
4. `docs/specs/v2_spec_execution_audit.md`
5. `docs/specs/v2_test_pipeline.md`

Do not treat `docs/archive/` as the source of truth for current implementation.

## Project State

The project has evolved from early `EvoQuant` / v1 material into `Pixiu v2`, an LLM-native alpha research funnel for A-shares.

Current realities:

- `src/schemas/` is the closest thing to the current interface truth.
- `docs/specs/v2_spec_execution_audit.md` is the authoritative summary of what is implemented, partial, drifting, or archived.
- Stage 4 and Stage 5 are currently the highest-drift areas.
- CLI and API exist in minimum form; Web Dashboard is not implemented yet.
- Test workflow is still being normalized; use `docs/specs/v2_test_pipeline.md` rather than historical test commands.

## Working Rules

- When specs and code disagree, first determine whether the code is ahead, behind, or drifting from spec. Record the answer in the relevant spec before large implementation changes.
- Prefer the active v2 specs in `docs/specs/` over legacy design notes.
- Treat `docs/research/` as context and historical discussion, not as implementation truth.
- Treat `docs/reference/` as supporting material only.

## Useful Commands

```bash
# baseline
python -m src.core.run_baseline

# single-island debug run
python -m src.core.orchestrator --mode single --island momentum

# evolve loop
python -m src.core.orchestrator --mode evolve --rounds 20

# tests
PYTHONPATH=. pytest -q tests
```

## Current Design Focus

If you are asked to advance the architecture, the recommended order is:

1. Keep docs/spec status accurate.
2. Normalize the test pipeline.
3. Converge Stage 4 on a single execution path.
4. Implement Stage 5 runtime components to match the schemas.
5. Only then expand Dashboard and data-source surface area.
