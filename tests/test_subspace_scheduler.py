"""Tests for Stage 2 subspace scheduler."""

import random

import pytest

pytestmark = pytest.mark.unit

from src.schemas.hypothesis import ExplorationSubspace
from src.scheduling.subspace_scheduler import (
    SchedulerState,
    SubspaceAllocation,
    SubspaceScheduler,
)


@pytest.fixture
def scheduler() -> SubspaceScheduler:
    return SubspaceScheduler()


@pytest.fixture
def cold_state() -> SchedulerState:
    return SchedulerState()


def test_cold_start_allocation(scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """冷启动分配 = [4, 3, 3, 2]（按权重降序）"""
    allocations = scheduler.allocate(cold_state)
    quotas = [a.quota for a in allocations]
    assert quotas == [4, 3, 3, 2]


def test_min_quota_guaranteed(scheduler: SubspaceScheduler):
    """每个子空间至少获得最低配额，即使在暖启动极端情况下。"""
    # Create a warm-start state where one subspace dominates
    state = SchedulerState(
        round_number=50,
        total_generated={
            "factor_algebra": 500,
            "narrative_mining": 10,
            "symbolic_mutation": 10,
            "cross_market": 10,
        },
        total_passed={
            "factor_algebra": 400,
            "narrative_mining": 0,
            "symbolic_mutation": 0,
            "cross_market": 0,
        },
        consecutive_zeros={
            "factor_algebra": 0,
            "narrative_mining": 50,
            "symbolic_mutation": 50,
            "cross_market": 50,
        },
        warm_start=True,
    )
    random.seed(42)
    allocations = scheduler.allocate(state)

    for alloc in allocations:
        assert alloc.quota >= scheduler.MIN_QUOTA[alloc.subspace], (
            f"{alloc.subspace.value} got {alloc.quota}, "
            f"min is {scheduler.MIN_QUOTA[alloc.subspace]}"
        )


def test_total_quota_exact(scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """总配额恒等于 12。"""
    allocations = scheduler.allocate(cold_state)
    assert sum(a.quota for a in allocations) == 12


def test_total_quota_exact_warm_start(scheduler: SubspaceScheduler):
    """暖启动时总配额也恒等于 12。"""
    state = SchedulerState(
        round_number=30,
        total_generated={
            "factor_algebra": 200,
            "narrative_mining": 150,
            "symbolic_mutation": 150,
            "cross_market": 100,
        },
        total_passed={
            "factor_algebra": 100,
            "narrative_mining": 60,
            "symbolic_mutation": 30,
            "cross_market": 20,
        },
        consecutive_zeros={},
        warm_start=True,
    )
    random.seed(123)
    allocations = scheduler.allocate(state)
    assert sum(a.quota for a in allocations) == 12


def test_update_state_immutable(scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """update_state 不修改原 state。"""
    original_round = cold_state.round_number
    original_generated = dict(cold_state.total_generated)
    original_passed = dict(cold_state.total_passed)

    results = {
        ExplorationSubspace.FACTOR_ALGEBRA: (4, 2),
        ExplorationSubspace.NARRATIVE_MINING: (3, 1),
        ExplorationSubspace.SYMBOLIC_MUTATION: (3, 0),
        ExplorationSubspace.CROSS_MARKET: (2, 1),
    }
    new_state = scheduler.update_state(cold_state, results)

    # Original state is unchanged
    assert cold_state.round_number == original_round
    assert cold_state.total_generated == original_generated
    assert cold_state.total_passed == original_passed

    # New state is updated
    assert new_state.round_number == 1
    assert new_state.total_generated["factor_algebra"] == 4
    assert new_state.total_passed["factor_algebra"] == 2


def test_warm_start_transition(scheduler: SubspaceScheduler):
    """累计通过 >= 200 触发暖启动。"""
    state = SchedulerState(
        round_number=49,
        total_generated={
            "factor_algebra": 300,
            "narrative_mining": 200,
            "symbolic_mutation": 200,
            "cross_market": 100,
        },
        total_passed={
            "factor_algebra": 100,
            "narrative_mining": 50,
            "symbolic_mutation": 30,
            "cross_market": 18,
        },
        consecutive_zeros={},
        warm_start=False,
    )
    # total passed = 198, not yet warm start
    assert not state.warm_start

    results = {
        ExplorationSubspace.FACTOR_ALGEBRA: (4, 2),
        ExplorationSubspace.NARRATIVE_MINING: (3, 0),
        ExplorationSubspace.SYMBOLIC_MUTATION: (3, 0),
        ExplorationSubspace.CROSS_MARKET: (2, 0),
    }
    new_state = scheduler.update_state(state, results)
    # total passed = 198 + 2 = 200, should trigger warm start
    assert new_state.warm_start is True


def test_consecutive_zero_warning(scheduler: SubspaceScheduler):
    """连续 3 轮零通过产生警告。"""
    state = SchedulerState(
        round_number=10,
        total_generated={"cross_market": 20},
        total_passed={"cross_market": 0},
        consecutive_zeros={"cross_market": 3},
        warm_start=False,
    )
    warnings = scheduler.get_warnings(state)
    assert len(warnings) >= 1
    assert "cross_market" in warnings[0]
    assert "3" in warnings[0]


def test_thompson_sampling_allocation(scheduler: SubspaceScheduler):
    """暖启动时高 pass rate 的子空间获得更多配额。"""
    state = SchedulerState(
        round_number=50,
        total_generated={
            "factor_algebra": 500,
            "narrative_mining": 500,
            "symbolic_mutation": 500,
            "cross_market": 500,
        },
        total_passed={
            "factor_algebra": 400,  # 80% pass rate
            "narrative_mining": 50,  # 10% pass rate
            "symbolic_mutation": 50,  # 10% pass rate
            "cross_market": 50,  # 10% pass rate
        },
        consecutive_zeros={},
        warm_start=True,
    )
    random.seed(42)
    allocations = scheduler.allocate(state)
    alloc_map = {a.subspace: a for a in allocations}

    # Factor algebra (80% pass) should get more than the others
    assert alloc_map[ExplorationSubspace.FACTOR_ALGEBRA].quota > alloc_map[
        ExplorationSubspace.NARRATIVE_MINING
    ].quota


def test_allocation_sorted_by_weight(scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """返回结果按权重降序。"""
    allocations = scheduler.allocate(cold_state)
    weights = [a.weight for a in allocations]
    assert weights == sorted(weights, reverse=True)
