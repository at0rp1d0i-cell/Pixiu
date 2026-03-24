# Stage 2 Diversity Control Layer Implementation Plan

**Goal:** Add a formal `diversity control layer` inside Stage 2 local prescreen so `factor_algebra` same-family collapse is handled before Stage 3 novelty.

**Architecture:** Keep this slice fully local to `AlphaResearcher._local_prescreen_notes()`. Reuse existing `factor_gene` metadata and `FactorPool` access. Add a new `anti_collapse` filter category with two checks: same-batch family budget and historical saturated-family gate.

**Tech Stack:** Python 3.12, existing `factor_gene` helpers, `FactorPool`, pytest unit tests, Pixiu single-run artifact proof.

---

## Fixed Decisions

- `factor_algebra` only
- no schema changes
- no scheduler changes
- `anti_collapse` is a new Stage 2 local filter category
- order is `validator -> anti_collapse -> novelty`
- validation mode is `fast feedback`

---

## Task 1: Add factor_algebra diversity control helpers

**Files:**
- Modify: `src/agents/researcher.py`
- Test: `tests/test_stage2.py`

**Implement:**

- helper to count historical variants by `family_gene_key`
- helper to apply same-batch family budget
- helper to decide historical saturation for `factor_algebra`

**Rules:**

- same batch: keep at most 1 note per `family_gene_key`
- history: reject when same island already has at least 2 variants of that `family_gene_key`

**Done when:**

- targeted tests cover same-batch budget and historical saturation
- non-`factor_algebra` notes remain unchanged

---

## Task 2: Wire diversity control into local prescreen diagnostics

**Files:**
- Modify: `src/agents/researcher.py`
- Test: `tests/test_stage2.py`

**Implement:**

- insert diversity control after validator and before novelty
- add `anti_collapse` to:
  - `rejection_counts_by_filter`
  - `rejection_counts_by_filter_and_subspace`
  - `sample_rejections`
- keep factor-gene keys in rejection samples

**Done when:**

- diagnostics clearly separate `anti_collapse` from `novelty`
- existing Stage 2 mapping logic still works

---

## Verification

Run:

```bash
uv run pytest -q tests/test_stage2.py -k "anti_collapse or factor_gene or diversity"
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_HUMAN_GATE_AUTO_ACTION=approve uv run pixiu run --mode single --island momentum
```

Expect:

- targeted tests pass
- artifact contains `anti_collapse`
- `factor_algebra` novelty pressure shifts downward relative to the previous baseline

---

## Commit

```bash
git add src/agents/researcher.py tests/test_stage2.py docs/plans/2026-03-24-stage2-diversity-control-layer-design.md docs/plans/2026-03-24-stage2-diversity-control-layer-implementation.md
git commit -m "feat(stage2): add diversity control layer" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```
