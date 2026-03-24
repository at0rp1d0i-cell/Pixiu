# Experiment Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a script-based experiment harness with JSON-backed profiles and a fixed preflight flow for Pixiu experiments.

**Architecture:** Keep `doctor` as the environment gate, add a thin preflight script for environment/profile evaluation, and add a harness runner that executes `doctor(core) -> single -> evolve 2 rounds -> optional long run` in a fixed order. Store only experiment-discipline settings in `config/experiments/default.json`.

**Tech Stack:** Python 3.12, existing `uv run` workflow, JSON config, pytest unit/smoke tests.

---

## Slice 0: Planning and Routing

- [x] Design approved
- [x] JSON chosen over YAML for v1 profile
- [x] Script-based entry chosen over CLI

---

## Slice 1: Profile and Preflight Contract

Owner: worker

Write set:

- Create `config/experiments/default.json`
- Create `scripts/experiment_preflight.py`
- Create `tests/test_experiment_preflight.py`
- Update `tests/test_script_entrypoints.py`

Tasks:

1. Add a minimal default experiment profile JSON file
2. Add a thin profile loader with validation in `scripts/experiment_preflight.py`
3. Check required environment truth:
   - `QLIB_DATA_DIR`
   - `TUSHARE_TOKEN`
4. Invoke existing `scripts/doctor.py --mode core`
5. Return structured preflight status with explicit blocking/non-blocking semantics
6. Add targeted tests for:
   - profile parsing
   - missing env handling
   - blocking fail propagation
   - script importability

Done when:

- Preflight can answer “can this experiment start” without running the experiment itself

---

## Slice 2: Harness Runner

Owner: worker

Write set:

- Create `scripts/run_experiment_harness.py`
- Create `tests/test_experiment_harness.py`
- Reuse/patch `tests/test_script_entrypoints.py` if needed

Tasks:

1. Load the experiment profile
2. Call preflight first and stop on blocking red-light
3. Run `single` using orchestrator entrypoint
4. Run `evolve` with profile-defined preflight rounds
5. Add explicit `--long-run` gate for longer rounds
6. Print a short summary and return non-zero on failure
7. Add targeted tests for:
   - call ordering
   - stop-on-failure behavior
   - long-run requires explicit flag
   - profile overrides applied correctly

Done when:

- The harness enforces the fixed discipline without relying on manual shell choreography

---

## Slice 3: Runtime Hook-up

Owner: worker

Write set:

- `src/core/orchestrator/_entrypoints.py` only if required for clean callable reuse
- `tests/test_orchestrator_entrypoints.py` only if required for new behavior coverage
- `docs/plans/current_implementation_plan.md`

Tasks:

1. Reuse existing `run_single` / `run_evolve` entrypoints directly where possible
2. Avoid changing runtime semantics unless required for script integration
3. If new failure/report surface is needed, keep it thin and deterministic
4. Update `current_implementation_plan.md` to reflect that experiment harness became the default preflight path

Done when:

- Scripts can drive the existing runtime without widening the execution layer

---

## Slice 4: Verification and Close-out

Owner: coordinator

Verification gates:

```bash
uv run pytest -q tests/test_experiment_preflight.py tests/test_experiment_harness.py tests/test_script_entrypoints.py
uv run pytest -q tests/test_orchestrator_config.py tests/test_doctor.py tests/test_stage1.py -k "doctor or stage1"
uv run pytest -q tests -m "smoke or unit"
```

Stretch verification after implementation:

```bash
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/experiment_preflight.py
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py
```

Done when:

- The harness is test-protected
- The default experiment path is executable
- No claim is made without fresh verification evidence
