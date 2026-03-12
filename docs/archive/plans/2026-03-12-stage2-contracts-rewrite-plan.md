# Stage 2 And Contracts Rewrite Plan

> Archived on 2026-03-12 after the Stage 2 and contracts document rewrite was completed.

**Goal:** Rewrite the Stage 2 design and interface contracts so they reflect the current authority model, hypothesis-expansion framing, and transition-state object boundaries.

**Architecture:** Keep the runtime-reality documents honest while defining a cleaner target object model. `stage-2-hypothesis-expansion.md` will describe the new cognitive search space and outputs; `interface-contracts.md` will define canonical research objects plus the current transitional compatibility layer.

**Tech Stack:** Markdown design docs, overview cross-links, audit/status updates.

---

### Task 1: Rewrite Stage 2 Design Around Hypothesis Expansion

**Files:**
- Modify: `docs/design/stage-2-hypothesis-expansion.md`

**Step 1: Replace old “batch note generation” framing**

Write the document so Stage 2 is defined as a `Hypothesis Expansion Engine`, not just a parallel note generator.

**Step 2: Define the five exploration subspaces**

Add explicit sections for:
- factor algebra search
- symbolic factor mutation
- cross-market pattern mining
- economic narrative mining
- regime-conditional factors

**Step 3: Define outputs and transition state**

Specify:
- current runtime output (`FactorResearchNote`)
- target canonical outputs (`Hypothesis`, `StrategySpec`)
- relation to `exploration_questions`, Stage 3 gate, and Stage 4 execute path

### Task 2: Rewrite Interface Contracts Around Canonical Objects

**Files:**
- Modify: `docs/design/interface-contracts.md`

**Step 1: Replace the old schema dump format**

Turn the document into a contract guide:
- canonical object list
- object roles
- current runtime mapping
- compatibility layer notes

**Step 2: Freeze the core objects**

Define at least:
- `Hypothesis`
- `StrategySpec`
- `FilterReport`
- `BacktestRun`
- `EvaluationReport`
- `FailureConstraint`
- `CriticVerdict`
- `FactorPoolRecord`
- `RunRecord/RunSnapshot`

**Step 3: Add transition notes**

Make clear where the code still uses:
- `FactorResearchNote`
- current `BacktestReport`
- current `CriticVerdict`
- `AgentState`

### Task 3: Sync Overview and Audit

**Files:**
- Modify: `docs/overview/architecture-overview.md`
- Modify: `docs/overview/spec-execution-audit.md`

**Step 1: Tighten overview wording**

Ensure overview references the updated object model consistently.

**Step 2: Update audit status**

Mark where Stage 2 design is ahead of runtime and where contracts are still transitional.

### Task 4: Validate Doc Navigation

**Files:**
- Inspect: `docs/design/stage-2-hypothesis-expansion.md`
- Inspect: `docs/design/interface-contracts.md`
- Inspect: `docs/overview/architecture-overview.md`
- Inspect: `docs/overview/spec-execution-audit.md`

**Step 1: Verify cross-links**

Run:

```bash
rg -n "Hypothesis|StrategySpec|FailureConstraint|FactorResearchNote|BacktestRun|EvaluationReport" docs/design docs/overview
```

Expected: the new object model is visible in both design and overview layers.
