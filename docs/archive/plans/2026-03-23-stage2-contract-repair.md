# Stage 2 Contract Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the remaining Stage 2 contract repair so generated hypotheses, injected subspace context, and retry feedback all align with the current Qlib runtime truth before the next controlled experiment run.

**Architecture:** Keep Stage 3 as the canonical hard gate and keep the new Stage 2 local pre-screen unchanged. This plan only removes remaining Stage 2 prompt/context drift: stale subspace wording, stale normalization guidance, and weak retry feedback that still permits obviously invalid Qlib expressions. Scope stays inside Stage 2 generation and its tests.

**Tech Stack:** Python, pytest, LangChain message prompts, Qlib expression runtime, Markdown skill assets

---

### Task 1: Remove stale Stage 2 subspace semantics

**Files:**
- Modify: `src/scheduling/subspace_context.py`
- Test: `tests/test_stage2.py`

**Step 1: Add/extend failing tests**
- Assert generated subspace context no longer mentions cross-sectional operators.
- Assert symbolic mutation context no longer recommends `zscore` / `minmax`.

**Step 2: Update context builders**
- Change factor algebra context so operator guidance matches current runtime truth.
- Change symbolic mutation normalization wording so it only references approved runtime-normalization patterns.

**Step 3: Run focused tests**
- `uv run pytest -q tests/test_stage2.py -k "subspace_context or injects"`

**Step 4: Commit**
- `git add src/scheduling/subspace_context.py tests/test_stage2.py`
- `git commit -m "fix(stage2): align subspace context with runtime truth"`

### Task 2: Tighten Stage 2 prompt and retry contract

**Files:**
- Modify: `src/agents/researcher.py`
- Test: `tests/test_stage2.py`

**Step 1: Add/extend failing tests**
- Assert the Stage 2 system/user prompt explicitly discourages invalid `Rank(expr)` and unsupported normalization/operator shortcuts.
- Assert retry feedback steers away from locally rejected validator/novelty patterns.

**Step 2: Update prompt contract**
- Strengthen `ALPHA_RESEARCHER_SYSTEM_PROMPT` and retry feedback wording around canonical safe patterns.
- Keep output schema and Stage 3 gate unchanged.

**Step 3: Run focused tests**
- `uv run pytest -q tests/test_stage2.py -k "researcher|local_prescreen|feedback|prompt"`

**Step 4: Commit**
- `git add src/agents/researcher.py tests/test_stage2.py`
- `git commit -m "fix(stage2): tighten prompt contract against invalid formulas"`

### Task 3: Re-run controlled Stage 2 gate

**Files:**
- None

**Step 1: Run targeted regression**
- `uv run pytest -q tests/test_stage2.py tests/test_skills.py`

**Step 2: Run real single-island verification**
- `env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 uv run pixiu run --mode single --island momentum`

**Step 3: Inspect Stage 2 artifact**
- Confirm local rejection mix continues to move waste out of Stage 3.
- Confirm no stale subspace/prompt wording remains in generated prompt path.

**Step 4: Commit**
- `git add -A`
- `git commit -m "test(stage2): verify contract repair against controlled run"`
