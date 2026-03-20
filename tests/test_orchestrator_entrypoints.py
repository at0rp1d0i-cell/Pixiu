from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import src.core.orchestrator as orchestrator
import src.core.orchestrator.graph as graph_mod
from src.core.orchestrator._entrypoints import run_evolve, run_single
from src.control_plane.state_store import StateStore

pytestmark = pytest.mark.unit


class _FakeGraph:
    def __init__(self, result: dict):
        self.ainvoke = AsyncMock(return_value=result)


class _FailingGraph:
    def __init__(self, exc: Exception):
        self.ainvoke = AsyncMock(side_effect=exc)


async def _run_entrypoint(
    monkeypatch,
    orchestrator_state_guard,
    tmp_path,
    entrypoint,
    kwargs,
    result,
):
    with orchestrator_state_guard():
        store = StateStore(tmp_path / "state_store.sqlite")
        graph = _FakeGraph(result)

        monkeypatch.setattr(orchestrator, "get_graph", lambda: graph)
        monkeypatch.setattr(orchestrator, "get_state_store", lambda: store)
        monkeypatch.setattr(orchestrator, "_current_run_id", None)
        monkeypatch.setattr(orchestrator, "MAX_ROUNDS", orchestrator.MAX_ROUNDS)
        monkeypatch.setattr(orchestrator, "ACTIVE_ISLANDS", list(orchestrator.ACTIVE_ISLANDS))
        monkeypatch.setattr(graph_mod, "_graph_config", None)

        update_calls: list[tuple[str, dict]] = []
        original_update_run = store.update_run

        def _spy_update_run(run_id: str, **fields):
            update_calls.append((run_id, dict(fields)))
            return original_update_run(run_id, **fields)

        monkeypatch.setattr(store, "update_run", _spy_update_run)

        await entrypoint(**kwargs)

        return {
            "graph": graph,
            "store": store,
            "update_calls": update_calls,
            "max_rounds": orchestrator.MAX_ROUNDS,
            "active_islands": list(orchestrator.ACTIVE_ISLANDS),
            "graph_config": graph_mod._graph_config,
        }


async def _run_failing_entrypoint(
    monkeypatch,
    orchestrator_state_guard,
    tmp_path,
    entrypoint,
    kwargs,
    exc: Exception,
):
    with orchestrator_state_guard():
        store = StateStore(tmp_path / "state_store.sqlite")
        graph = _FailingGraph(exc)

        monkeypatch.setattr(orchestrator, "get_graph", lambda: graph)
        monkeypatch.setattr(orchestrator, "get_state_store", lambda: store)
        monkeypatch.setattr(orchestrator, "_current_run_id", None)
        monkeypatch.setattr(orchestrator, "MAX_ROUNDS", orchestrator.MAX_ROUNDS)
        monkeypatch.setattr(orchestrator, "ACTIVE_ISLANDS", list(orchestrator.ACTIVE_ISLANDS))
        monkeypatch.setattr(graph_mod, "_graph_config", None)

        with pytest.raises(type(exc), match=str(exc)):
            await entrypoint(**kwargs)

        return {"graph": graph, "store": store}


@pytest.mark.asyncio
async def test_run_evolve_records_completed_final_status(monkeypatch, orchestrator_state_guard, tmp_path):
    result = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        tmp_path,
        run_evolve,
        {"rounds": 9, "islands": ["momentum", "valuation"]},
        {"current_round": 7},
    )
    graph = result["graph"]
    store = result["store"]
    update_calls = result["update_calls"]
    max_rounds = result["max_rounds"]
    active_islands = result["active_islands"]
    graph_config = result["graph_config"]

    assert max_rounds == 9
    assert active_islands == ["momentum", "valuation"]
    assert graph.ainvoke.await_count == 1
    assert graph_config is not None
    assert graph_config["configurable"]["thread_id"].startswith("pixiu_evolve_")

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_round"] == 0
    assert update_calls[0][1]["current_stage"] == orchestrator.NODE_MARKET_CONTEXT
    assert update_calls[0][1]["status"] == "running"
    assert update_calls[0][1]["current_round"] == 0

    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.mode == "evolve"
    assert latest_run.status == "completed"
    assert latest_run.current_stage == orchestrator.NODE_LOOP_CONTROL
    assert latest_run.current_round == 7
    assert latest_run.finished_at is not None
    assert latest_run.last_error is None


@pytest.mark.asyncio
async def test_run_single_records_stopped_final_status(monkeypatch, orchestrator_state_guard, tmp_path):
    result = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        tmp_path,
        run_single,
        {"island": "sentiment"},
        {"current_round": 3, "human_decision": "stop"},
    )
    graph = result["graph"]
    store = result["store"]
    max_rounds = result["max_rounds"]
    graph_config = result["graph_config"]

    assert max_rounds == 1
    assert graph.ainvoke.await_count == 1
    assert graph_config is not None
    assert graph_config["configurable"]["thread_id"].startswith("pixiu_single_sentiment_")

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_round"] == 0
    assert initial_state["current_island"] == "sentiment"
    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.mode == "single"
    assert latest_run.status == "stopped"
    assert latest_run.current_stage == orchestrator.NODE_LOOP_CONTROL
    assert latest_run.current_round == 3
    assert latest_run.finished_at is not None
    assert latest_run.last_error is None


@pytest.mark.asyncio
async def test_run_single_records_failed_final_status(monkeypatch, orchestrator_state_guard, tmp_path):
    result = await _run_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        tmp_path,
        run_single,
        {"island": "momentum"},
        {"current_round": 2, "last_error": "boom", "error_stage": orchestrator.NODE_PORTFOLIO},
    )
    graph = result["graph"]
    store = result["store"]
    max_rounds = result["max_rounds"]

    assert max_rounds == 1
    assert graph.ainvoke.await_count == 1

    initial_state = graph.ainvoke.await_args.args[0]
    assert initial_state["current_island"] == "momentum"

    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.mode == "single"
    assert latest_run.status == "failed"
    assert latest_run.current_stage == orchestrator.NODE_PORTFOLIO
    assert latest_run.current_round == 2
    assert latest_run.finished_at is not None
    assert latest_run.last_error == "boom"


@pytest.mark.asyncio
async def test_run_evolve_records_failed_status_when_graph_raises(
    monkeypatch,
    orchestrator_state_guard,
    tmp_path,
):
    result = await _run_failing_entrypoint(
        monkeypatch,
        orchestrator_state_guard,
        tmp_path,
        run_evolve,
        {"rounds": 3, "islands": ["momentum"]},
        RuntimeError("graph exploded"),
    )

    latest_run = result["store"].get_latest_run()
    assert latest_run is not None
    assert latest_run.mode == "evolve"
    assert latest_run.status == "failed"
    assert latest_run.current_stage == orchestrator.NODE_MARKET_CONTEXT
    assert latest_run.current_round == 0
    assert latest_run.finished_at is not None
    assert latest_run.last_error == "graph exploded"
