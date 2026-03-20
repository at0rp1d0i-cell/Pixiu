"""Helpers for isolating orchestrator module state in tests."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class OrchestratorStateSnapshot:
    graph: Any
    scheduler: Any
    current_run_id: str | None
    context_scheduler: Any
    context_current_run_id: str | None
    max_rounds: int
    report_every_n_rounds: int
    active_islands: list[str]
    reports_dir: Path
    get_state_store: Any
    graph_cache: Any
    graph_config: Any


def _snapshot_orchestrator_state() -> OrchestratorStateSnapshot:
    import src.core.orchestrator as orch
    import src.core.orchestrator._context as orch_context
    import src.core.orchestrator.graph as graph_mod

    return OrchestratorStateSnapshot(
        graph=orch._graph,
        scheduler=orch._scheduler,
        current_run_id=orch._current_run_id,
        context_scheduler=orch_context._scheduler,
        context_current_run_id=orch_context._current_run_id,
        max_rounds=orch.MAX_ROUNDS,
        report_every_n_rounds=orch.REPORT_EVERY_N_ROUNDS,
        active_islands=list(orch.ACTIVE_ISLANDS),
        reports_dir=orch.REPORTS_DIR,
        get_state_store=orch.get_state_store,
        graph_cache=graph_mod._graph,
        graph_config=graph_mod._graph_config,
    )


def _restore_orchestrator_state(snapshot: OrchestratorStateSnapshot) -> None:
    import src.core.orchestrator as orch
    import src.core.orchestrator._context as orch_context
    import src.core.orchestrator.graph as graph_mod

    orch._graph = snapshot.graph
    orch._scheduler = snapshot.scheduler
    orch._current_run_id = snapshot.current_run_id
    orch_context._scheduler = snapshot.context_scheduler
    orch_context._current_run_id = snapshot.context_current_run_id
    orch.MAX_ROUNDS = snapshot.max_rounds
    orch.REPORT_EVERY_N_ROUNDS = snapshot.report_every_n_rounds
    orch.ACTIVE_ISLANDS = list(snapshot.active_islands)
    orch.REPORTS_DIR = snapshot.reports_dir
    orch.get_state_store = snapshot.get_state_store
    graph_mod._graph = snapshot.graph_cache
    graph_mod._graph_config = snapshot.graph_config


@contextmanager
def isolated_orchestrator_state(
    *,
    max_rounds: int | None = None,
    report_every_n_rounds: int | None = None,
    active_islands: Iterable[str] | None = None,
    reports_dir: str | Path | None = None,
) -> Iterator[None]:
    """Temporarily reset orchestrator globals and restore them after the test."""
    import src.core.orchestrator as orch
    import src.core.orchestrator._context as orch_context
    import src.core.orchestrator.graph as graph_mod

    snapshot = _snapshot_orchestrator_state()
    try:
        orch._graph = None
        orch._scheduler = None
        orch._current_run_id = None
        orch_context._scheduler = None
        orch_context._current_run_id = None
        graph_mod._graph = None
        graph_mod._graph_config = None

        if max_rounds is not None:
            orch.MAX_ROUNDS = max_rounds
        if report_every_n_rounds is not None:
            orch.REPORT_EVERY_N_ROUNDS = report_every_n_rounds
        if active_islands is not None:
            orch.ACTIVE_ISLANDS = list(active_islands)
        if reports_dir is not None:
            orch.REPORTS_DIR = Path(reports_dir)

        yield
    finally:
        _restore_orchestrator_state(snapshot)
