"""Mutable orchestrator runtime state.

This module owns the singleton scheduler, run id, and graph cache used by the
orchestrator entry points. Keeping it separate from the package root makes the
compatibility layer thinner and easier to reason about.
"""
from __future__ import annotations

from typing import Optional

from src.factor_pool.pool import get_factor_pool
from src.factor_pool.scheduler import IslandScheduler

_scheduler = None
_current_run_id: Optional[str] = None
_graph = None
_graph_config = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        pool = get_factor_pool()
        _scheduler = IslandScheduler(pool=pool)
    return _scheduler


def peek_scheduler():
    return _scheduler


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def reset_scheduler() -> None:
    set_scheduler(None)


def get_current_run_id() -> Optional[str]:
    return _current_run_id


def set_current_run_id(run_id: Optional[str]) -> None:
    global _current_run_id
    _current_run_id = run_id


def reset_current_run_id() -> None:
    set_current_run_id(None)


def get_graph():
    return _graph


def set_graph(graph) -> None:
    global _graph
    _graph = graph


def reset_graph() -> None:
    set_graph(None)


def get_graph_config() -> dict:
    return _graph_config or {}


def set_graph_config(config: dict | None) -> None:
    global _graph_config
    _graph_config = config


def reset_runtime_state() -> None:
    reset_scheduler()
    reset_current_run_id()
    reset_graph()
    set_graph_config(None)
