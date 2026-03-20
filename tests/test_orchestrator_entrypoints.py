from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import src.core.orchestrator as orchestrator
import src.core.orchestrator.graph as graph_mod
from src.core.orchestrator._entrypoints import run_evolve, run_single

pytestmark = pytest.mark.unit


class _FakeGraph:
    def __init__(self, result: dict):
        self.ainvoke = AsyncMock(return_value=result)


async def _run_entrypoint(monkeypatch, orchestrator_state_guard, entrypoint, kwargs, result):
    with orchestrator_state_guard():
        graph = _FakeGraph(result)
        update_calls: list[tuple[str, dict]] = []

        monkeypatch.setattr(orchestrator, "get_graph", lambda: graph)
        monkeypatch.setattr(orchestrator, "_ensure_run_record", lambda mode="adhoc": "run-123")
        monkeypatch.setattr(orchestrator, "_current_run_id", None)
        monkeypatch.setattr(orchestrator, "MAX_ROUNDS", orchestrator.MAX_ROUNDS)
        monkeypatch.setattr(orchestrator, "ACTIVE_ISLANDS", list(orchestrator.ACTIVE_ISLANDS))
        monkeypatch.setattr(graph_mod, "_graph_config", None)
        monkeypatch.setattr(
            orchestrator,
            "_update_run_record",
            lambda stage, **fields: update_calls.append((stage, fields)),
        )

        await entrypoint(**kwargs)

        return graph, update_calls, orchestrator.MAX_ROUNDS, list(orchestrator.ACTIVE_ISLANDS)


@pytest.mark.asyncio
async def test_run_evolve_records_completed_final_status(monkeypatch, orchestrator_state_guard):
    graph, update_calls, max_rounds, active_islands = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        run_evolve,
        {"rounds": 9, "islands": ["momentum", "valuation"]},
        {"current_round": 7},
    )

    assert max_rounds == 9
    assert active_islands == ["momentum", "valuation"]
    assert graph.ainvoke.await_count == 1

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_round"] == 0
    assert update_calls[0] == (
        orchestrator.NODE_MARKET_CONTEXT,
        {"status": "running", "current_round": 0},
    )

    final_stage, final_fields = update_calls[-1]
    assert final_stage == orchestrator.NODE_LOOP_CONTROL
    assert final_fields["status"] == "completed"
    assert final_fields["current_round"] == 7
    assert final_fields["finished_at"] is not None
    assert final_fields["last_error"] is None


@pytest.mark.asyncio
async def test_run_single_records_stopped_final_status(monkeypatch, orchestrator_state_guard):
    graph, update_calls, max_rounds, _ = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        run_single,
        {"island": "sentiment"},
        {"current_round": 3, "human_decision": "stop"},
    )

    assert max_rounds == 1
    assert graph.ainvoke.await_count == 1

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_round"] == 0
    assert initial_state["current_island"] == "sentiment"
    assert update_calls[0] == (
        orchestrator.NODE_MARKET_CONTEXT,
        {"status": "running", "current_round": 0},
    )

    final_stage, final_fields = update_calls[-1]
    assert final_stage == orchestrator.NODE_LOOP_CONTROL
    assert final_fields["status"] == "stopped"
    assert final_fields["current_round"] == 3
    assert final_fields["finished_at"] is not None
    assert final_fields["last_error"] is None


@pytest.mark.asyncio
async def test_run_single_records_failed_final_status(monkeypatch, orchestrator_state_guard):
    graph, update_calls, max_rounds, _ = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        run_single,
        {"island": "momentum"},
        {"current_round": 2, "last_error": "boom", "error_stage": orchestrator.NODE_PORTFOLIO},
    )

    assert max_rounds == 1
    assert graph.ainvoke.await_count == 1

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_island"] == "momentum"

    final_stage, final_fields = update_calls[-1]
    assert final_stage == orchestrator.NODE_PORTFOLIO
    assert final_fields["status"] == "failed"
    assert final_fields["current_round"] == 2
    assert final_fields["finished_at"] is not None
    assert final_fields["last_error"] == "boom"
