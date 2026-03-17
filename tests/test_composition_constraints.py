"""
CompositionConstraints + forbidden_patterns 动态注入测试

验证：
1. CompositionConstraints schema 实例化和默认值
2. SubspaceRegistry 包含 composition_constraints 字段
3. build_factor_algebra_context() 在 pool=None 时不报错
4. build_factor_algebra_context() 在 pool 有 hard constraints 时注入 forbidden_patterns
5. forbidden_patterns 在 prompt 中出现
6. warning-severity 约束不注入 forbidden_patterns
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC

import pytest

from src.schemas.exploration import CompositionConstraints, SubspaceRegistry
from src.schemas.failure_constraint import FailureConstraint, FailureMode
from src.scheduling.subspace_context import build_factor_algebra_context, build_subspace_context
from src.schemas.hypothesis import ExplorationSubspace


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_pool_inmemory():
    """Create a FactorPool backed by the in-memory client (no ChromaDB on disk)."""
    from src.factor_pool.pool import FactorPool, _InMemoryClient
    pool = FactorPool.__new__(FactorPool)
    pool._storage_mode = "in_memory"
    pool._client = _InMemoryClient()
    pool._collection = pool._client.get_or_create_collection("factor_experiments")
    pool._notes_collection = pool._client.get_or_create_collection("research_notes")
    pool._explorations_collection = pool._client.get_or_create_collection("exploration_results")
    pool._constraints_collection = pool._client.get_or_create_collection(
        FactorPool.CONSTRAINT_COLLECTION
    )
    return pool


def _make_constraint(
    island: str = "momentum",
    severity: str = "hard",
    formula_pattern: str = "Div($close, Ref($close, N))",
    failure_mode: FailureMode = FailureMode.LOW_SHARPE,
) -> FailureConstraint:
    return FailureConstraint(
        constraint_id=str(uuid.uuid4()),
        source_note_id="note_test",
        source_verdict_id="verdict_test",
        failure_mode=failure_mode,
        island=island,
        formula_pattern=formula_pattern,
        constraint_rule=f"avoid {formula_pattern} in {island}",
        severity=severity,
        created_at=datetime.now(UTC).isoformat(),
    )


# ─────────────────────────────────────────────
# 1. CompositionConstraints schema
# ─────────────────────────────────────────────

@pytest.mark.unit
class TestCompositionConstraintsSchema:

    def test_default_instantiation(self):
        cc = CompositionConstraints()
        assert cc.max_nesting_depth == 4
        assert cc.max_total_operators == 8
        assert cc.forbidden_patterns == []

    def test_custom_values(self):
        cc = CompositionConstraints(
            max_nesting_depth=2,
            max_total_operators=5,
            forbidden_patterns=["Rank($pe_ttm)", "Std($volume, N)"],
        )
        assert cc.max_nesting_depth == 2
        assert cc.max_total_operators == 5
        assert len(cc.forbidden_patterns) == 2

    def test_forbidden_patterns_is_list(self):
        cc = CompositionConstraints()
        assert isinstance(cc.forbidden_patterns, list)

    def test_extra_fields_forbidden(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CompositionConstraints(nonexistent_field="oops")


# ─────────────────────────────────────────────
# 2. SubspaceRegistry contains composition_constraints
# ─────────────────────────────────────────────

@pytest.mark.unit
class TestSubspaceRegistryCompositionConstraints:

    def test_registry_has_composition_constraints_field(self):
        registry = SubspaceRegistry()
        assert hasattr(registry, "composition_constraints")
        assert isinstance(registry.composition_constraints, CompositionConstraints)

    def test_default_registry_has_composition_constraints(self):
        registry = SubspaceRegistry.get_default_registry()
        assert hasattr(registry, "composition_constraints")
        assert isinstance(registry.composition_constraints, CompositionConstraints)

    def test_default_composition_constraints_values(self):
        registry = SubspaceRegistry.get_default_registry()
        cc = registry.composition_constraints
        assert cc.max_nesting_depth == 4
        assert cc.max_total_operators == 8
        assert cc.forbidden_patterns == []

    def test_composition_constraints_mutable(self):
        registry = SubspaceRegistry.get_default_registry()
        registry.composition_constraints.forbidden_patterns.append("Rank($pe_ttm)")
        assert "Rank($pe_ttm)" in registry.composition_constraints.forbidden_patterns


# ─────────────────────────────────────────────
# 3. build_factor_algebra_context — pool=None
# ─────────────────────────────────────────────

@pytest.mark.smoke
class TestBuildFactorAlgebraContextNoPool:

    def test_no_pool_does_not_raise(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=None)
        assert isinstance(ctx, str)
        assert len(ctx) > 100

    def test_no_pool_contains_primitives(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=None)
        assert "$close" in ctx

    def test_no_pool_contains_nesting_depth(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=None)
        assert "最大嵌套深度" in ctx

    def test_no_pool_no_forbidden_section(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=None)
        # No forbidden patterns in default registry
        assert "禁止模式" not in ctx

    def test_omitted_pool_arg_same_as_none(self):
        """Calling without pool kwarg (legacy signature) must work unchanged."""
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum")
        assert len(ctx) > 100


# ─────────────────────────────────────────────
# 4. build_factor_algebra_context — hard constraints injected
# ─────────────────────────────────────────────

@pytest.mark.unit
class TestBuildFactorAlgebraContextWithPool:

    def test_hard_constraint_injected_into_forbidden_patterns(self):
        pool = _make_pool_inmemory()
        c = _make_constraint(island="momentum", severity="hard", formula_pattern="Div($close, Ref($close, N))")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        build_factor_algebra_context(registry, "momentum", pool=pool)

        assert "Div($close, Ref($close, N))" in registry.composition_constraints.forbidden_patterns

    def test_hard_constraint_appears_in_prompt(self):
        pool = _make_pool_inmemory()
        c = _make_constraint(island="momentum", severity="hard", formula_pattern="Div($close, Ref($close, N))")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)

        assert "禁止模式" in ctx
        assert "Div($close, Ref($close, N))" in ctx

    def test_multiple_hard_constraints_all_injected(self):
        pool = _make_pool_inmemory()
        patterns = ["Div($close, Ref($close, N))", "Rank(Mean($volume, N))", "Std($close, N_LONG)"]
        for pat in patterns:
            pool.register_constraint(_make_constraint(island="momentum", severity="hard", formula_pattern=pat))

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)

        for pat in patterns:
            assert pat in ctx

    def test_warning_constraint_not_injected(self):
        pool = _make_pool_inmemory()
        c = _make_constraint(island="momentum", severity="warning", formula_pattern="Rank($pe_ttm)")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)

        # warning constraints should NOT appear in forbidden_patterns section
        assert "Rank($pe_ttm)" not in registry.composition_constraints.forbidden_patterns
        assert "禁止模式" not in ctx

    def test_hard_constraint_different_island_not_injected(self):
        pool = _make_pool_inmemory()
        c = _make_constraint(island="value", severity="hard", formula_pattern="Rank($roe)")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)

        assert "Rank($roe)" not in registry.composition_constraints.forbidden_patterns
        assert "禁止模式" not in ctx

    def test_deduplication_of_repeated_patterns(self):
        pool = _make_pool_inmemory()
        pat = "Div($close, Ref($close, N))"
        # Register same pattern twice (different constraint IDs)
        pool.register_constraint(_make_constraint(island="momentum", severity="hard", formula_pattern=pat))
        pool.register_constraint(_make_constraint(island="momentum", severity="hard", formula_pattern=pat))

        registry = SubspaceRegistry.get_default_registry()
        build_factor_algebra_context(registry, "momentum", pool=pool)

        assert registry.composition_constraints.forbidden_patterns.count(pat) == 1

    def test_pool_error_degrades_gracefully(self):
        from unittest.mock import MagicMock
        broken_pool = MagicMock()
        broken_pool.query_constraints.side_effect = RuntimeError("DB unavailable")

        registry = SubspaceRegistry.get_default_registry()
        # Must not raise
        ctx = build_factor_algebra_context(registry, "momentum", pool=broken_pool)
        assert isinstance(ctx, str)
        assert len(ctx) > 100


# ─────────────────────────────────────────────
# 5. Dispatcher (build_subspace_context) passes pool through
# ─────────────────────────────────────────────

@pytest.mark.smoke
class TestDispatcherPassesPool:

    def test_dispatcher_factor_algebra_with_pool(self):
        pool = _make_pool_inmemory()
        c = _make_constraint(island="momentum", severity="hard", formula_pattern="Rank($turn)")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_subspace_context(
            ExplorationSubspace.FACTOR_ALGEBRA,
            registry,
            factor_pool=pool,
            island="momentum",
        )

        assert "禁止模式" in ctx
        assert "Rank($turn)" in ctx

    def test_dispatcher_factor_algebra_no_pool(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_subspace_context(
            ExplorationSubspace.FACTOR_ALGEBRA,
            registry,
            factor_pool=None,
            island="momentum",
        )
        assert "因子代数" in ctx
        assert "禁止模式" not in ctx
