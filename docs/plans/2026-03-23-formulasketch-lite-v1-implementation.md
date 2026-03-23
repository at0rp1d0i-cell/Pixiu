# FormulaSketch Lite v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce an internal `FormulaSketch Lite v1` path for `factor_algebra` so Stage 2 stops emitting as many low-level invalid and near-duplicate formulas before local prescreen.

**Architecture:** Keep the external `FactorResearchNote` contract unchanged, but insert an internal `FormulaRecipe -> deterministic renderer -> proposed_formula` step for `factor_algebra` only. The new recipe/renderer lives as a small pure helper module, then `AlphaResearcher` uses it only when the assigned subspace is `FACTOR_ALGEBRA`; all other subspaces keep the current path.

**Tech Stack:** Python 3.12, Pydantic/dataclass helpers, existing Stage 2 runtime, pytest unit tests, Pixiu experiment harness.

---

## Slice 0: Fixed Decisions

- [x] Validation mode:
  - fast feedback for targeted unit tests and single-island runtime proof
  - controlled run for harness regression proof
- [x] Proof artifacts:
  - `tests/test_formula_sketch.py`
  - `tests/test_stage2.py`
  - `data/experiment_runs/{run_id}/round_000.json`
- [x] Source checked:
  - Qlib official docs for `Rank(feature, N)` and `Quantile(feature, N, qscore)`
  - local `qlib 0.9.7` runtime behavior
- [x] Concession check:
  - `FormulaSketch Lite v1` is an `mvp_simplification`
  - `AST-first` and `schema-level FormulaSketch` remain deferred foundations

---

### Task 1: Add internal FormulaRecipe and deterministic renderer

**Files:**
- Create: `src/formula/sketch.py`
- Create: `tests/test_formula_sketch.py`

**Step 1: Write the failing tests**

Add unit tests that lock the v1 recipe/renderer contract:

- render `mean_spread`
- render `volatility_state`
- render `volume_confirmation`
- allow only `Rank(expr, N)` and `Quantile(expr, N, qscore)` normalization
- reject unsupported transform family
- reject unsupported normalization
- reject invalid window ordering
- reject free-form `Div`

**Step 2: Run the new tests to confirm they fail**

Run:

```bash
uv run pytest -q tests/test_formula_sketch.py
```

Expected:
- failures because the module does not exist yet

**Step 3: Implement the smallest pure helper module**

Create `src/formula/sketch.py` with:

- a small internal `FormulaRecipe` model
- explicit allowlists for:
  - `transform_family`
  - `normalization`
  - window buckets
- a deterministic renderer that outputs only approved formula templates
- a hard rule that v1 does not support arbitrary `Div`

Keep the module pure:
- no LLM calls
- no FactorPool access
- no Stage 3 logic

**Step 4: Run the unit tests again**

Run:

```bash
uv run pytest -q tests/test_formula_sketch.py
```

Expected:
- all tests pass

**Step 5: Commit**

```bash
git add src/formula/sketch.py tests/test_formula_sketch.py
git commit -m "feat(stage2): add FormulaSketch Lite renderer" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- a pure recipe/renderer helper exists
- invalid low-level combinations are rejected before Stage 2 emits a formula string

---

### Task 2: Route `factor_algebra` through FormulaSketch Lite

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `tests/test_stage2.py`

**Step 1: Write/extend failing Stage 2 tests**

Add Stage 2 tests that prove:

- when `subspace_hint == FACTOR_ALGEBRA`, the LLM can return recipe-shaped data and Stage 2 emits rendered `proposed_formula`
- `factor_algebra` no longer accepts free-form formula strings as the only path
- invalid recipe values are rejected locally and feed bounded retry
- other subspaces still use the current free-form path

Prefer focused tests over large integration mocks.

**Step 2: Run the targeted Stage 2 tests to confirm failure**

Run:

```bash
uv run pytest -q tests/test_stage2.py -k "formula_sketch or factor_algebra"
```

Expected:
- failures that show the new contract is not wired yet

**Step 3: Implement the factor_algebra-only routing**

Modify `src/agents/researcher.py` to:

- detect `ExplorationSubspace.FACTOR_ALGEBRA`
- instruct the LLM to emit the recipe-shaped payload for that subspace
- render the recipe into `proposed_formula`
- preserve the existing `FactorResearchNote` external schema
- keep all other subspaces on the current behavior
- keep local prescreen and Stage 3 hard gate unchanged

Do not:
- change `FactorResearchNote`
- change `Hypothesis`
- change `StrategySpec`
- widen the renderer into a general AST engine

**Step 4: Run the targeted tests again**

Run:

```bash
uv run pytest -q tests/test_formula_sketch.py tests/test_stage2.py -k "formula_sketch or factor_algebra"
```

Expected:
- all targeted tests pass

**Step 5: Commit**

```bash
git add src/agents/researcher.py tests/test_stage2.py
git commit -m "feat(stage2): route factor algebra through FormulaSketch Lite" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- `factor_algebra` has a recipe/renderer path
- non-`factor_algebra` subspaces remain unchanged
- external note/schema contracts are untouched

---

### Task 3: Prove runtime behavior with fast feedback and controlled run

**Files:**
- Modify: `docs/plans/current_implementation_plan.md` only if the active execution note needs updating
- No other docs unless behavior changed beyond the approved design

**Step 1: Run fast feedback proof**

Run:

```bash
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 uv run pixiu run --mode single --island momentum
```

Expected:
- the run completes
- a new `data/experiment_runs/{run_id}/round_000.json` exists

**Step 2: Inspect the artifact**

Check that:

- `stage2.rejection_counts_by_filter_and_subspace.validator.factor_algebra` moves in the right direction relative to the recent baseline
- Stage 3 remains active
- no schema break shows up in the artifact

**Step 3: Run controlled-run regression proof**

Run:

```bash
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json
```

Expected:
- `ok: true`
- `single` and `evolve 2 rounds` still complete

**Step 4: Run the regression test subset**

Run:

```bash
uv run pytest -q tests/test_formula_sketch.py tests/test_stage2.py tests/test_experiment_harness.py
```

Expected:
- all tests pass

**Step 5: Commit**

```bash
git add docs/plans/current_implementation_plan.md
git commit -m "docs: record FormulaSketch Lite progress" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Skip this commit if no docs changed.

Done when:

- fast feedback proof exists
- controlled run still passes
- the change is backed by artifact evidence, not log claims

---

### Task 4: Coordinator review and close-out

Owner: coordinator

Review checklist:

- spec compliance:
  - only `factor_algebra` changed
  - Stage 3 hard gate unchanged
  - schema-level sketch not introduced accidentally
- code quality:
  - helper module stays pure
  - no prompt bloat without tests
  - no free-form `Div` reintroduced in the renderer path
- concession hygiene:
  - if runtime behavior changed beyond the approved design, re-check [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)

Final verification:

```bash
uv run pytest -q tests/test_formula_sketch.py tests/test_stage2.py tests/test_experiment_harness.py
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 uv run pixiu run --mode single --island momentum
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json
```

Done when:

- the plan is implemented without widening scope
- proof artifacts show `factor_algebra` is cleaner
- the branch is ready for normal review/merge/push
