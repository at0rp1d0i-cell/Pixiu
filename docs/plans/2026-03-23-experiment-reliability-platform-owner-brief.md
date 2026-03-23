# Experiment Reliability Platform Owner Brief

Status: active
Owner: coordinator
Last Reviewed: 2026-03-23

Purpose: Define a parallel owner lane for a second developer to build the experiment reliability platform without colliding with the active Stage 2 / FormulaSketch mainline.

---

## Recommended Branch

- `feature/experiment-reliability-platform`

This branch owns the experiment platform layer, not the Stage 2 generation core.

---

## Mission

Take ownership of the `Experiment Reliability Platform` as an independent subsystem.

The goal is to make Pixiu experiments:

- easier to start
- easier to configure
- easier to diagnose
- less fragile under live-data noise

This is not a bugfix branch. It is a platform branch.

---

## Why This Branch Exists

Current mainline work is concentrated on:

- Stage 2 convergence
- FormulaSketch Lite
- anti-collapse / failure policy discussion

That write set is already hot and should stay narrow.

At the same time, the experiment platform is still underbuilt:

- Stage 1 live-data behavior is noisy
- `doctor / preflight / harness` layering still needs hardening
- experiment settings are still too thin
- fast feedback experiments are not yet first-class
- runtime diagnostics are useful but not yet a stable platform surface

This branch isolates that work behind a clear ownership boundary.

---

## In Scope

This branch owns:

1. `Stage 1 reliability hardening`
2. `doctor / preflight / harness` layering
3. `experiment settings layer v1`
4. `fast feedback experiment` formalization
5. runtime diagnostics / artifact readability

---

## Out of Scope

Do **not** change:

- `src/agents/researcher.py`
- FormulaSketch / Stage 2 contract work
- Stage 3 validator / math semantics
- schema truth in `src/schemas/`
- `docs/overview/05_spec-execution-audit.md`
- product positioning docs

If work discovers design drift in those areas, report it back to coordinator instead of silently expanding scope.

---

## Canonical Truth Anchors

Read these first:

1. [AGENTS.md](/home/torpedo/Workspace/ML/Pixiu/AGENTS.md)
2. [CLAUDE.md](/home/torpedo/Workspace/ML/Pixiu/CLAUDE.md)
3. [00_documentation-standard.md](/home/torpedo/Workspace/ML/Pixiu/docs/00_documentation-standard.md)
4. [03_architecture-overview.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/03_architecture-overview.md)
5. [05_spec-execution-audit.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/05_spec-execution-audit.md)
6. [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)
7. [2026-03-23-experiment-harness-design.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/2026-03-23-experiment-harness-design.md)
8. [2026-03-23-experiment-harness-implementation.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/2026-03-23-experiment-harness-implementation.md)
9. [2026-03-23-env-truth-design.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/2026-03-23-env-truth-design.md)
10. [2026-03-23-env-truth-implementation.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/2026-03-23-env-truth-implementation.md)

Use repo-local Codex workflow too:

- [/.codex/README.md](/home/torpedo/Workspace/ML/Pixiu/.codex/README.md)
- [pixiu-official-source-gate](/home/torpedo/Workspace/ML/Pixiu/.codex/skills/pixiu-official-source-gate/SKILL.md)
- [pixiu-harness-first](/home/torpedo/Workspace/ML/Pixiu/.codex/skills/pixiu-harness-first/SKILL.md)
- [pixiu-runtime-concession-check](/home/torpedo/Workspace/ML/Pixiu/.codex/skills/pixiu-runtime-concession-check/SKILL.md)
- [pixiu-worker-brief](/home/torpedo/Workspace/ML/Pixiu/.codex/skills/pixiu-worker-brief/SKILL.md)

---

## Allowed Write Surface

Primary write surface:

- [market_analyst.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/market_analyst.py)
- [stage1.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/nodes/stage1.py)
- [doctor.py](/home/torpedo/Workspace/ML/Pixiu/scripts/doctor.py)
- [experiment_preflight.py](/home/torpedo/Workspace/ML/Pixiu/scripts/experiment_preflight.py)
- [run_experiment_harness.py](/home/torpedo/Workspace/ML/Pixiu/scripts/run_experiment_harness.py)
- [config/experiments](/home/torpedo/Workspace/ML/Pixiu/config/experiments)
- Stage 1 / harness / settings related tests

Allowed doc surface:

- [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md) only when a real runtime concession changes
- new `docs/plans/` docs for this branch’s implementation slices

Avoid touching unrelated docs.

---

## Milestones

### M1: Stage 1 Hardening

Goal:

- make blocking core / enrichment failure semantics explicit
- normalize Stage 1 output shape
- stop enrichment noise from polluting controlled runs

Concrete targets:

- `get_market_hot_topics` is clearly enrichment-only
- semantic failures become telemetry, not just logs
- `northbound` fields do not degrade because of `None` shape drift

Acceptance:

- Stage 1 artifacts clearly distinguish:
  - blocking failure
  - enrichment failure
  - degraded reason

### M2: Experiment Settings Layer v1

Goal:

- turn experiment mode selection into config, not ad hoc shell choreography

Concrete targets:

- target islands / subspaces
- market context mode: `live | cached | frozen`
- persistence mode: `artifact_only | test_namespace | full`
- stage toggles where appropriate
- explicit fast-feedback vs controlled-run profile separation

Acceptance:

- profiles resolve into explicit runtime truth
- no ambiguity about what a run is allowed to write

### M3: Fast Feedback Experiment

Goal:

- create a first-class fast loop for engineering validation

Concrete targets:

- frozen or cached context support
- no pollution of formal `factor_pool / failure memory / scheduler state`
- support targeted subspace debugging

Acceptance:

- a developer can run a focused experiment without pretending it is a formal controlled run

### M4: Diagnostics Surface

Goal:

- make failures easier to interpret across doctor, preflight, harness, and Stage 1 artifacts

Concrete targets:

- clearer failure summaries
- clearer tiering of API/data/runtime issues
- stable artifact fields for later productization

Acceptance:

- the platform tells the user where the run failed without reading raw logs

---

## Validation Gates

Use `pixiu-harness-first`.

Default evidence ladder:

1. targeted pytest
2. `doctor(core)`
3. `preflight`
4. `single`
5. `fast feedback` or `controlled run`, depending on the slice

Preferred commands:

```bash
uv run pytest -q tests -k "stage1 or doctor or preflight or harness"
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/experiment_preflight.py --json
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 uv run pixiu run --mode single --island momentum
```

Do not jump directly to long runs.

---

## External Semantics Rule

Use `pixiu-official-source-gate`.

If changing behavior tied to:

- Tushare
- MCP
- OpenAI
- Chroma

check official docs or runtime truth first.

Task notes must include:

`Source checked: ...`

---

## Runtime Concession Rule

Use `pixiu-runtime-concession-check`.

If the branch introduces:

- new fallback
- degraded mode
- experiment-only shortcut
- compat bridge
- deferred runtime behavior

then explicitly decide whether [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md) must change.

Do not let runtime concessions live only in chat or commit messages.

---

## Worker / Reviewer Output Standard

Every task handoff must include:

1. `What changed`
2. `Why`
3. `Verification`
4. `Open items`

No verification means not done.

---

## Success Definition

This branch is successful when `Experiment Reliability Platform` becomes a clearly owned subsystem rather than a loose pile of scripts and conventions.

By the end of the branch, Pixiu should be meaningfully better at:

- starting experiments
- configuring experiments
- distinguishing live-data failure from system failure
- running fast engineering validation without pretending it is research truth
