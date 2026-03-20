"""Timing helpers for per-round stage observability."""
from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.state import AgentState


def now_counter() -> float:
    return perf_counter()


def elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000.0, 2)


def merge_stage_timing(
    state: "AgentState",
    stage: str,
    elapsed_ms_value: float,
    *,
    step_timings: dict[str, float] | None = None,
) -> dict[str, dict]:
    timings = dict(state.stage_timings)
    timings[stage] = elapsed_ms_value

    merged_step_timings = {
        key: dict(value)
        for key, value in state.stage_step_timings.items()
    }
    if step_timings:
        merged_step_timings[stage] = dict(step_timings)

    return {
        "stage_timings": timings,
        "stage_step_timings": merged_step_timings,
    }
