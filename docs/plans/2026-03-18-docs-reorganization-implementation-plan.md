# Docs Reorganization Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild Pixiu's documentation into a human-first top layer plus a maintainable implementation layer, with numbering, standards, and clear lifecycle boundaries.

**Architecture:** First create the governing standard and the new reading-path skeleton, then renumber and clean canonical docs, then move forward-looking and stale material out of the active path, and finally run link/reference validation. The reorganization must preserve a usable docs entrypoint at every stage.

**Tech Stack:** Markdown docs, git moves, ripgrep-based validation, `git diff --check`

---

### Task 1: Establish Documentation Governance

**Files:**
- Create: `docs/00_documentation-standard.md`
- Modify: `docs/README.md`
- Reference: `docs/plans/2026-03-18-docs-reorganization-design.md`

**Step 1: Draft the documentation standard**

Write `docs/00_documentation-standard.md` with:

- directory roles for `overview / design / plans / futures / research / reference / archive`
- document levels `L1-L5`
- numbering rules
- canonical metadata header
- lifecycle and archive rules
- link/reference rules
- length/splitting rules

**Step 2: Rewrite the root docs entry**

Update `docs/README.md` so it becomes the single human-first entrypoint:

- explain the two-layer model
- point to the default reading sequence
- explain where to go for design vs plans vs futures
- stop presenting the docs tree as a flat catalog

**Step 3: Verify governance terminology is internally consistent**

Run:

```bash
rg -n 'futures|L1|L2|L3|L4|L5|Canonical|Last Reviewed' docs/00_documentation-standard.md docs/README.md
```

Expected:

- all major governance terms appear in the standard
- `docs/README.md` references the same directory names and reading path

**Step 4: Run formatting sanity check**

Run:

```bash
git diff --check
```

Expected: no whitespace or patch formatting errors

### Task 2: Build the Human-first Overview Path

**Files:**
- Move/rename: `docs/overview/01_project-snapshot.md` -> `docs/overview/01_project-snapshot.md`
- Create: `docs/overview/02_codebase-map.md`
- Move/rename: `docs/overview/03_architecture-overview.md` -> `docs/overview/03_architecture-overview.md`
- Create: `docs/overview/04_current-state.md`
- Move/rename: `docs/overview/05_spec-execution-audit.md` -> `docs/overview/05_spec-execution-audit.md`
- Modify: `docs/overview/README.md`

**Step 1: Renumber the current overview docs**

Rename the canonical overview docs into numbered files and update internal links.

**Step 2: Write `02_codebase-map.md`**

Cover:

- repo entrypoints
- Stage 1-5 code flow
- control plane
- schemas
- CLI/API entrypoints
- where a new contributor should start when debugging a given area

**Step 3: Write `04_current-state.md`**

Keep it short and human-readable:

- what works today
- what is partially implemented
- what is intentionally future work
- what changed in Phase 3/Phase 4 planning

**Step 4: Rewrite `docs/overview/README.md`**

Make it a simple overview index for the numbered set.

**Step 5: Validate the default reading path**

Run:

```bash
rg -n '01_project-snapshot|02_codebase-map|03_architecture-overview|04_current-state|05_spec-execution-audit' docs/README.md docs/overview/README.md
```

Expected:

- both entry docs point to the same ordered overview path

**Step 6: Sanity-check the main overview docs**

Run:

```bash
wc -l docs/overview/*.md
```

Expected:

- no overview file grows into an unbounded implementation dump

### Task 3: Renumber and Clean the Canonical Design Layer

**Files:**
- Modify/move numbered canonical design docs in `docs/design/`
- Modify: `docs/design/README.md`

**Target numbered set:**

- `docs/design/10_authority-model.md`
- `docs/design/11_interface-contracts.md`
- `docs/design/12_orchestrator.md`
- `docs/design/13_control-plane.md`
- `docs/design/14_factor-pool.md`
- `docs/design/15_data-sources.md`
- `docs/design/16_test-pipeline.md`
- `docs/design/20_stage-1-market-context.md`
- `docs/design/21_stage-2-hypothesis-expansion.md`
- `docs/design/22_stage-3-prefilter.md`
- `docs/design/23_stage-4-execution.md`
- `docs/design/24_stage-5-judgment.md`
- `docs/design/25_stage-45-golden-path.md`
- `docs/design/30_agent-team.md`

**Step 1: Renumber the active design docs**

Rename active canonical design docs into the numbered set and update cross-links from `docs/README.md`, `overview/`, `AGENTS.md`, and `CLAUDE.md`.

**Step 2: Add canonical metadata headers**

Add a short header block to active design docs:

- `Purpose`
- `Status`
- `Audience`
- `Canonical`
- `Owner`
- `Last Reviewed`

**Step 3: Remove obvious drift from active design docs**

Fix or mark:

- deleted entrypoint paths
- deleted compat shims
- outdated CLI/run commands
- references to nonexistent implementation files

**Step 4: Rewrite `docs/design/README.md`**

Make it a numbered reading guide rather than a loose inventory.

**Step 5: Validate deleted-path cleanup**

Run:

```bash
rg -n 'src/core/orchestrator\.py|src/agents/judgment\.py|src/agents/critic\.py|src/agents/schemas\.py|src/schemas/factor_pool_record\.py' docs AGENTS.md CLAUDE.md -g '!docs/archive/**'
```

Expected:

- matches only where explicitly discussed as deleted legacy artifacts
- no canonical design doc still treats deleted files as active truth

### Task 4: Move Forward-looking Docs out of the Active Design Layer

**Files:**
- Create: `docs/futures/README.md`
- Move/rename candidates from `docs/design/` into `docs/futures/`

**Initial candidates:**

- `docs/futures/terminal-dashboard.md`
- `docs/futures/reflection-system.md`
- `docs/futures/oos-and-generalization.md`
- `docs/futures/system-bootstrap.md`
- `docs/futures/commercialization-principles.md`

**Step 1: Create the futures landing page**

Explain that `docs/futures/` contains forward-looking designs that are not current runtime truth.

**Step 2: Move forward-looking docs**

Rename the selected docs into `docs/futures/` with consistent numbering and update inbound links.

**Step 3: Ensure active-path docs stop pointing readers at futures by default**

`docs/README.md` and `docs/overview/README.md` should mention `docs/futures/` as optional/deferred reading.

**Step 4: Validate futures separation**

Run:

```bash
rg -n 'terminal-dashboard|reflection-system|oos-and-generalization|system-bootstrap|commercialization-principles' docs/README.md docs/overview docs/design/README.md
```

Expected:

- these docs are no longer presented as core canonical reading

### Task 5: Shrink Active Plans and Clarify Plan Lifecycle

**Files:**
- Modify: `docs/plans/README.md`
- Move/archive stale plans from `docs/plans/` to `docs/archive/plans/`

**Likely active plans to keep:**

- `docs/plans/current_implementation_plan.md`
- `docs/plans/engineering-debt.md`
- current unfinished 2026-03-18 topical plans that still guide work

**Likely archive candidates:**

- superseded audits and implementation plans whose assumptions were consumed by Phase 3 refactors

**Step 1: Classify every plan as active vs archive**

Create a one-line rationale per file before moving anything.

**Step 2: Move completed or superseded plans to archive**

Preserve history, but remove them from active reading paths.

**Step 3: Rewrite `docs/plans/README.md`**

Clarify:

- what stays active
- what gets archived
- that date-prefix naming remains canonical for plan docs

**Step 4: Validate active-plan clarity**

Run:

```bash
find docs/plans -maxdepth 1 -type f | sort
```

Expected:

- the active plan set is visibly smaller and easier to scan

### Task 6: Repair Cross-links and Code-path References End-to-End

**Files:**
- Modify any docs that still reference moved files or invalid code paths

**Step 1: Fix doc-to-doc path references**

Update all links after renames/moves in `README`, `overview`, `design`, `plans`, `AGENTS.md`, and `CLAUDE.md`.

**Step 2: Fix doc-to-code path references**

Remove or rewrite references to nonexistent code paths. If a path is intentionally future work, mark it as planned rather than active.

**Step 3: Run mechanical validation for dead references**

Run:

```bash
while read -r p; do [ -e "$p" ] || echo "$p"; done < <(rg --no-filename -o 'src/[A-Za-z0-9_./-]+\.py(?:\.tpl)?' docs AGENTS.md CLAUDE.md -g '!docs/archive/**' | sort -u)
```

Expected:

- no unexpected nonexistent code paths remain in the active docs

Run:

```bash
while read -r p; do [ -e "$p" ] || echo "$p"; done < <(rg --no-filename -o 'docs/[A-Za-z0-9_./-]+\.md' docs AGENTS.md CLAUDE.md -g '!docs/archive/**' | sort -u)
```

Expected:

- no broken active doc links remain

### Task 7: Final Validation and Human Readability Pass

**Files:**
- Review all changed docs

**Step 1: Run final validation**

Run:

```bash
git diff --check
```

Expected: clean

Run:

```bash
rg -n 'src/core/orchestrator\.py|src/agents/judgment\.py|docs/PROJECT_SNAPSHOT\.md|docs/specs/v2_architecture_overview\.md|docs/specs/v2_spec_execution_audit\.md' docs AGENTS.md CLAUDE.md -g '!docs/archive/**'
```

Expected:

- no active-path stale references remain except deliberate compatibility notices

**Step 2: Perform a human readability pass**

Manually read this sequence:

1. `docs/README.md`
2. `docs/overview/01_project-snapshot.md`
3. `docs/overview/02_codebase-map.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/04_current-state.md`

Expected:

- a new reader can follow the project story without needing to guess the next file

**Step 3: Record residual risks**

If any long design docs still need a second-wave split, note them explicitly in the final report rather than leaving them implicit.

