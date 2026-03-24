# Stage1 Telemetry And Ledger V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Stage 1 reliability telemetry to round artifacts and extend runtime LLM accounting from run aggregates to call-level events.

**Architecture:** Keep both changes additive. Stage 1 telemetry should flow through `AgentState -> ExperimentLogger` and stay in experiment artifacts first, not the API surface. LLM accounting should keep the current aggregate ledger, add call-event truth underneath it, and let existing snapshot/control-plane readers continue to consume aggregates.

**Tech Stack:** Python, Pydantic, pytest, LangChain callback hooks, existing control-plane/experiment artifact JSON payloads

---

### Task 1: Stage 1 Reliability Telemetry V1

**Files:**
- Modify: `src/agents/market_analyst.py`
- Modify: `src/schemas/state.py`
- Modify: `src/core/orchestrator/nodes/stage1.py`
- Modify: `src/core/experiment_logger.py`
- Test: `tests/test_stage1.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write failing tests for Stage 1 telemetry shape**

Add/extend tests that prove:
- Stage 1 records blocking/enrichment tool stats
- forced finalization is visible
- degraded reason is visible
- round artifact emits `stage1_reliability`

**Step 2: Run focused tests and confirm failure**

Run:
```bash
uv run pytest -q tests/test_stage1.py tests/test_orchestrator.py
```

**Step 3: Implement telemetry capture in Stage 1**

Add a compact diagnostics payload with:
- `blocking_required`
- `blocking_tools_expected`
- `blocking_tools_used`
- `enrichment_tools_used`
- `tool_calls_total`
- `tool_timeouts_total`
- `tool_errors_total`
- `finalization_forced`
- `degraded`
- `degrade_reason`
- `tool_stats`
- `sample_failures`

Route it through `AgentState` and include it in experiment snapshots.

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest -q tests/test_stage1.py tests/test_orchestrator.py
```

**Step 5: Commit**

```bash
git add src/agents/market_analyst.py src/schemas/state.py src/core/orchestrator/nodes/stage1.py src/core/experiment_logger.py tests/test_stage1.py tests/test_orchestrator.py
git commit -m "feat(stage1): add reliability telemetry to experiment artifacts"
```

### Task 2: Runtime Token Ledger V2 Call Events

**Files:**
- Modify: `src/llm/usage_ledger.py`
- Modify: `src/llm/openai_compat.py`
- Modify: `src/core/experiment_logger.py`
- Modify: `src/core/orchestrator/control_plane.py`
- Modify: `src/schemas/control_plane.py`
- Modify: `src/control_plane/state_store.py`
- Modify: `src/api/server.py`
- Test: `tests/test_llm_usage_ledger.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write failing tests for call-level events**

Add/extend tests that prove:
- each runtime LLM callback records a `call_event`
- aggregates still update correctly
- experiment artifacts expose round/cumulative aggregates plus call samples/events as designed

**Step 2: Run focused tests and confirm failure**

Run:
```bash
uv run pytest -q tests/test_llm_usage_ledger.py tests/test_state_store.py tests/test_orchestrator.py
```

**Step 3: Implement additive call-event truth**

Add per-call event recording with fields:
- `call_id`
- `run_id`
- `stage`
- `round`
- `agent_role`
- `llm_profile`
- `provider`
- `model`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `latency_ms`
- `success`
- `error_class`
- `error_message`
- `timestamp`

Keep current run aggregates stable for existing consumers.

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest -q tests/test_llm_usage_ledger.py tests/test_state_store.py tests/test_orchestrator.py
```

**Step 5: Commit**

```bash
git add src/llm/usage_ledger.py src/llm/openai_compat.py src/core/experiment_logger.py src/core/orchestrator/control_plane.py src/schemas/control_plane.py src/control_plane/state_store.py src/api/server.py tests/test_llm_usage_ledger.py tests/test_state_store.py tests/test_orchestrator.py
git commit -m "feat(ledger): add call-level runtime usage events"
```

### Task 3: Integration Verification

**Files:**
- Verify only; no planned write set

**Step 1: Run focused verification**

Run:
```bash
uv run pytest -q tests/test_stage1.py tests/test_orchestrator.py tests/test_llm_usage_ledger.py tests/test_state_store.py
```

**Step 2: Run harness sanity checks**

Run:
```bash
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/experiment_preflight.py --json
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin uv run python scripts/run_experiment_harness.py --json
```

**Step 3: Commit integration adjustments if needed**

```bash
git add <touched files>
git commit -m "test(harness): verify telemetry and ledger integration"
```
