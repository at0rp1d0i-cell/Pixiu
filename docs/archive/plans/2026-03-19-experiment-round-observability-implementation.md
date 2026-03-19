# Experiment Round Observability Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich `data/experiment_runs/<run_id>/round_*.json` so each round explains where candidates were filtered and why executed factors failed.

**Architecture:** Keep the change local to the per-round snapshot pipeline. Stage 3 will emit lightweight prefilter diagnostics into `AgentState`, and `ExperimentLogger` will derive compact execution and judgment summaries from existing state objects without persisting full reports or verdicts.

**Tech Stack:** Python 3.12, Pydantic models, LangGraph state dicts, pytest

---

### Task 1: Define the snapshot diagnostics contract

**Files:**
- Modify: `src/schemas/state.py`
- Modify: `src/schemas/stage_io.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

Add a snapshot integration assertion that expects new top-level keys such as `prefilter`, `execution`, and `judgment`, plus nested counters for rejections and failures.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestrator.py -k snapshot`
Expected: FAIL because the snapshot JSON does not include the new diagnostics fields.

**Step 3: Write minimal implementation**

Extend `AgentState` and `PrefilterOutput` with a lightweight `prefilter_diagnostics` payload that can hold:
- `input_count`
- `approved_count`
- `rejection_counts_by_filter`
- `sample_rejections`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_orchestrator.py -k snapshot`
Expected: PASS

**Step 5: Commit**

```bash
git add src/schemas/state.py src/schemas/stage_io.py tests/test_orchestrator.py
git commit -m "test(observability): add snapshot diagnostics contract"
```

### Task 2: Emit Stage 3 diagnostics into state

**Files:**
- Modify: `src/agents/prefilter.py`
- Modify: `src/core/orchestrator/nodes/stage3.py`
- Test: `tests/test_prefilter.py`

**Step 1: Write the failing test**

Add a test that runs `PreFilter.filter_batch(...)` on notes rejected by different filters and asserts:
- per-filter rejection counters are aggregated
- approved count is recorded
- sample rejection payloads are capped and human-readable

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_prefilter.py -k diagnostics`
Expected: FAIL because `PreFilter` does not currently return diagnostics.

**Step 3: Write minimal implementation**

Accumulate rejection counts and a small sample list during `filter_batch()`, then thread that payload through the LangGraph Stage 3 node into `AgentState`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_prefilter.py -k diagnostics`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agents/prefilter.py src/core/orchestrator/nodes/stage3.py tests/test_prefilter.py
git commit -m "feat(observability): add prefilter rejection diagnostics"
```

### Task 3: Enrich round snapshots with execution and judgment summaries

**Files:**
- Modify: `src/core/experiment_logger.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

Extend the snapshot test to assert:
- `execution.backtest_reports_count`
- `execution.execution_error_count`
- `execution.executed_factor_ids_sample`
- `judgment.verdict_counts_by_decision`
- `judgment.failure_mode_counts`
- `judgment.failed_check_counts`
- `judgment.sample_failures`

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestrator.py -k snapshot`
Expected: FAIL because the snapshot payload lacks these summaries.

**Step 3: Write minimal implementation**

In `ExperimentLogger`, derive compact summaries from `state.backtest_reports` and `state.critic_verdicts` without writing full objects into the round JSON.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_orchestrator.py -k snapshot`
Expected: PASS

**Step 5: Commit**

```bash
git add src/core/experiment_logger.py tests/test_orchestrator.py
git commit -m "feat(observability): enrich experiment round snapshots"
```

### Task 4: Run the focused verification suite

**Files:**
- Test: `tests/test_prefilter.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_prefilter.py -k diagnostics
uv run pytest -q tests/test_orchestrator.py -k snapshot
uv run pytest -q tests/test_prefilter.py tests/test_orchestrator.py
```

Expected: PASS

**Step 2: Run formatting/sanity check**

Run:

```bash
git diff --check
```

Expected: no output

**Step 3: Commit**

```bash
git add docs/plans/2026-03-19-experiment-round-observability-implementation.md
git commit -m "docs(plans): add experiment observability implementation plan"
```
