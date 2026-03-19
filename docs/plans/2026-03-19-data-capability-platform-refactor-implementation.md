# Data Capability Platform Refactor Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a canonical formula capability kernel so field specs, operator specs, SubspaceRegistry templates, and Stage 2 prompt guidance stop drifting apart.

**Architecture:** Start with the narrowest safe slice of Epic A: keep current runtime field coverage semantics, but extract a canonical `field + operator` manifest and make `src.formula.capabilities`, `SubspaceRegistry`, and Stage 2 prompt generation all consume it. Fix the known bad negative-`Ref` examples in code paths that currently mislead Stage 2. Leave full dataset registry/readiness layering for the next slice.

**Tech Stack:** Python 3.12, Pydantic/dataclasses, pytest, uv

---

### Task 1: Add failing tests for canonical formula manifest

**Files:**
- Modify: `tests/test_formula_capabilities.py`
- Modify: `tests/test_stage2.py`
- Modify: `tests/test_scheduler.py`

**Step 1: Write the failing tests**

Add tests that assert:
- canonical operator specs use `Ref($field, N)` instead of negative offsets
- Stage 2 system prompt now injects a runtime operator block
- `SubspaceRegistry` primitives and factor-algebra context no longer emit negative-`Ref` examples
- `get_runtime_formula_capabilities()` still exposes the same available fields and operators when fed the same fake `features/` tree

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_formula_capabilities.py tests/test_stage2.py tests/test_scheduler.py
```

Expected:
- tests fail because the canonical operator manifest and prompt/context wiring do not yet exist

**Step 3: Commit**

Do not commit yet. Continue to Task 2 once the red test is observed.

### Task 2: Introduce the canonical formula manifest

**Files:**
- Create: `src/formula/manifest.py`
- Modify: `src/formula/capabilities.py`
- Modify: `src/formula/__init__.py`

**Step 1: Write minimal implementation**

Create `src/formula/manifest.py` with:
- `FormulaFieldSpec`
- `FormulaOperatorSpec`
- canonical field specs for:
  - `qlib_price_volume`
  - `fina_indicator`
  - `daily_basic`
- canonical operator specs for the operator templates exposed to Stage 2

Refactor `src.formula.capabilities` to import from this manifest while preserving its public API.

**Step 2: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_formula_capabilities.py tests/test_stage2.py tests/test_scheduler.py
```

Expected:
- PASS

**Step 3: Commit**

Do not commit yet. Continue to Task 3 while the write set is still local and coherent.

### Task 3: Rewire Stage 2 and exploration templates to consume the manifest

**Files:**
- Modify: `src/agents/researcher.py`
- Modify: `src/schemas/exploration.py`
- Modify: `src/scheduling/subspace_context.py`
- Modify: `knowledge/skills/constraints/qlib_formula_syntax.md`

**Step 1: Refactor implementation**

Change Stage 2 and exploration wiring so that:
- Stage 2 prompt receives both field and operator capability blocks
- `SubspaceRegistry` primitive templates are generated from the canonical manifest
- `build_factor_algebra_context()` no longer emits future-data examples
- the most misleading static skill example is updated to the canonical syntax

**Step 2: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_formula_capabilities.py tests/test_stage2.py tests/test_prefilter.py tests/test_scheduler.py tests/test_constraints.py
```

Expected:
- PASS

### Task 4: Update planning docs and verify the first slice

**Files:**
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/current_implementation_plan.md`
- Optionally modify: `docs/plans/2026-03-19-data-capability-platform-refactor-design.md`

**Step 1: Update planning docs**

Record that Epic A slice 1 establishes the canonical formula capability kernel and that full dataset registry/readiness layering remains the next slice.

**Step 2: Run verification**

Run:

```bash
uv run pytest -q tests/test_formula_capabilities.py tests/test_stage2.py tests/test_prefilter.py tests/test_scheduler.py tests/test_constraints.py
uv run ruff check src/formula/manifest.py src/formula/capabilities.py src/formula/__init__.py src/agents/researcher.py src/schemas/exploration.py src/scheduling/subspace_context.py tests/test_formula_capabilities.py tests/test_stage2.py tests/test_scheduler.py knowledge/skills/constraints/qlib_formula_syntax.md
git diff --check
```

Expected:
- all tests pass
- ruff passes
- no diff formatting errors

**Step 3: Commit**

```bash
git add src/formula/manifest.py src/formula/capabilities.py src/formula/__init__.py src/agents/researcher.py src/schemas/exploration.py src/scheduling/subspace_context.py tests/test_formula_capabilities.py tests/test_stage2.py tests/test_scheduler.py knowledge/skills/constraints/qlib_formula_syntax.md docs/plans/2026-03-19-data-capability-platform-refactor-implementation.md docs/plans/current_implementation_plan.md docs/plans/README.md
git commit -m "refactor(formula): add canonical capability manifest"
```

### Scope Guardrails

- Do not include `moneyflow`, `stk_limit`, or `moneyflow_hsgt` in this first implementation slice.
- Do not change Stage 2/3 runtime behavior beyond making field/operator truth canonical and removing wrong examples.
- Do not expand the approved operator set in this slice.
- Do not rewrite download scripts or conversion scripts in this slice.

### Handoff Notes

After this slice lands, the next Epic A slice should add:
- canonical dataset registry under `src/data_pipeline/`
- explicit staged/materialized/runtime-available readiness helpers
- non-formula dataset registry entries
- capability reporting for Stage 1 / regime data

---

## Status Update

- `2026-03-19` Slice 1 已完成：canonical formula capability kernel（field/operator manifest + 错误示例清理）已落地。
- `2026-03-19` Slice 2 已完成：`qlib_price_volume / fina_indicator / daily_basic` 的 dataset registry + readiness 已落地，field truth 已从 `src/formula/` 下沉到 `src/data_pipeline/`。
- 下一刀应聚焦 non-formula dataset readiness 与 Stage 1 / regime 数据能力报告，而不是继续扩字段表。
