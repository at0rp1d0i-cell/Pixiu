# Stage 2 Controlled Factor Algebra Allowlist Implementation Plan

<execution_handoff>
  <executor>codex</executor>
  <primary_mode>subagent-driven-development</primary_mode>
  <alternate_mode>executing-plans</alternate_mode>
  <rule>Execute task-by-task with verification after each task.</rule>
</execution_handoff>

**Goal:** Stabilize controlled single-note factor_algebra generation by allowing only `mean_spread` in the current bounded profile.

**Architecture:** Replace the current controlled-run paused-family blacklist with a bounded allowlist inside `src/agents/researcher.py`, then verify the real Stage 2 rejection mix on a fresh controlled-run single artifact.

**Tech Stack:** Python, pytest, uv, Pixiu Stage 2 runtime, repo-backed docs

---

### Task 1: Update tests to express the allowlist

**Files:**
- Modify: `tests/test_stage2.py`
- Reference: `src/agents/researcher.py`

Add or update controlled-run tests so `ratio_momentum` and `volume_confirmation` are both rejected by policy in single-note mode, and the prompt clearly advertises a `mean_spread` allowlist.

### Task 2: Implement the bounded allowlist

**Files:**
- Modify: `src/agents/researcher.py`

Replace the current controlled-run paused-family logic with an allowlist check for `mean_spread` only. Keep the change scoped to:

- `controlled_run`
- `factor_algebra`
- `PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1`

### Task 3: Update the concession ledger

**Files:**
- Modify: `docs/overview/06_runtime-concessions.md`

Record that the current controlled single-note factor-algebra path is temporarily narrowed to `mean_spread`.

### Task 4: Verify the real surface

**Files:**
- Write later: `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md`

Run:

```bash
uv run pytest -q tests/test_stage2.py -k "controlled_run_rejects_ratio_momentum_family or controlled_run_rejects_volume_confirmation_family or controlled_run_single_note_injects_focus_section"
env HOME=/tmp/pixiu-home UV_CACHE_DIR=/tmp/pixiu-uv-cache QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_EXPERIMENT_PROFILE_KIND=controlled_run PIXIU_STAGE2_REQUESTED_NOTE_COUNT=1 PIXIU_STAGE1_ENABLE_ENRICHMENT=0 uv run pixiu run --mode single --island momentum
```

Compare against:

- `data/experiment_runs/20260330_125645/round_000.json`

### Task 5: Write implementation report

Create:

- `docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md`

Include what changed, why, verification, and whether evolve-smoke is finally unlocked.
