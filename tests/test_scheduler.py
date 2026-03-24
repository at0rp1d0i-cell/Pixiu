"""
Island 调度器 + SubspaceScheduler + Scheduler-Pool 集成 + SubspaceContext + SubspaceRegistry。

Sources:
  - tests/test_scheduler.py  (original)
  - tests/test_subspace_scheduler.py
  - tests/test_scheduler_pool_integration.py
  - tests/test_subspace_context.py
  - tests/test_subspace_registry.py
"""
import random
from unittest.mock import MagicMock, patch

import pytest

from src.factor_pool.pool import FactorPool
from src.factor_pool.scheduler import IslandScheduler, VIRGIN_ISLAND_SHARPE, T_MIN, RESET_MIN_RUNS
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.exploration import (
    SubspaceRegistry,
    PrimitiveCategory,
    FactorPrimitive,
    MarketMechanismTemplate,
    NarrativeCategory,
    MutationRecord,
)
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.scheduling.subspace_scheduler import (
    SchedulerState,
    SubspaceScheduler,
)
from src.scheduling.subspace_context import (
    build_factor_algebra_context,
    build_symbolic_mutation_context,
    build_cross_market_context,
    build_narrative_mining_context,
    build_subspace_context,
)
from src.formula.capabilities import (
    BASE_FIELD_SPECS,
    EXPERIMENTAL_FIELD_SPECS,
    get_runtime_formula_capabilities,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def pool(tmp_path):
    return FactorPool(db_path=str(tmp_path / "test_db"))


@pytest.fixture()
def scheduler(pool):
    return IslandScheduler(pool, seed=42)


def _register(pool, island, name, sharpe):
    report = BacktestReport(
        report_id=f"report-{name}",
        note_id=f"note-{name}",
        factor_id=f"{island}_{name}",
        island=island,
        formula="Mean($close,5)",
        metrics=BacktestMetrics(sharpe=sharpe, annualized_return=0.1, max_drawdown=-0.1,
                                ic_mean=0.03, ic_std=0.01, icir=0.4, turnover_rate=20.0),
        passed=sharpe > 2.67,
        execution_time_seconds=1.0,
        qlib_output_raw="{}",
    )
    verdict = CriticVerdict(
        report_id=f"report-{name}",
        factor_id=f"{island}_{name}",
        note_id=f"note-{name}",
        overall_passed=sharpe > 2.67,
        decision="promote" if sharpe > 2.67 else "archive",
        score=0.8 if sharpe > 2.67 else 0.3,
        checks=[],
        register_to_pool=True,
        pool_tags=[],
        reason_codes=[],
    )
    risk = RiskAuditReport(
        factor_id=f"{island}_{name}",
        overfitting_score=0.0,
        overfitting_flag=False,
        correlation_flags=[],
        recommendation="clear",
        audit_notes="ok",
    )
    pool.register_factor(report=report, verdict=verdict, risk_report=risk, hypothesis="test")


class TestSoftmax:
    def test_probabilities_sum_to_one(self, scheduler):
        probs = scheduler._softmax([2.0, 2.5, 3.0], temperature=1.0)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_higher_value_gets_higher_prob(self, scheduler):
        probs = scheduler._softmax([1.0, 2.0, 3.0], temperature=1.0)
        assert probs[2] > probs[1] > probs[0]

    def test_high_temperature_is_more_uniform(self, scheduler):
        probs_low = scheduler._softmax([1.0, 3.0], temperature=0.1)
        probs_high = scheduler._softmax([1.0, 3.0], temperature=10.0)
        # 低温时差距更大
        assert (probs_low[1] - probs_low[0]) > (probs_high[1] - probs_high[0])

    def test_low_temperature_approaches_argmax(self, scheduler):
        probs = scheduler._softmax([1.0, 1.0, 100.0], temperature=0.01)
        assert probs[2] > 0.999


class TestSelectIsland:
    def test_returns_active_island(self, scheduler):
        chosen = scheduler.select_island()
        assert chosen in scheduler._active_islands

    def test_virgin_islands_get_default_sharpe(self, pool, scheduler):
        # 无历史数据时，使用 VIRGIN_ISLAND_SHARPE
        sharpes = scheduler._get_island_sharpes()
        for island in scheduler._active_islands:
            assert sharpes[island] == VIRGIN_ISLAND_SHARPE

    def test_known_island_uses_historical_sharpe(self, pool, scheduler):
        _register(pool, "momentum", "factor_a", sharpe=2.9)
        sharpes = scheduler._get_island_sharpes()
        assert sharpes["momentum"] == pytest.approx(2.9)

    def test_statistical_selection_bias(self, pool):
        """高 Sharpe Island 在大量采样中被选中概率更高。"""
        _register(pool, "momentum", "high", sharpe=3.5)
        _register(pool, "northbound", "low", sharpe=1.5)

        sched = IslandScheduler(pool, seed=0)
        # 只保留这两个做测试
        sched._active_islands = ["momentum", "northbound"]
        sched._reserve_islands = []

        counts = {"momentum": 0, "northbound": 0}
        for _ in range(200):
            counts[sched.select_island()] += 1

        # momentum（高 Sharpe）应该被选中更多次
        assert counts["momentum"] > counts["northbound"]


class TestAnnealing:
    def test_temperature_decreases_after_anneal_every(self, scheduler):
        from src.factor_pool.scheduler import ANNEAL_EVERY
        initial_t = scheduler._temperature
        for i in range(ANNEAL_EVERY):
            scheduler.on_epoch_done("momentum", i)
        assert scheduler._temperature < initial_t

    def test_temperature_never_below_t_min(self, scheduler):
        for i in range(200):
            scheduler.on_epoch_done("momentum", i)
        assert scheduler._temperature >= T_MIN


class TestReset:
    def test_no_reset_if_too_few_runs(self, pool, scheduler):
        # 只跑了 1 次，低于 RESET_MIN_RUNS=3，不触发重置
        _register(pool, "momentum", "bad", sharpe=1.0)
        assert not scheduler._should_reset("momentum")

    def test_triggers_reset_when_conditions_met(self, pool, scheduler):
        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"bad_{i}", sharpe=1.0)
        assert scheduler._should_reset("momentum")

    def test_no_reset_if_no_reserve(self, pool):
        sched = IslandScheduler(pool, seed=0)
        sched._reserve_islands = []  # 清空备用池
        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"f_{i}", sharpe=1.0)
        assert not sched._should_reset("momentum")

    def test_reset_swaps_islands(self, pool):
        sched = IslandScheduler(pool, seed=0)
        original_active = set(sched._active_islands)

        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"f_{i}", sharpe=1.0)

        sched._reset_island("momentum")

        new_active = set(sched._active_islands)
        new_reserve = set(sched._reserve_islands)

        assert "momentum" not in new_active
        assert "momentum" in new_reserve
        assert len(new_active) == len(original_active)  # 数量不变


# ─────────────────────────────────────────────────────────
# From test_subspace_scheduler.py
# ─────────────────────────────────────────────────────────

@pytest.fixture
def subspace_scheduler() -> SubspaceScheduler:
    return SubspaceScheduler()


@pytest.fixture
def cold_state() -> SchedulerState:
    return SchedulerState()


def test_cold_start_allocation(subspace_scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """冷启动分配 = [4, 3, 3, 2]（按权重降序）"""
    allocations = subspace_scheduler.allocate(cold_state)
    quotas = [a.quota for a in allocations]
    assert quotas == [4, 3, 3, 2]


def test_min_quota_guaranteed(subspace_scheduler: SubspaceScheduler):
    """每个子空间至少获得最低配额，即使在暖启动极端情况下。"""
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
    allocations = subspace_scheduler.allocate(state)

    for alloc in allocations:
        assert alloc.quota >= subspace_scheduler.MIN_QUOTA[alloc.subspace], (
            f"{alloc.subspace.value} got {alloc.quota}, "
            f"min is {subspace_scheduler.MIN_QUOTA[alloc.subspace]}"
        )


def test_total_quota_exact(subspace_scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """总配额恒等于 12。"""
    allocations = subspace_scheduler.allocate(cold_state)
    assert sum(a.quota for a in allocations) == 12


def test_total_quota_exact_warm_start(subspace_scheduler: SubspaceScheduler):
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
    allocations = subspace_scheduler.allocate(state)
    assert sum(a.quota for a in allocations) == 12


def test_update_state_immutable(subspace_scheduler: SubspaceScheduler, cold_state: SchedulerState):
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
    new_state = subspace_scheduler.update_state(cold_state, results)

    assert cold_state.round_number == original_round
    assert cold_state.total_generated == original_generated
    assert cold_state.total_passed == original_passed

    assert new_state.round_number == 1
    assert new_state.total_generated["factor_algebra"] == 4
    assert new_state.total_passed["factor_algebra"] == 2


def test_warm_start_transition(subspace_scheduler: SubspaceScheduler):
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
    assert not state.warm_start

    results = {
        ExplorationSubspace.FACTOR_ALGEBRA: (4, 2),
        ExplorationSubspace.NARRATIVE_MINING: (3, 0),
        ExplorationSubspace.SYMBOLIC_MUTATION: (3, 0),
        ExplorationSubspace.CROSS_MARKET: (2, 0),
    }
    new_state = subspace_scheduler.update_state(state, results)
    assert new_state.warm_start is True


def test_consecutive_zero_warning(subspace_scheduler: SubspaceScheduler):
    """连续 3 轮零通过产生警告。"""
    state = SchedulerState(
        round_number=10,
        total_generated={"cross_market": 20},
        total_passed={"cross_market": 0},
        consecutive_zeros={"cross_market": 3},
        warm_start=False,
    )
    warnings = subspace_scheduler.get_warnings(state)
    assert len(warnings) >= 1
    assert "cross_market" in warnings[0]
    assert "3" in warnings[0]


def test_thompson_sampling_allocation(subspace_scheduler: SubspaceScheduler):
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
            "factor_algebra": 400,
            "narrative_mining": 50,
            "symbolic_mutation": 50,
            "cross_market": 50,
        },
        consecutive_zeros={},
        warm_start=True,
    )
    random.seed(42)
    allocations = subspace_scheduler.allocate(state)
    alloc_map = {a.subspace: a for a in allocations}

    assert alloc_map[ExplorationSubspace.FACTOR_ALGEBRA].quota > alloc_map[
        ExplorationSubspace.NARRATIVE_MINING
    ].quota


def test_allocation_sorted_by_weight(subspace_scheduler: SubspaceScheduler, cold_state: SchedulerState):
    """返回结果按权重降序。"""
    allocations = subspace_scheduler.allocate(cold_state)
    weights = [a.weight for a in allocations]
    assert weights == sorted(weights, reverse=True)


def test_allocate_honors_target_subspaces_env(monkeypatch: pytest.MonkeyPatch, subspace_scheduler: SubspaceScheduler):
    monkeypatch.setenv("PIXIU_TARGET_SUBSPACES", "factor_algebra,cross_market")

    allocations = subspace_scheduler.allocate(SchedulerState())

    assert [alloc.subspace for alloc in allocations] == [
        ExplorationSubspace.FACTOR_ALGEBRA,
        ExplorationSubspace.CROSS_MARKET,
    ]
    assert sum(alloc.quota for alloc in allocations) == subspace_scheduler.TOTAL_QUOTA


# ─────────────────────────────────────────────────────────
# From test_scheduler_pool_integration.py
# ─────────────────────────────────────────────────────────

def _make_pool_report(island: str, factor_id: str, sharpe: float) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{factor_id}",
        note_id=factor_id,
        factor_id=factor_id,
        island=island,
        formula="$close",
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.1,
            max_drawdown=0.1,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.5,
            turnover_rate=0.2,
        ),
        passed=sharpe > 1.0,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
    )


def _make_pool_verdict(factor_id: str, passed: bool) -> CriticVerdict:
    return CriticVerdict(
        report_id=f"report-{factor_id}",
        factor_id=factor_id,
        note_id=factor_id,
        overall_passed=passed,
        decision="promote" if passed else "archive",
        score=0.9 if passed else 0.3,
        checks=[],
        register_to_pool=True,
        pool_tags=[],
        reason_codes=[],
    )


def _make_pool_risk_report(factor_id: str) -> RiskAuditReport:
    return RiskAuditReport(
        factor_id=factor_id,
        overfitting_score=0.0,
        overfitting_flag=False,
        correlation_flags=[],
        recommendation="clear",
        audit_notes="ok",
    )


def _register_n_factors(pool: FactorPool, island: str, sharpe: float, n: int):
    for i in range(n):
        fid = f"{island}_factor_{i}"
        report = _make_pool_report(island, fid, sharpe)
        verdict = _make_pool_verdict(fid, passed=sharpe > 1.0)
        risk = _make_pool_risk_report(fid)
        pool.register_factor(report=report, verdict=verdict, risk_report=risk, hypothesis="test")


@pytest.fixture()
def pool_integration(tmp_path):
    """使用 in-memory client 的 FactorPool，避免 ChromaDB 触发网络下载。"""
    with patch("src.factor_pool.pool.chromadb.PersistentClient", side_effect=RuntimeError("force in-memory")):
        return FactorPool(db_path=str(tmp_path / "test_db"))


@pytest.fixture()
def scheduler_integration(pool_integration):
    return IslandScheduler(pool_integration, seed=42)


def test_get_active_islands_returns_list(scheduler_integration):
    islands = scheduler_integration.get_active_islands()
    assert isinstance(islands, list)
    assert len(islands) > 0


def test_get_active_islands_matches_internal_state(scheduler_integration):
    assert scheduler_integration.get_active_islands() == scheduler_integration._active_islands


def test_get_active_islands_returns_copy(scheduler_integration):
    result = scheduler_integration.get_active_islands()
    result.clear()
    assert len(scheduler_integration._active_islands) > 0, "外部修改不应影响内部 _active_islands"


def test_scheduler_selects_based_on_real_pool_leaderboard(pool_integration):
    _register_n_factors(pool_integration, "momentum", sharpe=3.5, n=3)
    _register_n_factors(pool_integration, "northbound", sharpe=1.0, n=3)

    sched = IslandScheduler(pool_integration, seed=0)
    sched._active_islands = ["momentum", "northbound"]
    sched._reserve_islands = []

    counts = {"momentum": 0, "northbound": 0}
    for _ in range(200):
        counts[sched.select_island()] += 1

    assert counts["momentum"] > counts["northbound"]


def test_get_active_islands_reflects_reset(pool_integration):
    sched = IslandScheduler(pool_integration, seed=0)

    _register_n_factors(pool_integration, "momentum", sharpe=1.0, n=RESET_MIN_RUNS)

    original_active = sched.get_active_islands()
    assert "momentum" in original_active

    sched._reset_island("momentum")

    new_active = sched.get_active_islands()
    assert "momentum" not in new_active


def test_scheduler_virgin_island_uses_default_sharpe(pool_integration, scheduler_integration):
    sharpes = scheduler_integration._get_island_sharpes()
    for island in scheduler_integration.get_active_islands():
        assert sharpes[island] == VIRGIN_ISLAND_SHARPE


def test_scheduler_known_island_uses_real_sharpe(pool_integration):
    _register_n_factors(pool_integration, "momentum", sharpe=2.9, n=1)
    sched = IslandScheduler(pool_integration, seed=42)
    sharpes = sched._get_island_sharpes()
    assert sharpes["momentum"] == pytest.approx(2.9)


def test_on_epoch_done_triggers_anneal_after_n_rounds(pool_integration, scheduler_integration):
    from src.factor_pool.scheduler import ANNEAL_EVERY

    initial_t = scheduler_integration._temperature
    for i in range(ANNEAL_EVERY):
        scheduler_integration.on_epoch_done("momentum", i)
    assert scheduler_integration._temperature < initial_t


# ─────────────────────────────────────────────────────────
# From test_subspace_context.py
# ─────────────────────────────────────────────────────────

@pytest.fixture
def default_registry():
    return SubspaceRegistry.get_default_registry()


@pytest.mark.smoke
class TestContextBuilders:

    def test_factor_algebra_non_empty(self, default_registry):
        ctx = build_factor_algebra_context(default_registry, "momentum")
        assert len(ctx) > 100
        assert "原语" in ctx or "primitive" in ctx.lower()
        assert "$close" in ctx
        assert "Ref($field, -N)" not in ctx

    def test_symbolic_mutation_non_empty(self, default_registry):
        ctx = build_symbolic_mutation_context(default_registry, None, "momentum")
        assert len(ctx) > 100
        assert "变异" in ctx or "mutation" in ctx.lower()

    def test_cross_market_non_empty(self, default_registry):
        ctx = build_cross_market_context(default_registry)
        assert len(ctx) > 100
        assert "跨市场" in ctx or "cross" in ctx.lower()
        assert "库存周期" in ctx or "利率" in ctx

    def test_narrative_mining_non_empty(self, default_registry):
        ctx = build_narrative_mining_context(default_registry)
        assert len(ctx) > 100
        assert "叙事" in ctx or "narrative" in ctx.lower()
        assert "政策" in ctx


@pytest.mark.smoke
class TestDispatcher:

    def test_routes_all_subspaces(self, default_registry):
        for ss in ExplorationSubspace:
            ctx = build_subspace_context(ss, default_registry, island="momentum")
            assert len(ctx) > 50, f"{ss.value} context too short"

    def test_factor_algebra_route(self, default_registry):
        ctx = build_subspace_context(ExplorationSubspace.FACTOR_ALGEBRA, default_registry, island="momentum")
        assert "因子代数" in ctx

    def test_symbolic_mutation_route(self, default_registry):
        ctx = build_subspace_context(ExplorationSubspace.SYMBOLIC_MUTATION, default_registry, island="momentum")
        assert "符号变异" in ctx

    def test_cross_market_route(self, default_registry):
        ctx = build_subspace_context(ExplorationSubspace.CROSS_MARKET, default_registry, island="momentum")
        assert "跨市场" in ctx

    def test_narrative_mining_route(self, default_registry):
        ctx = build_subspace_context(ExplorationSubspace.NARRATIVE_MINING, default_registry, island="momentum")
        assert "叙事" in ctx


# ─────────────────────────────────────────────────────────
# From test_subspace_registry.py
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestSubspaceRegistryDefaults:
    """默认注册表应包含完整的结构化上下文数据。"""

    @pytest.fixture
    def registry(self):
        return SubspaceRegistry.get_default_registry()

    def test_four_subspaces_enabled(self, registry):
        enabled = registry.get_enabled_subspaces()
        assert len(enabled) == 4
        for ss in ExplorationSubspace:
            assert ss in enabled

    def test_primitives_non_empty(self, registry):
        assert len(registry.primitives) >= 15

    def test_primitives_cover_categories(self, registry):
        cats = {p.category for p in registry.primitives}
        assert PrimitiveCategory.PRICE_VOLUME in cats
        assert PrimitiveCategory.TEMPORAL_TRANSFORM in cats
        capabilities = get_runtime_formula_capabilities()
        if capabilities.available_experimental_fields:
            assert PrimitiveCategory.FUNDAMENTAL in cats

    def test_temporal_primitives_use_non_future_templates(self, registry):
        primitives = {p.name: p for p in registry.primitives}
        assert primitives["Ref"].qlib_syntax == "Ref($field, N)"
        assert primitives["Delta"].qlib_syntax == "Delta($field, N)"

    def test_primitive_fields(self, registry):
        for p in registry.primitives:
            assert isinstance(p, FactorPrimitive)
            assert p.name
            assert p.qlib_syntax
            assert p.description

    def test_mechanism_templates_non_empty(self, registry):
        assert len(registry.mechanism_templates) >= 5

    def test_mechanism_template_fields(self, registry):
        for t in registry.mechanism_templates:
            assert isinstance(t, MarketMechanismTemplate)
            assert t.name
            assert t.source_market
            assert t.transmission_path
            assert t.skeleton

    def test_narrative_categories_non_empty(self, registry):
        assert len(registry.narrative_categories) >= 4

    def test_narrative_category_fields(self, registry):
        for c in registry.narrative_categories:
            assert isinstance(c, NarrativeCategory)
            assert c.category
            assert len(c.extraction_targets) > 0
            assert len(c.example_patterns) > 0


def test_subspace_registry_does_not_reintroduce_base_field_fallback_when_capabilities_empty():
    from src.formula.capabilities import FormulaCapabilities

    empty_caps = FormulaCapabilities(
        field_status={},
        approved_operators=tuple(),
        total_instruments=0,
        min_coverage_ratio=0.95,
    )

    for spec in BASE_FIELD_SPECS + EXPERIMENTAL_FIELD_SPECS:
        empty_caps.field_status[spec.formula_name] = MagicMock(available=False)

    with patch("src.schemas.exploration.get_runtime_formula_capabilities", return_value=empty_caps):
        registry = SubspaceRegistry.get_default_registry()

    assert registry.configs["factor_algebra"].allowed_primitives == []
    assert not any(
        p.category in {PrimitiveCategory.PRICE_VOLUME, PrimitiveCategory.FUNDAMENTAL}
        for p in registry.primitives
    )


@pytest.mark.smoke
class TestMutationRecord:
    """MutationRecord schema 验证。"""

    def test_create_mutation_record(self):
        rec = MutationRecord(
            source_factor_id="f_001",
            operator=MutationOperator.SWAP_HORIZON,
            parameter_change="5日→20日",
            result_formula="Mean($close, 20) / Mean($close, 60) - 1",
        )
        assert rec.operator == MutationOperator.SWAP_HORIZON
        assert "20日" in rec.parameter_change


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
