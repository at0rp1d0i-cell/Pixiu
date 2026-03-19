# Data Capability Alignment Design

**Goal:** Make Pixiu's formula-generation boundary derive from real local data capabilities instead of drifting independently across prompts, skills, registries, and validators.

**Problem Statement**

Current runtime behavior shows a systematic mismatch between what Stage 2 is encouraged to generate and what Stage 3/4 can actually execute:

- The local Qlib runtime is stable for the price-volume base fields only.
- Fundamental staging data exists locally, but the Qlib feature layer is not yet populated for the fields that Stage 2 currently advertises.
- Skills and prompt docs mention fields and operators that the validator rejects.
- The runtime does not have a single canonical source of truth for formula capabilities.

This creates token waste, noisy rejection funnels, and false "research quality" signals that are actually capability misalignment.

---

## 1. Approaches Considered

### Option A: Keep static docs and manually sync them

Change prompt text, skills, and validator lists by hand whenever data capabilities change.

Pros:
- Fastest short-term patch

Cons:
- Recreates the current failure mode
- Human synchronization burden is too high
- Easy to drift again after the next data or schema change

### Option B: Recommended — capability-driven runtime

Introduce a canonical capability layer that:

- defines the operator allowlist in one place
- scans the local Qlib feature store to determine which fields are truly available
- exposes that availability to Researcher, PreFilter, and related skills/prompt assembly

Pros:
- Matches the user's goal that skills should not hardcode availability
- Lets Pixiu adapt to actual local data readiness
- Reduces wasted generations immediately

Cons:
- Requires a small refactor across Stage 2/3
- Needs coverage thresholds so partially converted data does not appear "available" too early

### Option C: Full remote/data-source registry first

Build a large source registry with MCP/data-source metadata before changing runtime behavior.

Pros:
- Most complete long-term architecture

Cons:
- Too much surface area for the current blocker
- Does not solve the immediate local runtime mismatch fast enough

**Recommendation:** Option B.

---

## 2. Recommended Design

The implementation should be split into two tracks.

### Track A: Complete the local data pipeline

We should make the intended experimental fields real in `data/qlib_bin/features/**` before exposing them to Stage 2.

Target P0 experimental fields:

- `$roe`
- `$pb`
- `$pe_ttm`
- `$turnover_rate`
- `$float_mv`

Source mapping:

- `fina_indicator` path:
  - `$roe`
- `daily_basic` path:
  - `$pb`
  - `$pe_ttm`
  - `$turnover_rate`
  - `$float_mv` (mapped from the provider's float/circulating market value field)

This requires:

- a new `daily_basic` downloader
- a new `daily_basic -> qlib bin` converter
- a clear contract for which fields each converter can materialize

### Track B: Add a runtime capability layer

Create a canonical capability module that:

- keeps the approved operator list in one place
- scans `data/qlib_bin/features/**` and counts field coverage
- exposes "currently available formula fields" based on a minimum coverage threshold

Then connect that capability module to:

- Stage 2 prompt construction
- Stage 3 validator field checks
- exploration/subspace registry field exposure

This lets the runtime truth drive the generation truth.

---

## 3. Data Flow

### 3.1 Base price-volume path

Already present:

- `scripts/download_qlib_data.py`
- `data/qlib_bin/features/**/{open,high,low,close,volume,vwap,amount,factor}.day.bin`

### 3.2 Fundamental path

Current partial path:

- `scripts/download_fundamental_data.py`
- `data/fundamental_staging/fina_indicator/*.parquet`
- `scripts/convert_fundamental_to_qlib.py`

Needed refinement:

- document and enforce which fields that converter writes
- treat these as runtime-available only after bins exist with sufficient coverage

### 3.3 Daily-basic path

New path:

- `scripts/download_daily_basic_data.py`
- `data/fundamental_staging/daily_basic/*.parquet`
- `scripts/convert_daily_basic_to_qlib.py`
- output into `data/qlib_bin/features/{instrument}/`

---

## 4. Capability Contract

The runtime should distinguish:

- `base_fields`
  - always expected in the local Qlib store
- `experimental_fields`
  - may or may not be present locally
- `approved_operators`
  - canonical allowlist used by validator and prompt assembly

Field availability should be computed, not narrated.

Suggested rule:

- a field is "runtime available" only if its `.day.bin` coverage passes a configurable minimum threshold

This avoids advertising a field after converting only a tiny subset of instruments.

---

## 5. Operator Policy

We should not silently expand operators until they are verified against actual Qlib execution semantics.

So this change should:

- centralize the operator manifest now
- keep the currently trusted operator set stable
- stop skills/prompt text from advertising operators that are not in the canonical manifest

Operator expansion can come next, but only after verification against real Stage 4 execution.

---

## 6. Skills and Prompt Policy

Skills should describe methods, not pretend a field is always available.

Example direction:

- good:
  - "when valuation fields are available, prefer value ratios; otherwise use price-volume proxies"
- bad:
  - "use `$pb`"

The concrete available field list should be injected dynamically into the runtime prompt context, not embedded as static prose in multiple files.

---

## 7. Success Criteria

We should consider this design successful when all of the following are true:

- Pixiu can materialize the P0 experimental fields into local Qlib bins
- Stage 2 sees only fields that the local feature store actually supports
- Stage 3 validator derives allowed fields from the same capability source
- skills stop hardcoding optional field availability
- future data expansions require updating the capability manifest, not four separate prompt/skill/validator copies

---

## 8. Out of Scope for This Pass

- Full MCP/data-source marketplace design
- Stage 2 tool-calling upgrade
- Final operator expansion beyond currently trusted runtime behavior
- Refactoring all research skills in one sweep

This pass is about making local formula capability truthful and data-backed.
