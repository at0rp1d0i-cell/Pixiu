# Data Capability Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the missing local data pipeline for P0 experimental fields and make Stage 2/3 derive field availability from the actual local Qlib feature store.

**Architecture:** Introduce a canonical formula capability module and split the experimental data pipeline into `fina_indicator` and `daily_basic` branches. Runtime field availability will be computed from local `.day.bin` coverage instead of hardcoded prompt text.

**Tech Stack:** Python 3.12, pandas, Tushare, Qlib binary feature layout, pytest

---

### Task 1: Add a canonical formula capability module

**Files:**
- Create: `src/formula/capabilities.py`
- Create: `tests/test_formula_capabilities.py`
- Modify: `src/agents/prefilter.py`
- Modify: `src/agents/researcher.py`

**Step 1: Write the failing test**

Add tests that:
- build a temporary `qlib_bin/features/` tree
- assert base fields are exposed
- assert experimental fields are exposed only after bin coverage passes the threshold
- assert the approved operator list comes from one canonical module

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_formula_capabilities.py`
Expected: FAIL because the capability module does not exist yet.

**Step 3: Write minimal implementation**

Implement:
- base field manifest
- experimental field manifest
- canonical approved operator list
- feature coverage scan helpers
- `get_runtime_formula_capabilities(...)`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_formula_capabilities.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/formula/capabilities.py tests/test_formula_capabilities.py src/agents/prefilter.py src/agents/researcher.py
git commit -m "feat(data): add runtime formula capability manifest"
```

### Task 2: Add a `daily_basic` downloader for market-derived fields

**Files:**
- Create: `scripts/download_daily_basic_data.py`
- Create: `tests/test_daily_basic_pipeline.py`

**Step 1: Write the failing test**

Add tests that cover:
- provider field selection and local output path conventions
- `circ_mv -> float_mv` mapping intent
- progress/checkpoint file naming

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_daily_basic_pipeline.py -k downloader`
Expected: FAIL because the downloader script/helpers do not exist.

**Step 3: Write minimal implementation**

Implement a Tushare `daily_basic` downloader that:
- requires `TUSHARE_TOKEN`
- stores one parquet per stock under `data/fundamental_staging/daily_basic/`
- checkpoints progress
- downloads the fields needed for:
  - `pe_ttm`
  - `pb`
  - `turnover_rate`
  - floating market value

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_daily_basic_pipeline.py -k downloader`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/download_daily_basic_data.py tests/test_daily_basic_pipeline.py
git commit -m "feat(data): add daily basic downloader"
```

### Task 3: Add `daily_basic -> qlib bin` conversion

**Files:**
- Modify: `tests/test_daily_basic_pipeline.py`
- Create: `scripts/convert_daily_basic_to_qlib.py`

**Step 1: Write the failing test**

Add tests that:
- create a tiny sample daily-basic parquet
- run conversion helpers against a toy calendar
- assert output arrays align by `trade_date`
- assert `float_mv.day.bin` is produced from the mapped source field

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_daily_basic_pipeline.py -k convert`
Expected: FAIL because the converter does not exist yet.

**Step 3: Write minimal implementation**

Implement a converter that:
- reads `data/fundamental_staging/daily_basic/*.parquet`
- aligns by trading calendar
- writes:
  - `pe_ttm.day.bin`
  - `pb.day.bin`
  - `turnover_rate.day.bin`
  - `float_mv.day.bin`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_daily_basic_pipeline.py -k convert`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/convert_daily_basic_to_qlib.py tests/test_daily_basic_pipeline.py
git commit -m "feat(data): convert daily basic fields to qlib bins"
```

### Task 4: Make Stage 2/3 consume runtime field availability

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `src/agents/prefilter.py`
- Modify: `src/schemas/exploration.py`
- Modify: `tests/test_stage2.py`
- Modify: `tests/test_prefilter.py`

**Step 1: Write the failing test**

Add tests that assert:
- Researcher prompt text reflects runtime-available fields
- Validator accepts fields from the capability module
- exploration registry does not advertise unavailable experimental fields

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_stage2.py -k available_fields
uv run pytest -q tests/test_prefilter.py -k available_fields
```

Expected: FAIL because Stage 2/3 still use hardcoded lists.

**Step 3: Write minimal implementation**

Replace the hardcoded field list and `FUNDAMENTAL_FIELDS_ENABLED` branch with capability-derived values.

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q tests/test_stage2.py -k available_fields
uv run pytest -q tests/test_prefilter.py -k available_fields
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/agents/researcher.py src/agents/prefilter.py src/schemas/exploration.py tests/test_stage2.py tests/test_prefilter.py
git commit -m "feat(runtime): derive formula fields from local capability scan"
```

### Task 5: Update docs and operational guidance

**Files:**
- Modify: `docs/reference/data-download-guide.md`
- Modify: `docs/design/15_data-sources.md`

**Step 1: Write the doc updates**

Document:
- the split between `fina_indicator` and `daily_basic`
- which P0 fields come from which source
- that runtime availability is determined by local bin coverage

**Step 2: Run link/sanity verification**

Run:

```bash
git diff --check
```

Expected: no output

**Step 3: Commit**

```bash
git add docs/reference/data-download-guide.md docs/design/15_data-sources.md
git commit -m "docs(data): document capability-driven field pipeline"
```

### Task 6: Run focused verification

**Files:**
- Test: `tests/test_formula_capabilities.py`
- Test: `tests/test_daily_basic_pipeline.py`
- Test: `tests/test_prefilter.py`
- Test: `tests/test_stage2.py`

**Step 1: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_formula_capabilities.py tests/test_daily_basic_pipeline.py tests/test_prefilter.py tests/test_stage2.py
```

Expected: PASS

**Step 2: Run broader regression**

Run:

```bash
uv run pytest -q tests/test_stage1.py tests/test_stage2.py tests/test_prefilter.py tests/test_stage4.py tests/test_llm_config.py
```

Expected: PASS

**Step 3: Final sanity**

Run:

```bash
git diff --check
```

Expected: no output

**Step 4: Commit**

```bash
git add .
git commit -m "feat(data): align runtime field capabilities with local data"
```
