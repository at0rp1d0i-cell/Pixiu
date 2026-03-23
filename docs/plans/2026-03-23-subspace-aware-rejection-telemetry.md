# Subspace-Aware Rejection Telemetry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Stage 2 and Stage 3 rejection telemetry explicitly subspace-aware so controlled experiments can answer which subspaces produce validator, novelty, and alignment waste.

**Architecture:** Keep Stage 2/3 filtering behavior unchanged. Only enrich rejection diagnostics with `exploration_subspace` and add compact aggregate counters grouped by `filter × subspace`, then persist those summaries into round artifacts.

**Tech Stack:** Python, pytest, Pydantic state models, JSON experiment artifacts

---

### Task 1: Add subspace-aware rejection diagnostics

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `src/agents/prefilter.py`
- Test: `tests/test_stage2.py`

**Step 1: Write/extend failing tests**
- Assert Stage 2 local rejection samples include `exploration_subspace`.
- Assert Stage 2 diagnostics include `rejection_counts_by_filter_and_subspace`.

**Step 2: Implement Stage 2 diagnostics enrichment**
- Add `exploration_subspace` to local rejection sample payloads.
- Add grouped counters keyed by filter and subspace.
- Keep existing counters and behavior unchanged.

**Step 3: Implement Stage 3 diagnostics enrichment**
- Add `exploration_subspace` to `sample_rejections`.
- Add grouped counters keyed by filter and subspace.
- Keep filtering logic unchanged.

**Step 4: Run focused tests**
- `uv run pytest -q tests/test_stage2.py -k "rejection or prefilter or diagnostics"`

**Step 5: Commit**
- `git add src/agents/researcher.py src/agents/prefilter.py tests/test_stage2.py`
- `git commit -m "feat(telemetry): add subspace-aware rejection diagnostics"`

### Task 2: Persist telemetry into experiment artifacts

**Files:**
- Modify: `src/core/experiment_logger.py`
- Test: `tests/test_experiment_harness.py`

**Step 1: Write/extend failing tests**
- Assert round snapshots persist the enriched Stage 2 / prefilter telemetry fields.

**Step 2: Implement minimal artifact persistence**
- Preserve `exploration_subspace` in rejection samples.
- Persist grouped `filter × subspace` counts in round JSON.
- Do not redesign artifact schema beyond these additive fields.

**Step 3: Run focused tests**
- `uv run pytest -q tests/test_stage2.py tests/test_experiment_harness.py`

**Step 4: Commit**
- `git add src/core/experiment_logger.py tests/test_experiment_harness.py`
- `git commit -m "feat(artifacts): persist subspace-aware rejection summaries"`

### Task 3: Verify against a controlled run

**Files:**
- None

**Step 1: Run targeted regression**
- `uv run pytest -q tests/test_stage2.py tests/test_experiment_harness.py`

**Step 2: Run Gate 1 harness**
- `env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json`

**Step 3: Inspect artifacts**
- Confirm `round_*.json` includes subspace-aware rejection samples and grouped counters.
- Confirm the new telemetry is sufficient to answer which subspaces dominate validator / novelty / alignment waste.

**Step 4: Commit**
- `git add -A`
- `git commit -m "test(telemetry): verify subspace-aware rejection artifacts"`
