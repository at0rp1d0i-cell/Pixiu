# Stage 2 Controlled Factor Algebra Family Steering Implementation Plan

<execution_handoff>
  <executor>codex</executor>
  <primary_mode>subagent-driven-development</primary_mode>
  <alternate_mode>executing-plans</alternate_mode>
  <rule>Execute task-by-task with verification after each task.</rule>
</execution_handoff>

**Goal:** Reduce the next stable controlled-run Stage 2 blocker by steering single-note `factor_algebra` generation away from `ratio_momentum`.

**Architecture:** Reuse the existing `fast_feedback` family-steering pattern inside `src/agents/researcher.py`, but scope it narrowly to `controlled_run + factor_algebra + requested_note_count=1`. Keep enforcement local to Stage 2 pre-screen and record the profile-specific pause as a runtime concession.

**Tech Stack:** Python, pytest, uv, Pixiu Stage 2 runtime, repo-backed docs

---

### Task 1: Add failing tests for controlled-run family steering

**Files:**
- Modify: `tests/test_stage2.py`
- Reference: `src/agents/researcher.py`

**Step 1: Write the failing test**

Add a controlled-run test that submits a `factor_algebra` note with `transform_family=ratio_momentum` and asserts the note is rejected as `value_density` with a controlled-run specific reason.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_ratio_momentum_family"`

Expected: FAIL because the controlled-run policy rejection does not exist yet.

### Task 2: Implement the minimal controlled-run steering

**Files:**
- Modify: `src/agents/researcher.py`
- Test: `tests/test_stage2.py`

**Step 1: Add profile helpers/constants**

Add the smallest profile helpers needed to express:

- controlled-run single-note `factor_algebra` family pause list
- controlled-run prompt focus section

**Step 2: Reuse the local prescreen policy hook**

Generalize the existing fast-feedback-only policy rejection so it can also reject controlled-run single-note `ratio_momentum` as `value_density`.

**Step 3: Add prompt steering on first attempt**

Inject the controlled-run focus section into the first-attempt factor-algebra prompt so the model is told not to emit `ratio_momentum` in this bounded profile.

**Step 4: Run tests**

Run: `uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`

Expected: PASS

### Task 3: Record the concession

**Files:**
- Modify: `docs/overview/06_runtime-concessions.md`

**Step 1: Update the Stage 2 generation concession**

Record that controlled-run single-note mode now carries a temporary `factor_algebra` family pause for the current blocker family.

**Step 2: Keep the rationale bounded**

State explicitly that this is an `experiment_concession`, not a final generation architecture.

### Task 4: Verify the real surface

**Files:**
- Reference only: `data/experiment_runs/**`
- Write later: `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md`

**Step 1: Run targeted pytest**

Run: `uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_ratio_momentum_family or factor_algebra_controlled_run_single_note_full_rejection_skips_retry"`

Expected: PASS

**Step 2: Run controlled single**

Run:

```bash
env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum
```

Expected: command succeeds and writes a fresh `round_000.json`.

**Step 3: Compare against prior controlled-run baseline**

Compare the new artifact against:

- `data/experiment_runs/20260329_224455/round_000.json`
- `data/experiment_runs/20260330_114204/round_000.json`

Success means the new factor-algebra blocker is no longer dominated by `ratio_momentum` novelty/alignment.

### Task 5: Write implementation report

**Files:**
- Create: `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-family-steering.md`

**Step 1: Capture what changed**

List code files, doc files, and the controlled-run artifact used as proof.

**Step 2: Capture why**

Tie the slice back to the repeated controlled-run residual pattern.

**Step 3: Capture verification**

Include exact commands and outcomes.

**Step 4: Capture open items**

State whether self-evolve smoke is unlocked or still blocked by another Stage 2 residual.
