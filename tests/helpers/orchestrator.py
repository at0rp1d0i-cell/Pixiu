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
    max_rounds: int
    report_every_n_rounds: int
    active_islands: list[str]
    reports_dir: Path
    graph_config: Any


def _snapshot_orchestrator_state() -> OrchestratorStateSnapshot:
    from src.core.orchestrator import config as orch_config
    from src.core.orchestrator import runtime as orch_runtime
    return OrchestratorStateSnapshot(
        graph=orch_runtime.get_graph(),
        scheduler=orch_runtime.peek_scheduler(),
        current_run_id=orch_runtime.get_current_run_id(),
        max_rounds=orch_config.MAX_ROUNDS,
        report_every_n_rounds=orch_config.REPORT_EVERY_N_ROUNDS,
        active_islands=list(orch_config.ACTIVE_ISLANDS),
        reports_dir=orch_config.REPORTS_DIR,
        graph_config=orch_runtime.get_graph_config(),
    )


def _restore_orchestrator_state(snapshot: OrchestratorStateSnapshot) -> None:
    from src.core.orchestrator import config as orch_config
    from src.core.orchestrator import runtime as orch_runtime

    orch_runtime.set_scheduler(snapshot.scheduler)
    orch_runtime.set_current_run_id(snapshot.current_run_id)
    orch_runtime.set_graph(snapshot.graph)
    orch_runtime.set_graph_config(snapshot.graph_config)
    orch_config.MAX_ROUNDS = snapshot.max_rounds
    orch_config.REPORT_EVERY_N_ROUNDS = snapshot.report_every_n_rounds
    orch_config.ACTIVE_ISLANDS = list(snapshot.active_islands)
    orch_config.REPORTS_DIR = snapshot.reports_dir


@contextmanager
def isolated_orchestrator_state(
    *,
    max_rounds: int | None = None,
    report_every_n_rounds: int | None = None,
    active_islands: Iterable[str] | None = None,
    reports_dir: str | Path | None = None,
) -> Iterator[None]:
    """Temporarily reset orchestrator globals and restore them after the test."""
    from src.core.orchestrator import config as orch_config
    from src.core.orchestrator import runtime as orch_runtime

    snapshot = _snapshot_orchestrator_state()
    try:
        orch_runtime.reset_runtime_state()

        if max_rounds is not None:
            orch_config.MAX_ROUNDS = max_rounds
        if report_every_n_rounds is not None:
            orch_config.REPORT_EVERY_N_ROUNDS = report_every_n_rounds
        if active_islands is not None:
            orch_config.ACTIVE_ISLANDS = list(active_islands)
        if reports_dir is not None:
            orch_config.REPORTS_DIR = Path(reports_dir)

        yield
    finally:
        _restore_orchestrator_state(snapshot)
