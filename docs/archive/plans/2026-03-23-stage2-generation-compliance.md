# Stage 2 Generation Compliance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Stage 2 deliver higher-quality candidates by enforcing the same canonical math-safety and novelty rules before Stage 3, without weakening the Stage 3 hard gate.

**Architecture:** Keep Stage 3 as the source-of-truth hard gate. Stage 2 becomes factor-pool-aware and adds a local pre-screen using the same validator/novelty logic. If a generated batch is entirely rejected locally, allow at most one bounded retry with compact rejection feedback; otherwise pass through only locally-approved notes.

**Tech Stack:** Python, Pydantic, LangGraph-style typed state, pytest

---

### Task 1: Lock the Stage 2 contract

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `src/core/orchestrator/nodes/stage2.py`
- Modify: `src/schemas/stage_io.py`
- Modify: `src/schemas/state.py`

**Step 1: Add a typed Stage 2 diagnostics payload**
- Record generated count, delivered count, local rejection counts, retry count, and sample rejection reasons.

**Step 2: Pass FactorPool into Stage 2 generation**
- Use orchestrator runtime/control-plane access instead of leaving `AlphaResearcher.factor_pool=None`.

**Step 3: Keep Stage 3 unchanged**
- Do not loosen validator/novelty rules or bypass Stage 3.

### Task 2: Add local Stage 2 pre-screen

**Files:**
- Modify: `src/agents/researcher.py`
- Test: `tests/test_stage2.py`

**Step 1: Reuse canonical validator and novelty checks**
- Use the existing canonical validator path for math/field/operator safety.
- Use the existing novelty filter against the current factor pool.

**Step 2: Filter generated notes locally**
- Keep only notes that pass local validator + novelty checks.
- Record rejection reasons into Stage 2 diagnostics.

**Step 3: Add one bounded retry**
- Retry only when a batch is fully rejected locally.
- Feed a compact rejection summary back into the next prompt.
- Stop after one retry.

### Task 3: Surface diagnostics and verify behavior

**Files:**
- Modify: `src/core/experiment_logger.py`
- Test: `tests/test_stage2.py`
- Test: `tests/integration/test_stage1_to_stage3.py`

**Step 1: Write Stage 2 diagnostics into round artifacts**
- Keep payload compact and machine-readable.

**Step 2: Add regression tests**
- FactorPool is passed into Stage 2 generation.
- Unsafe formulas are locally rejected before handoff.
- Duplicate formulas are locally rejected when factor pool says so.
- Fully rejected first batch triggers exactly one retry.
- Partially approved batch does not retry.

**Step 3: Run focused verification**
- `uv run pytest -q tests/test_stage2.py tests/integration/test_stage1_to_stage3.py`

### Task 4: Run experiment gate again

**Files:**
- None

**Step 1: Re-run harness preflight path**
- `env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json`

**Step 2: Compare Stage 2/3 waste**
- Confirm Stage 2 diagnostics show local rejections.
- Confirm Stage 3 still acts as the final hard gate.
