# Codex Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a repository-scoped Codex workflow layer so Pixiu development defaults to source-backed, harness-first, concession-aware execution with consistent worker briefs.

**Architecture:** Create a repo-local `/.codex/` workflow layer that lives alongside `AGENTS.md` and project docs. The implementation stays documentation-only: a tiny entry document plus four project-specific skills, then a minimal `AGENTS.md` hook that points future Codex sessions to the new workflow layer.

**Tech Stack:** Markdown documentation, repo-local `.codex/skills`, existing `AGENTS.md`, Pixiu docs hierarchy

---

### Task 1: Add the repository-scoped Codex entrypoint

**Files:**
- Create: `.codex/README.md`
- Create: `.codex/skills/.gitkeep`
- Modify: `AGENTS.md`

**Step 1: Write the entrypoint draft**

Create `.codex/README.md` with:
- one-paragraph purpose
- a short “when to use which skill” list
- a short rule that repo-local skills override ad hoc habits

**Step 2: Add the skills directory skeleton**

Create:
- `.codex/skills/.gitkeep`

This keeps the repo-local workflow layer visible even before all skills exist.

**Step 3: Add the minimal AGENTS hook**

Modify `AGENTS.md` by adding one short section that:
- says the repo contains project-local Codex workflow skills under `/.codex/skills/`
- points to `/.codex/README.md`
- does not duplicate the skill bodies

**Step 4: Verify the files render cleanly**

Run:

```bash
sed -n '1,220p' .codex/README.md
sed -n '1,240p' AGENTS.md
```

Expected:
- the new section is short
- `AGENTS.md` is still a map, not a new encyclopedia

**Step 5: Commit**

```bash
git add .codex/README.md .codex/skills/.gitkeep AGENTS.md
git commit -m "docs: add codex workflow entrypoint" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 2: Create `pixiu-official-source-gate`

**Files:**
- Create: `.codex/skills/pixiu-official-source-gate/SKILL.md`

**Step 1: Write the trigger-focused frontmatter**

Frontmatter must clearly say this skill applies when:
- changing behavior tied to `Qlib / Tushare / OpenAI / Chroma / MCP`
- relying on external semantics or API behavior

**Step 2: Write the minimal workflow**

The body should enforce:
- identify the external truth source
- check official docs or local runtime truth first
- record what source was used
- do not patch implementation if no source was found

Include explicit Pixiu examples:
- Qlib operator signatures
- Tushare field availability
- OpenAI model/runtime behavior

**Step 3: Add a “what counts as evidence” section**

Require one of:
- official docs
- local installed runtime behavior
- existing canonical project docs that already cite the source

**Step 4: Verify structure**

Run:

```bash
sed -n '1,260p' .codex/skills/pixiu-official-source-gate/SKILL.md
```

Expected:
- concise trigger
- no long theory dump
- concrete stop condition when evidence is missing

**Step 5: Commit**

```bash
git add .codex/skills/pixiu-official-source-gate/SKILL.md
git commit -m "docs: add official source gate skill" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 3: Create `pixiu-harness-first`

**Files:**
- Create: `.codex/skills/pixiu-harness-first/SKILL.md`

**Step 1: Write the frontmatter**

Trigger on:
- mainline runtime changes
- experiment pipeline changes
- stage behavior changes
- bugfixes that need runtime proof

**Step 2: Write the workflow**

Require the worker to state before coding:
- `fast feedback` or `controlled run`
- which profile or command will validate the change
- what artifact or output proves success

**Step 3: Encode Pixiu-specific validation anchors**

Reference:
- `scripts/experiment_preflight.py`
- `scripts/run_experiment_harness.py`
- `data/experiment_runs/.../round_*.json`

**Step 4: Add “do not do this” guidance**

Forbid:
- direct long-run testing as first validation
- claiming success from logs alone without artifact evidence

**Step 5: Verify structure**

Run:

```bash
sed -n '1,260p' .codex/skills/pixiu-harness-first/SKILL.md
```

Expected:
- clear validation-first workflow
- explicit distinction between `fast feedback` and `controlled run`

**Step 6: Commit**

```bash
git add .codex/skills/pixiu-harness-first/SKILL.md
git commit -m "docs: add harness-first workflow skill" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 4: Create `pixiu-runtime-concession-check`

**Files:**
- Create: `.codex/skills/pixiu-runtime-concession-check/SKILL.md`

**Step 1: Write the frontmatter**

Trigger on:
- new fallback
- auto-approve or special-case gate
- degraded mode
- temporary limitation
- deferred runtime behavior

**Step 2: Write the workflow**

Require the worker to decide:
- is this a concession or a normal design choice
- if concession, which type applies
- whether [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md) must be updated

**Step 3: Encode the Pixiu-specific types**

Include:
- `experiment_concession`
- `mvp_simplification`
- `compat_bridge`
- `deferred`

**Step 4: Add a short “not everything goes into the ledger” section**

Exclude:
- generic engineering debt
- already-archived compat layers
- speculative futures work

**Step 5: Verify structure**

Run:

```bash
sed -n '1,260p' .codex/skills/pixiu-runtime-concession-check/SKILL.md
```

Expected:
- ties directly to the runtime concessions ledger
- distinguishes concession from drift

**Step 6: Commit**

```bash
git add .codex/skills/pixiu-runtime-concession-check/SKILL.md
git commit -m "docs: add runtime concession check skill" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 5: Create `pixiu-worker-brief`

**Files:**
- Create: `.codex/skills/pixiu-worker-brief/SKILL.md`

**Step 1: Write the frontmatter**

Trigger on:
- any worker delegation
- multi-step execution in this repo
- bounded implementation tasks

**Step 2: Write the required brief template**

Require:
- `Task`
- `Context`
- `Constraints`
- `Output`
- `Done When`

**Step 3: Add Pixiu-specific guardrails**

Require the brief to state:
- allowed write set
- which truth docs are relevant
- which verification command is required
- whether the task may update docs

**Step 4: Add a “bad brief vs good brief” section**

Use one short Pixiu example showing:
- vague prompt that invites agent hallucination
- corrected prompt with bounded ownership

**Step 5: Verify structure**

Run:

```bash
sed -n '1,260p' .codex/skills/pixiu-worker-brief/SKILL.md
```

Expected:
- the template is copy-pasteable
- the skill is concise enough for frequent use

**Step 6: Commit**

```bash
git add .codex/skills/pixiu-worker-brief/SKILL.md
git commit -m "docs: add worker brief skill" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 6: Wire the workflow docs together

**Files:**
- Modify: `.codex/README.md`
- Modify: `AGENTS.md`
- Modify: `docs/plans/2026-03-23-codex-workflow-design.md`

**Step 1: Re-read the entrypoint and AGENTS hook**

Make sure the final wording:
- points to the four skills
- does not restate the whole workflow
- still keeps `AGENTS.md` compact

**Step 2: Reconcile naming and wording**

Ensure the skill names in:
- `.codex/README.md`
- `AGENTS.md`
- `docs/plans/2026-03-23-codex-workflow-design.md`

all match exactly.

**Step 3: Verify the links**

Run:

```bash
rg -n "pixiu-official-source-gate|pixiu-harness-first|pixiu-runtime-concession-check|pixiu-worker-brief" .codex AGENTS.md docs/plans/2026-03-23-codex-workflow-design.md
```

Expected:
- each skill name appears consistently

**Step 4: Commit**

```bash
git add .codex/README.md AGENTS.md docs/plans/2026-03-23-codex-workflow-design.md
git commit -m "docs: wire codex workflow references" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```

### Task 7: Validate the workflow layer

**Files:**
- Review only

**Step 1: Validate file structure**

Run:

```bash
find .codex -maxdepth 3 -type f | sort
```

Expected:
- repo-local `.codex/README.md`
- four skill folders
- one `SKILL.md` per skill

**Step 2: Validate skill frontmatter**

Run:

```bash
rg -n "^---$|^name:|^description:" .codex/skills/*/SKILL.md
```

Expected:
- every skill has valid frontmatter

**Step 3: Validate formatting**

Run:

```bash
git diff --check
```

Expected:
- no whitespace or merge-marker issues

**Step 4: Do one manual forward-read**

Read:

```bash
sed -n '1,220p' .codex/README.md
sed -n '1,220p' .codex/skills/pixiu-official-source-gate/SKILL.md
sed -n '1,220p' .codex/skills/pixiu-harness-first/SKILL.md
```

Expected:
- the workflow is understandable without opening chat history

**Step 5: Final commit**

```bash
git add .codex AGENTS.md
git commit -m "docs: finalize repo codex workflow layer" -m "Co-authored-by: OpenAI Codex <noreply@openai.com>"
```
