# Doc System Restructure Implementation Plan

**Goal:** Reorganize Pixiu documentation into `overview + design + archive`, while preserving a single readable entrypoint and reducing old/new mixing.

**Architecture:** Active architecture truth moves into `docs/overview/` and `docs/design/`. `docs/archive/` becomes the only home for historical specs and notes. `docs/specs/` is downgraded to a compatibility entrypoint only.

**Tech Stack:** Markdown docs, repository metadata files, path/link updates via search-and-replace and manual edits.

---

### Task 1: Establish New Top-Level Documentation Layers

**Files:**
- Create: `docs/overview/README.md`
- Create: `docs/design/README.md`
- Modify: `docs/README.md`

**Step 1: Add the new overview/design entrypoints**

Create the two README files and rewrite the root docs README to explain:
- what belongs in `overview`
- what belongs in `design`
- what belongs in `plans`, `research`, `reference`, and `archive`

**Step 2: Verify the new root reading order**

Run: `rg -n "overview/|design/" docs/README.md docs/overview/README.md docs/design/README.md`
Expected: all three files point to the new paths.

### Task 2: Migrate Core Overview Documents

**Files:**
- Move: `docs/PROJECT_SNAPSHOT.md` -> `docs/overview/project-snapshot.md`
- Move: `docs/specs/v2_architecture_overview.md` -> `docs/overview/architecture-overview.md`
- Move: `docs/specs/v2_spec_execution_audit.md` -> `docs/overview/spec-execution-audit.md`

**Step 1: Move and rewrite overview docs**

Rewrite them so they:
- use the new path scheme
- link each top-level architecture part to `docs/design/`
- keep summary status concise

**Step 2: Verify links**

Run: `rg -n "docs/design/|Design Links" docs/overview`
Expected: overview docs reference design docs directly.

### Task 3: Migrate Active Design Documents

**Files:**
- Move all active current specs from `docs/specs/` into `docs/design/`
- Rename Stage 2 to `docs/design/stage-2-hypothesis-expansion.md`
- Move `docs/specs/v2_misc_todos.md` -> `docs/plans/engineering-debt.md`

**Step 1: Move files**

Preserve content initially, then adjust the most important docs:
- `authority-model.md`
- `stage-2-hypothesis-expansion.md`
- `stage-45-golden-path.md`
- `test-pipeline.md`

**Step 2: Rewrite Stage 2 framing**

Update Stage 2 so it is no longer only “parallel note generation”. It should define the five exploration subspaces and position Stage 2 as a hypothesis expansion engine.

**Step 3: Verify active design inventory**

Run: `find docs/design -maxdepth 1 -type f | sort`
Expected: design directory contains the active design corpus.

### Task 4: Archive Old Spec Structure

**Files:**
- Move: `docs/specs/archive/*` -> `docs/archive/specs/`
- Modify: `docs/archive/README.md`
- Modify: `docs/specs/README.md`

**Step 1: Move archived specs under docs/archive**

Keep `docs/specs/README.md` only as a compatibility notice pointing to `docs/design/README.md`.

**Step 2: Verify archive isolation**

Run: `find docs/archive -maxdepth 3 -type f | sort`
Expected: archived specs sit under `docs/archive/specs/`.

### Task 5: Update Repository-Wide References

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: active files under `docs/`
- Modify: selected code comments/tests that still point to old spec paths

**Step 1: Replace active path references**

Update repository guidance so canonical docs are:
- `docs/README.md`
- `docs/overview/README.md`
- `docs/overview/architecture-overview.md`
- `docs/overview/spec-execution-audit.md`
- `docs/design/test-pipeline.md`

**Step 2: Verify there are no stale active references**

Run: `rg -n "docs/specs/v2_|docs/PROJECT_SNAPSHOT.md" README.md AGENTS.md docs src tests`
Expected: only archive notes or explicit compatibility notices remain.

### Task 6: Final Validation

**Files:**
- Inspect: `docs/README.md`
- Inspect: `docs/overview/README.md`
- Inspect: `docs/design/README.md`

**Step 1: Validate the new reading path**

Run:

```bash
sed -n '1,220p' docs/README.md
sed -n '1,220p' docs/overview/README.md
sed -n '1,260p' docs/design/README.md
```

Expected: the reading order is coherent and does not bounce between old and new structures.

**Step 2: Summarize remaining gaps**

Record which design docs still need deeper rewriting, especially:
- `stage-2-hypothesis-expansion`
- `architecture-overview`
- commercialization and data-source positioning
