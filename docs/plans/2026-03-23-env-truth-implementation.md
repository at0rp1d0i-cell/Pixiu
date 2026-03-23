# Environment Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a worktree-safe, machine-scoped environment truth layer with source tracing for doctor and experiment preflight.

**Architecture:** Keep one shared loader in `src/core/env.py`. Scripts resolve environment through that helper, with precedence `process_env > user_runtime_env > repo_env > default/profile`. Limit the first slice to runtime env loading and debugging visibility.

**Tech Stack:** Python, pytest, python-dotenv, Pixiu scripts/runtime helpers

---

### Task 1: Add failing tests for layered env resolution

**Files:**
- Modify: `tests/test_env.py`

**Step 1: Write failing tests**

Add tests that cover:

- explicit env beating user runtime env and repo `.env`
- user runtime env beating repo `.env`
- source metadata reporting the winning layer

**Step 2: Run the focused tests to verify failure**

Run:

```bash
uv run pytest -q tests/test_env.py
```

Expected: new tests fail because layered resolution/source tracing does not exist yet.

**Step 3: Commit**

```bash
git add tests/test_env.py
git commit -m "test(env): add layered runtime env expectations"
```

### Task 2: Implement shared layered env helpers

**Files:**
- Modify: `src/core/env.py`
- Test: `tests/test_env.py`

**Step 1: Write minimal implementation**

Add shared helpers that:

- resolve user runtime env path (`~/.config/pixiu/runtime.env` by default)
- load user runtime env and repo `.env` without overriding explicit env
- return merged values plus source metadata
- optionally apply merged values to a target environment mapping

Keep the existing explicit-path helper behavior available for current callers.

**Step 2: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_env.py
```

Expected: env tests pass.

**Step 3: Commit**

```bash
git add src/core/env.py tests/test_env.py
git commit -m "feat(env): add layered runtime env resolution"
```

### Task 3: Rewire doctor to shared env truth and surface sources

**Files:**
- Modify: `scripts/doctor.py`
- Possibly modify: `README.md`
- Possibly modify: `.env.example`
- Add/modify tests if a focused script test already exists

**Step 1: Update doctor entry/setup**

Make `doctor` resolve layered env through `src/core/env.py` rather than directly loading only repo `.env`.

Surface critical source info for at least:

- `QLIB_DATA_DIR`
- `TUSHARE_TOKEN`

Keep the current blocking/core/full behavior unchanged.

**Step 2: Run targeted verification**

Run:

```bash
uv run pytest -q tests/test_env.py tests/test_script_entrypoints.py
```

Expected: pass.

**Step 3: Commit**

```bash
git add scripts/doctor.py README.md .env.example tests/test_script_entrypoints.py
git commit -m "feat(doctor): use layered env truth and trace sources"
```

### Task 4: Rewire experiment preflight/harness to shared env truth

**Files:**
- Modify: `scripts/experiment_preflight.py`
- Modify: `scripts/run_experiment_harness.py`
- Modify: `tests/test_experiment_preflight.py`
- Modify: `tests/test_experiment_harness.py`

**Step 1: Update preflight**

Make preflight:

- resolve env via the shared helper
- preserve explicit env override precedence
- include source metadata in structured output for critical values

**Step 2: Update harness**

Make harness apply the resolved env truth before runtime entrypoints execute, so live runs inherit the same shared machine config.

**Step 3: Run focused verification**

Run:

```bash
uv run pytest -q tests/test_env.py tests/test_experiment_preflight.py tests/test_experiment_harness.py tests/test_script_entrypoints.py
```

Expected: pass.

**Step 4: Commit**

```bash
git add scripts/experiment_preflight.py scripts/run_experiment_harness.py tests/test_experiment_preflight.py tests/test_experiment_harness.py tests/test_script_entrypoints.py
git commit -m "feat(harness): share layered env truth across preflight and runtime"
```

### Task 5: Verify with real script invocations

**Files:**
- No code changes required unless verification fails

**Step 1: Run real invocation checks**

Run:

```bash
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/experiment_preflight.py --json
uv run python scripts/doctor.py --mode core
```

Expected:

- `preflight` reports the correct `QLIB_DATA_DIR` source/value
- `doctor` shows stable source tracing for critical keys

**Step 2: Final commit if needed**

If verification required follow-up fixes, commit them with a focused message.

### Scope Guardrails

- Do not create a general application settings system
- Do not add secret storage/encryption
- Do not expand CLI surface
- Do not change Stage 1/Stage 3 runtime logic
- Keep source tracing minimal and debugging-oriented
