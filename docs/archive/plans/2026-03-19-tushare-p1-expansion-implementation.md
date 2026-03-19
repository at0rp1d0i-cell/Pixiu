# Tushare P1 Expansion Implementation Plan

Status: historical
Owner: coordinator
Last Reviewed: 2026-03-19

> Archived on 2026-03-19. The staged `moneyflow` / `stk_limit` pipelines and adjacent
> data-contract cleanup have already landed. Remaining data-surface follow-up is now
> tracked centrally in `docs/plans/current_implementation_plan.md`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Pixiu's local Tushare data surface beyond `daily_basic`/`fina_indicator` with the next highest-value daily datasets, while keeping runtime contracts and docs aligned.

**Architecture:** Add thin staging-first download pipelines for P1 daily datasets, keep runtime capabilities dynamic, and update docs/cleanup work in parallel while long-running downloads proceed. Do not widen Stage 2/3 contracts until local data coverage is real.

**Tech Stack:** Python 3.12, uv, Tushare Pro, pandas, parquet staging, pytest

---

### Task 1: Finalize current capability-contract cleanup

**Files:**
- Modify: `src/agents/prefilter.py`
- Test: `tests/test_prefilter.py`

**Step 1: Write or extend a failing test**

Add a test proving `PreFilter` can reuse a provided `FormulaCapabilities` instead of rescanning runtime state independently.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_prefilter.py -k capability`

**Step 3: Implement minimal cleanup**

Thread `FormulaCapabilities` through `PreFilter` so `Validator` and related checks share one canonical capability snapshot.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_prefilter.py -k capability`

**Step 5: Commit**

Commit together with adjacent data-contract cleanup if the diff stays small.

### Task 2: Add Tushare `moneyflow` staging pipeline

**Files:**
- Create: `src/data_pipeline/moneyflow.py`
- Create: `scripts/download_moneyflow_data.py`
- Create: `tests/test_moneyflow_pipeline.py`
- Modify: `tests/test_script_entrypoints.py`

**Step 1: Write the failing tests**

Cover schema normalization, deterministic output path, and CLI entrypoint importability.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_moneyflow_pipeline.py tests/test_script_entrypoints.py -k moneyflow`

**Step 3: Implement the pipeline**

Create a daily segmented downloader that stages per-symbol parquet files under `data/fundamental_staging/moneyflow/`.

**Step 4: Run tests**

Run: `uv run pytest -q tests/test_moneyflow_pipeline.py tests/test_script_entrypoints.py -k moneyflow`

**Step 5: Start the real download**

Run the script in the background after local tests pass.

### Task 3: Add Tushare `stk_limit` staging pipeline

**Files:**
- Create: `src/data_pipeline/stk_limit.py`
- Create: `scripts/download_stk_limit_data.py`
- Create: `tests/test_stk_limit_pipeline.py`
- Modify: `tests/test_script_entrypoints.py`

**Step 1: Write the failing tests**

Cover schema normalization, staging path, and CLI entrypoint importability.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_stk_limit_pipeline.py tests/test_script_entrypoints.py -k stk_limit`

**Step 3: Implement the pipeline**

Create a daily segmented downloader that stages per-trading-day parquet files under `data/fundamental_staging/stk_limit/`.

**Step 4: Run tests**

Run: `uv run pytest -q tests/test_stk_limit_pipeline.py tests/test_script_entrypoints.py -k stk_limit`

**Step 5: Start the real download**

Run the script in the background after local tests pass.

### Task 4: Update reference docs and active data-source docs

**Files:**
- Modify: `docs/reference/tushare-dataset-matrix.md`
- Modify: `docs/reference/data-download-guide.md`
- Modify: `docs/design/15_data-sources.md`
- Modify: `docs/reference/README.md`

**Step 1: Update the docs**

Reflect the new P1 pipelines, clarify what is staged vs runtime-available, and add official-source links.

**Step 2: Run a lightweight link and formatting check**

Run: `git diff --check`

### Task 5: Audit active plans/docs during downloads

**Files:**
- Modify as needed: `docs/plans/*`, `docs/archive/plans/*`

**Step 1: Identify stale active plans**

Move plans to archive only when they are clearly completed or superseded.

**Step 2: Apply minimal cleanup**

Keep active plans aligned with current work; do not rewrite unrelated documents.

**Step 3: Verify**

Run: `git diff --check`

### Task 6: Full verification and checkpoint commit

**Files:**
- Modify: relevant files from Tasks 1-5

**Step 1: Run focused verification**

Run:
- `uv run pytest -q tests/test_prefilter.py tests/test_moneyflow_pipeline.py tests/test_stk_limit_pipeline.py tests/test_script_entrypoints.py`
- `uv run pytest -q tests/test_env.py tests/test_fundamental_pipeline.py tests/test_daily_basic_pipeline.py tests/test_moneyflow_hsgt_pipeline.py`

**Step 2: Run formatting diff check**

Run: `git diff --check`

**Step 3: Commit**

Use a message that describes the new Tushare staging surface and include the co-author trailer.
