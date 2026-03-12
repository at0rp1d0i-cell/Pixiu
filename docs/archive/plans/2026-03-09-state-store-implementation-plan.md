# State Store Implementation Plan

**Goal:** Build a minimal SQLite-backed `state_store` so orchestrator, CLI, and API can read and write a stable control-plane data model.

**Architecture:** Add a small control-plane schema and repository layer, then wire orchestrator writes and CLI/API reads to it without replacing LangGraph checkpoint or `FactorPool`. Keep the first version limited to run metadata, snapshots, artifact refs, and human decisions.

**Tech Stack:** Python, Pydantic, sqlite3, pytest, FastAPI, Typer

---

### Task 1: Add Control-Plane Schemas

**Files:**
- Create: `src/schemas/control_plane.py`
- Modify: `src/schemas/__init__.py`
- Test: `tests/test_schemas.py`

**Step 1: Write the failing test**

Add schema assertions for:

```python
run = RunRecord(run_id="r1", mode="single", status="running", current_round=1, current_stage="coder")
snapshot = RunSnapshot(run_id="r1", approved_notes_count=1, backtest_reports_count=0, verdicts_count=0, awaiting_human_approval=False)
artifact = ArtifactRecord(run_id="r1", kind="cio_report", ref_id="rep1", path="/tmp/report.md")
decision = HumanDecisionRecord(run_id="r1", action="approve")
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_schemas.py`
Expected: FAIL with missing import or missing schema

**Step 3: Write minimal implementation**

Create the four Pydantic models with tight field names and no extra behavior.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_schemas.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/schemas/control_plane.py src/schemas/__init__.py tests/test_schemas.py
git commit -m "feat: add control plane schemas"
```

### Task 2: Add SQLite State Store

**Files:**
- Create: `src/control_plane/state_store.py`
- Test: `tests/test_state_store.py`

**Step 1: Write the failing test**

Cover:

- `create_run`
- `update_run`
- `write_snapshot`
- `append_artifact`
- `append_human_decision`
- `get_latest_run`
- `get_snapshot`
- `list_reports`

Use a temp SQLite path and assert the latest report artifact is returned in descending order.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_state_store.py`
Expected: FAIL with missing module or methods

**Step 3: Write minimal implementation**

Use `sqlite3` from stdlib. Create tables lazily in constructor. Keep SQL small and explicit.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_state_store.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/control_plane/state_store.py tests/test_state_store.py
git commit -m "feat: add sqlite state store"
```

### Task 3: Wire Orchestrator Writes

**Files:**
- Modify: `src/core/orchestrator.py`
- Test: `tests/test_orchestrator_state_store.py`

**Step 1: Write the failing test**

Assert that a minimal run:

- creates a run record
- updates stage names
- writes a snapshot
- records a `cio_report` artifact when report stage completes

Use monkeypatch to inject a temp state store.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_orchestrator_state_store.py`
Expected: FAIL because orchestrator does not write control-plane state

**Step 3: Write minimal implementation**

Add thin helpers in orchestrator to:

- create/update current run
- write snapshot after Stage 4 / 5
- append artifact on report generation

Avoid mixing SQL directly into nodes.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_orchestrator_state_store.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/core/orchestrator.py tests/test_orchestrator_state_store.py
git commit -m "feat: persist orchestrator run state"
```

### Task 4: Wire API and CLI Reads

**Files:**
- Modify: `src/api/server.py`
- Modify: `src/cli/main.py`
- Test: `tests/test_api_state_store.py`

**Step 1: Write the failing test**

Cover:

- `/api/status` reads `latest_run + snapshot`
- `/api/reports` reads report artifacts from `state_store`

Keep CLI verification light; at minimum verify helper functions can read the latest run/report without `FactorPool`.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_api_state_store.py`
Expected: FAIL because API still reads `FactorPool` only

**Step 3: Write minimal implementation**

Switch the read path to:

1. try `state_store`
2. if empty, return empty state or explicit placeholder

Do not silently fabricate report data from `FactorPool`.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_api_state_store.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/server.py src/cli/main.py tests/test_api_state_store.py
git commit -m "feat: read control plane state from state store"
```

### Task 5: Update Docs and Run Local Verification

**Files:**
- Modify: `docs/specs/v2_spec_execution_audit.md`
- Modify: `docs/PROJECT_SNAPSHOT.md`
- Modify: `docs/plans/current_implementation_plan.md`
- Modify: `docs/specs/v2_test_pipeline.md`

**Step 1: Update docs**

Record:

- `state_store` exists
- CLI/API now read control-plane state
- new local integration tests

**Step 2: Run focused verification**

Run:

```bash
pytest -q tests/test_state_store.py tests/test_orchestrator_state_store.py tests/test_api_state_store.py
pytest -q tests -m "smoke or unit"
pytest -q tests -m "integration and not live and not e2e"
```

Expected: PASS

**Step 3: Commit**

```bash
git add docs/specs/v2_spec_execution_audit.md docs/PROJECT_SNAPSHOT.md docs/plans/current_implementation_plan.md docs/specs/v2_test_pipeline.md
git commit -m "docs: document state store control plane"
```
