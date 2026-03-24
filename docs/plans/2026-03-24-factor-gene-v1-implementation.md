# Factor Gene v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a deterministic `factor gene` layer for `factor_algebra` so Pixiu can distinguish duplicate formulas, same-family variants, and saturated families without relying only on token-level similarity.

**Architecture:** Keep `factor gene` internal to Stage 2/3 for v1. Extract `family_gene` and `variant_gene` directly from `FormulaRecipe`, store both structured objects and canonical keys, then let `NoveltyFilter` and Stage 2 anti-collapse consume those keys for `factor_algebra` only. Do not change the main schema contracts in this slice.

**Tech Stack:** Python 3.12, existing `FormulaRecipe`/Stage 2 runtime, FactorPool integration points, pytest unit tests, Pixiu single-run experiment proof.

---

## Slice 0: Fixed Decisions

- [x] Scope:
  - `factor_algebra` only
  - no schema-level gene object
  - no multi-subspace ontology
- [x] Gene shape:
  - `family_gene`
  - `variant_gene`
  - `family_gene_key`
  - `variant_gene_key`
- [x] Truth rule:
  - structured object is source of truth
  - canonical key is retrieval/comparison key
- [x] Similarity semantics:
  - same family + same variant = duplicate
  - same family + different variant = same-family variant
  - repeated family over recent rounds = saturated family candidate
- [x] Source checked:
  - `docs/plans/2026-03-24-factor-gene-v1-design.md`
  - current `FormulaRecipe` in `src/formula/sketch.py`
  - current Stage 2 novelty/anti-collapse behavior in `src/agents/researcher.py`

---

### Task 1: Add deterministic factor gene helpers

**Files:**
- Create: `src/formula/gene.py`
- Test: `tests/test_formula_gene.py`

**Step 1: Write the failing tests**

Add focused unit tests for:

- extracting `family_gene` from a valid `FormulaRecipe`
- extracting `variant_gene` from a valid `FormulaRecipe`
- generating stable `family_gene_key`
- generating stable `variant_gene_key`
- keeping `family_gene` unchanged when only windows/qscore change
- changing `family_gene` when `transform_family` or `base_field` changes

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_formula_gene.py
```

Expected:
- fail because `src/formula/gene.py` does not exist yet

**Step 3: Write minimal implementation**

Create `src/formula/gene.py` with:

- pure helper functions only
- no LLM calls
- no FactorPool access
- no Stage 3 logic

Add:

- `build_family_gene(recipe)`
- `build_variant_gene(recipe)`
- `build_family_gene_key(recipe_or_gene)`
- `build_variant_gene_key(recipe_or_gene)`

Keep serialization deterministic:

- explicit field order
- explicit `null` handling
- no dependence on dict insertion order

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q tests/test_formula_gene.py
```

Expected:
- pass

**Step 5: Commit**

```bash
git add src/formula/gene.py tests/test_formula_gene.py
git commit -m "feat(stage2): add factor gene helpers" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- deterministic gene extraction exists
- keys are stable and test-backed

---

### Task 2: Surface factor gene in Stage 2 diagnostics

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `tests/test_stage2.py`

**Step 1: Write the failing tests**

Add/extend tests that prove:

- `factor_algebra` notes carry enough local metadata to derive genes before novelty filtering
- Stage 2 diagnostics/artifact-facing rejection samples can include gene keys for `factor_algebra`
- non-`factor_algebra` paths remain unchanged

**Step 2: Run targeted tests to verify failure**

Run:

```bash
uv run pytest -q tests/test_stage2.py -k "factor_gene or factor_algebra"
```

Expected:
- failure because gene metadata is not surfaced yet

**Step 3: Implement minimal Stage 2 integration**

Modify `src/agents/researcher.py` to:

- derive gene data from `FormulaRecipe` after successful render
- attach `family_gene_key` / `variant_gene_key` in a local runtime-safe way for `factor_algebra`
- include gene keys in local rejection samples and diagnostics where helpful

Do not:

- change `FactorResearchNote` schema in v1
- widen this to other subspaces

**Step 4: Run targeted tests**

Run:

```bash
uv run pytest -q tests/test_formula_gene.py tests/test_stage2.py -k "factor_gene or factor_algebra"
```

Expected:
- pass

**Step 5: Commit**

```bash
git add src/agents/researcher.py tests/test_stage2.py
git commit -m "feat(stage2): expose factor gene diagnostics" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- Stage 2 can talk about `factor_algebra` candidates in gene terms, not only formula strings

---

### Task 3: Add gene-aware novelty for factor_algebra

**Files:**
- Modify: `src/agents/prefilter.py`
- Modify: novelty-related tests in `tests/`
- Possibly modify: `src/factor_pool/pool.py` only if a helper is needed

**Step 1: Write failing tests**

Add focused tests for `NoveltyFilter`:

- same `family_gene_key` + same `variant_gene_key` => duplicate
- same `family_gene_key` + different `variant_gene_key` => same-family variant / collapse candidate
- non-`factor_algebra` notes still use current novelty path

**Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest -q tests/test_constraints.py tests/test_stage2.py -k "novelty or factor_gene"
```

Expected:
- failure because novelty is not gene-aware yet

**Step 3: Implement minimal novelty integration**

Modify novelty logic so that for `factor_algebra`:

- gene equality is checked before token-level fallback
- duplicate vs same-family-variant is separated in reason text
- current behavior for all other subspaces remains unchanged

Keep v1 simple:

- no continuous distance metric
- no multi-subspace ontology
- no cross-island composite factor logic

**Step 4: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_formula_gene.py tests/test_constraints.py tests/test_stage2.py -k "novelty or factor_gene"
```

Expected:
- pass

**Step 5: Commit**

```bash
git add src/agents/prefilter.py tests/test_constraints.py tests/test_stage2.py
git commit -m "feat(stage3): add gene-aware novelty for factor algebra" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- `factor_algebra` novelty is no longer driven only by formula token similarity

---

### Task 4: Upgrade anti-collapse from skeleton hints to family memory hints

**Files:**
- Modify: `src/agents/researcher.py`
- Possibly modify: `knowledge/skills/researcher/subspaces/factor_algebra.md`
- Test: `tests/test_stage2.py`

**Step 1: Write failing tests**

Add tests that prove Stage 2 prompt injection now prefers:

- saturated `family_gene_key`
- same-family variant warnings
- not just string skeleton examples

**Step 2: Run targeted tests**

Run:

```bash
uv run pytest -q tests/test_stage2.py -k "anti_collapse or factor_gene"
```

Expected:
- failure because anti-collapse still only injects skeleton text

**Step 3: Implement minimal family-memory upgrade**

Replace/extend the current anti-collapse prompt section so it can say:

- these family genes are saturated
- these recent variants were rejected as same-family collapse
- change `transform_family/base_field/interaction_mode`, not only windows

Do not yet build:

- long-term curator
- scheduler-level diversity penalty
- full gene memory persistence policy

**Step 4: Run tests**

Run:

```bash
uv run pytest -q tests/test_formula_gene.py tests/test_stage2.py -k "anti_collapse or factor_gene"
```

Expected:
- pass

**Step 5: Commit**

```bash
git add src/agents/researcher.py knowledge/skills/researcher/subspaces/factor_algebra.md tests/test_stage2.py
git commit -m "feat(stage2): add gene-based anti-collapse hints" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Done when:

- anti-collapse prompt is family-aware, not just formula-string-aware

---

### Task 5: Prove behavior with a real single-run experiment

**Files:**
- No code changes required unless verification fails
- If docs need updates after proof, modify:
  - `docs/overview/06_runtime-concessions.md`
  - `docs/plans/current_implementation_plan.md`

**Step 1: Run targeted unit/regression suite**

Run:

```bash
env UV_CACHE_DIR=/tmp/pixiu-uv-cache uv run pytest -q tests/test_formula_gene.py tests/test_stage2.py tests/test_constraints.py
```

Expected:
- pass

**Step 2: Run real fast-feedback proof**

Run:

```bash
env UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_HUMAN_GATE_AUTO_ACTION=approve uv run pixiu run --mode single --island momentum
```

Expected:
- run completes
- a new `data/experiment_runs/{run_id}/round_000.json` exists

**Step 3: Inspect proof artifact**

Check at minimum:

- `factor_algebra` novelty reasons use gene-aware semantics
- `factor_algebra` duplicate/same-family waste moves in the right direction
- `llm_usage.call_events_round` still shows `provider=openai`, `model=gpt-5.4`

**Step 4: Record follow-up truth**

If this slice changes the runtime tradeoff, update:

- `docs/overview/06_runtime-concessions.md`
- `docs/plans/current_implementation_plan.md`

Only if the evidence justifies it.

**Step 5: Commit**

```bash
git add docs/overview/06_runtime-concessions.md docs/plans/current_implementation_plan.md
git commit -m "docs: record factor gene v1 progress" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

Skip this commit if no docs changed.

Done when:

- `factor_gene v1` is backed by both tests and a real experiment artifact

---

## Scope Guardrails

- Do not add schema-level gene objects in v1
- Do not widen this beyond `factor_algebra`
- Do not introduce continuous similarity metrics
- Do not build a curator, RL loop, or archive policy
- Do not turn Stage 2 into a multi-turn open-ended chat loop
- Do not replace current portfolio logic with gene-based optimization in this slice
