"""
Merged constraint tests: failure_constraint + composition_constraints + mutation.

Sources:
  - tests/test_failure_constraint.py
  - tests/test_composition_constraints.py
  - tests/test_mutation.py
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

import pytest

from src.schemas.failure_constraint import FailureConstraint, FailureMode
from src.schemas.judgment import CriticVerdict, ThresholdCheck
from src.schemas.research_note import FactorResearchNote
from src.schemas.exploration import CompositionConstraints, SubspaceRegistry
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator
from src.scheduling.subspace_context import build_factor_algebra_context, build_subspace_context
from src.hypothesis.mutation import (
    QlibFormulaParser,
    SymbolicMutator,
    MutationResult,
    try_all_mutations,
    build_mutation_record_dict,
)

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────
# Helpers / factories (from test_failure_constraint.py)
# ─────────────────────────────────────────────

def _make_note(
    formula: str = "Div($close, Ref($close, 5))",
    island: str = "momentum",
) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=f"{island}_{uuid.uuid4().hex[:8]}",
        island=island,
        iteration=0,
        hypothesis="短期动量假设",
        economic_intuition="价格趋势具有短期自我强化特性",
        proposed_formula=formula,
        risk_factors=["流动性冲击"],
        market_context_date="2026-03-17",
    )


def _make_failed_verdict(
    failure_mode: str = "low_sharpe",
    checks: list[ThresholdCheck] | None = None,
) -> CriticVerdict:
    if checks is None:
        checks = [
            ThresholdCheck(metric="sharpe", value=0.5, threshold=2.67, passed=False),
            ThresholdCheck(metric="ic_mean", value=0.01, threshold=0.02, passed=False),
        ]
    return CriticVerdict(
        report_id=str(uuid.uuid4()),
        factor_id=f"factor_{uuid.uuid4().hex[:8]}",
        overall_passed=False,
        failure_mode=failure_mode,
        failure_explanation=f"Failed due to {failure_mode}",
        suggested_fix="Consider adjusting the formula.",
        checks=checks,
        register_to_pool=False,
    )


def _make_passed_verdict() -> CriticVerdict:
    return CriticVerdict(
        report_id=str(uuid.uuid4()),
        factor_id=f"factor_{uuid.uuid4().hex[:8]}",
        overall_passed=True,
        checks=[
            ThresholdCheck(metric="sharpe", value=3.5, threshold=2.67, passed=True),
        ],
        register_to_pool=True,
    )


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
        source_note_id="note_abc",
        source_verdict_id="verdict_xyz",
        failure_mode=failure_mode,
        island=island,
        formula_pattern=formula_pattern,
        constraint_rule=f"avoid {formula_pattern} in {island} — test constraint",
        severity=severity,
        created_at=datetime.now(UTC).isoformat(),
    )


# ─────────────────────────────────────────────
# 1. Schema validation
# ─────────────────────────────────────────────

class TestFailureConstraintSchema:
    def test_valid_constraint_instantiation(self):
        c = _make_constraint()
        assert c.island == "momentum"
        assert c.severity == "hard"
        assert c.failure_mode == FailureMode.LOW_SHARPE
        assert c.times_violated == 0
        assert c.times_checked == 0

    def test_failure_mode_enum_values(self):
        assert FailureMode.LOW_SHARPE.value == "low_sharpe"
        assert FailureMode.HIGH_TURNOVER.value == "high_turnover"
        assert FailureMode.EXECUTION_ERROR.value == "execution_error"
        assert FailureMode.DUPLICATE.value == "duplicate"

    def test_severity_defaults_to_warning(self):
        c = FailureConstraint(
            source_note_id="n1",
            source_verdict_id="v1",
            failure_mode=FailureMode.NO_IC,
            island="value",
            formula_pattern="Rank($pe_ttm)",
            constraint_rule="avoid Rank($pe_ttm)",
            created_at=datetime.now(UTC).isoformat(),
        )
        assert c.severity == "warning"

    def test_constraint_id_auto_generated(self):
        c = FailureConstraint(
            source_note_id="n1",
            source_verdict_id="v1",
            failure_mode=FailureMode.HIGH_DRAWDOWN,
            island="reversal",
            formula_pattern="Sub($close, Ref($close, N))",
            constraint_rule="avoid deep drawdown pattern",
            created_at=datetime.now(UTC).isoformat(),
        )
        parsed = uuid.UUID(c.constraint_id)
        assert str(parsed) == c.constraint_id

    def test_extra_fields_forbidden(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FailureConstraint(
                source_note_id="n1",
                source_verdict_id="v1",
                failure_mode=FailureMode.LOW_SHARPE,
                island="momentum",
                formula_pattern="X",
                constraint_rule="Y",
                created_at=datetime.now(UTC).isoformat(),
                nonexistent_field="oops",
            )

    def test_optional_subspace_is_none_by_default(self):
        c = _make_constraint()
        assert c.subspace is None

    def test_optional_last_violated_at_is_none_by_default(self):
        c = _make_constraint()
        assert c.last_violated_at is None


# ─────────────────────────────────────────────
# 2. ConstraintExtractor
# ─────────────────────────────────────────────

class TestConstraintExtractor:
    def setup_method(self):
        from src.agents.judgment import ConstraintExtractor
        self.extractor = ConstraintExtractor()

    def test_passed_verdict_returns_none(self):
        verdict = _make_passed_verdict()
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result is None

    def test_failed_verdict_returns_constraint(self):
        verdict = _make_failed_verdict(failure_mode="low_sharpe")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result is not None
        assert isinstance(result, FailureConstraint)

    def test_constraint_has_correct_ids(self):
        verdict = _make_failed_verdict()
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.source_note_id == note.note_id
        assert result.source_verdict_id == verdict.verdict_id

    def test_constraint_island_matches_note(self):
        verdict = _make_failed_verdict()
        note = _make_note(island="reversal")
        result = self.extractor.extract(verdict, note)
        assert result.island == "reversal"

    def test_failure_mode_classification_low_sharpe(self):
        verdict = _make_failed_verdict(failure_mode="low_sharpe")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.failure_mode == FailureMode.LOW_SHARPE

    def test_failure_mode_classification_execution_error(self):
        verdict = _make_failed_verdict(failure_mode="execution_error")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.failure_mode == FailureMode.EXECUTION_ERROR

    def test_execution_error_is_warning_only(self):
        verdict = _make_failed_verdict(failure_mode="execution_error")
        note = _make_note()
        result = self.extractor.extract(verdict, note)

        assert result is not None
        assert result.failure_mode == FailureMode.EXECUTION_ERROR
        assert result.severity == "warning"
        assert "execution error" in result.constraint_rule.lower()

    def test_failure_mode_classification_high_turnover(self):
        verdict = _make_failed_verdict(failure_mode="high_turnover")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.failure_mode == FailureMode.HIGH_TURNOVER

    def test_failure_mode_fallback_from_checks(self):
        checks = [
            ThresholdCheck(metric="turnover", value=0.8, threshold=0.5, passed=False),
        ]
        verdict = _make_failed_verdict(failure_mode="unknown_mode", checks=checks)
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.failure_mode == FailureMode.HIGH_TURNOVER

    def test_extract_pattern_replaces_numbers_with_N(self):
        from src.agents.judgment import ConstraintExtractor
        extractor = ConstraintExtractor()
        pattern = extractor._extract_pattern("Div($close, Ref($close, 5))")
        assert pattern == "Div($close, Ref($close, N_SHORT))"

    def test_extract_pattern_multiple_numbers(self):
        from src.agents.judgment import ConstraintExtractor
        extractor = ConstraintExtractor()
        pattern = extractor._extract_pattern("Rank(Mean($volume, 10))")
        assert pattern == "Rank(Mean($volume, N_SHORT))"

    def test_extract_pattern_empty_formula(self):
        from src.agents.judgment import ConstraintExtractor
        extractor = ConstraintExtractor()
        assert extractor._extract_pattern("") == ""

    def test_severity_warning_for_execution_error(self):
        verdict = _make_failed_verdict(failure_mode="execution_error")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.severity == "warning"

    def test_severity_hard_for_high_turnover(self):
        verdict = _make_failed_verdict(failure_mode="high_turnover")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.severity == "hard"

    def test_severity_warning_for_low_sharpe_single_check(self):
        checks = [ThresholdCheck(metric="sharpe", value=1.0, threshold=2.67, passed=False)]
        verdict = _make_failed_verdict(failure_mode="low_sharpe", checks=checks)
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.severity == "warning"

    def test_severity_hard_when_many_checks_fail(self):
        checks = [
            ThresholdCheck(metric="sharpe", value=0.3, threshold=2.67, passed=False),
            ThresholdCheck(metric="ic_mean", value=0.001, threshold=0.02, passed=False),
            ThresholdCheck(metric="turnover", value=0.9, threshold=0.5, passed=False),
        ]
        verdict = _make_failed_verdict(failure_mode="low_sharpe", checks=checks)
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.severity == "hard"

    def test_constraint_rule_is_non_empty_string(self):
        verdict = _make_failed_verdict()
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert isinstance(result.constraint_rule, str)
        assert len(result.constraint_rule) > 0

    def test_created_at_is_iso_string(self):
        verdict = _make_failed_verdict()
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        datetime.fromisoformat(result.created_at)

    def test_subspace_from_note_exploration_subspace(self):
        note = _make_note()
        note_with_subspace = note.model_copy(
            update={"exploration_subspace": ExplorationSubspace.FACTOR_ALGEBRA}
        )
        verdict = _make_failed_verdict()
        result = self.extractor.extract(verdict, note_with_subspace)
        assert result.subspace == ExplorationSubspace.FACTOR_ALGEBRA.value

    def test_subspace_none_when_not_set(self):
        note = _make_note()
        verdict = _make_failed_verdict()
        result = self.extractor.extract(verdict, note)
        assert result.subspace is None


# ─────────────────────────────────────────────
# 3. FactorPool constraint CRUD
# ─────────────────────────────────────────────

class TestFactorPoolConstraintCRUD:
    def setup_method(self):
        self.pool = _make_pool_inmemory()

    def test_register_constraint_and_query_by_island(self):
        c = _make_constraint(island="momentum")
        self.pool.register_constraint(c)
        results = self.pool.query_constraints(island="momentum")
        assert len(results) == 1
        assert results[0].constraint_id == c.constraint_id

    def test_query_constraints_empty_returns_empty_list(self):
        results = self.pool.query_constraints(island="nonexistent")
        assert results == []

    def test_query_constraints_by_failure_mode(self):
        c1 = _make_constraint(failure_mode=FailureMode.LOW_SHARPE)
        c2 = _make_constraint(failure_mode=FailureMode.HIGH_TURNOVER)
        self.pool.register_constraint(c1)
        self.pool.register_constraint(c2)
        results = self.pool.query_constraints(failure_mode=FailureMode.LOW_SHARPE)
        assert len(results) == 1
        assert results[0].failure_mode == FailureMode.LOW_SHARPE

    def test_query_constraints_by_island_and_failure_mode(self):
        c1 = _make_constraint(island="momentum", failure_mode=FailureMode.LOW_SHARPE)
        c2 = _make_constraint(island="value", failure_mode=FailureMode.LOW_SHARPE)
        self.pool.register_constraint(c1)
        self.pool.register_constraint(c2)
        results = self.pool.query_constraints(
            island="momentum", failure_mode=FailureMode.LOW_SHARPE
        )
        assert len(results) == 1
        assert results[0].island == "momentum"

    def test_register_multiple_and_query_all(self):
        for _ in range(3):
            self.pool.register_constraint(_make_constraint(island="value"))
        results = self.pool.query_constraints(island="value")
        assert len(results) == 3

    def test_query_constraints_by_formula_returns_results(self):
        c = _make_constraint(formula_pattern="Div($close, Ref($close, N))")
        self.pool.register_constraint(c)
        results = self.pool.query_constraints_by_formula(
            "Div($close, Ref($close, 5))", limit=5
        )
        assert len(results) >= 1

    def test_query_constraints_by_formula_empty_pool(self):
        results = self.pool.query_constraints_by_formula("Rank($close)", limit=5)
        assert results == []

    def test_increment_violation_updates_count(self):
        c = _make_constraint()
        self.pool.register_constraint(c)
        self.pool.increment_violation(c.constraint_id)
        results = self.pool.query_constraints(island=c.island)
        assert len(results) == 1
        assert results[0].times_violated == 1

    def test_increment_violation_multiple_times(self):
        c = _make_constraint()
        self.pool.register_constraint(c)
        self.pool.increment_violation(c.constraint_id)
        self.pool.increment_violation(c.constraint_id)
        results = self.pool.query_constraints(island=c.island)
        assert results[0].times_violated == 2

    def test_increment_violation_nonexistent_id_does_not_raise(self):
        self.pool.increment_violation("nonexistent-constraint-id")

    def test_upsert_overwrites_existing(self):
        c = _make_constraint()
        self.pool.register_constraint(c)
        updated = c.model_copy(update={"severity": "warning"})
        self.pool.register_constraint(updated)
        results = self.pool.query_constraints(island=c.island)
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_constraint_severity_preserved_through_roundtrip(self):
        c = _make_constraint(severity="hard")
        self.pool.register_constraint(c)
        results = self.pool.query_constraints(island=c.island)
        assert results[0].severity == "hard"

    def test_constraint_formula_pattern_preserved_through_roundtrip(self):
        c = _make_constraint(formula_pattern="Rank(Mean($volume, N))")
        self.pool.register_constraint(c)
        results = self.pool.query_constraints(island=c.island)
        assert results[0].formula_pattern == "Rank(Mean($volume, N))"


# ─────────────────────────────────────────────
# 4. ConstraintChecker prefilter integration
# ─────────────────────────────────────────────

class TestConstraintChecker:
    def setup_method(self):
        from src.agents.prefilter import ConstraintChecker
        self.pool = _make_pool_inmemory()
        self.checker = ConstraintChecker(pool=self.pool)

    def test_no_constraints_passes(self):
        note = _make_note()
        passed, reason = self.checker.check(note)
        assert passed is True

    def test_hard_constraint_matching_formula_rejects(self):
        c = _make_constraint(
            island="momentum",
            severity="hard",
            formula_pattern="Div($close, Ref($close, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        passed, reason = self.checker.check(note)
        assert passed is False
        assert "failure pattern" in reason.lower() or "Matches" in reason

    def test_warning_constraint_does_not_reject(self):
        c = _make_constraint(
            island="momentum",
            severity="warning",
            formula_pattern="Div($close, Ref($close, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        passed, reason = self.checker.check(note)
        assert passed is True

    def test_hard_constraint_different_island_does_not_reject(self):
        c = _make_constraint(
            island="value",
            severity="hard",
            formula_pattern="Div($close, Ref($close, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        passed, reason = self.checker.check(note)
        assert passed is True

    def test_hard_constraint_non_matching_pattern_passes(self):
        c = _make_constraint(
            island="momentum",
            severity="hard",
            formula_pattern="Rank(Mean($volume, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        passed, reason = self.checker.check(note)
        assert passed is True

    def test_increment_violation_called_on_rejection(self):
        c = _make_constraint(
            island="momentum",
            severity="hard",
            formula_pattern="Div($close, Ref($close, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        self.checker.check(note)
        results = self.pool.query_constraints(island="momentum")
        assert results[0].times_violated == 1

    def test_checker_degrades_on_pool_error(self):
        from src.agents.prefilter import ConstraintChecker
        broken_pool = MagicMock()
        broken_pool.query_constraints.side_effect = RuntimeError("DB unavailable")
        checker = ConstraintChecker(pool=broken_pool)
        note = _make_note()
        passed, reason = checker.check(note)
        assert passed is True

    def test_checker_uses_final_formula_when_set(self):
        c = _make_constraint(
            island="momentum",
            severity="hard",
            formula_pattern="Rank(Mean($volume, N))",
        )
        self.pool.register_constraint(c)
        note = _make_note(formula="Div($close, Ref($close, 5))", island="momentum")
        note_with_final = note.model_copy(
            update={"final_formula": "Rank(Mean($volume, 20))"}
        )
        passed, reason = self.checker.check(note_with_final)
        assert passed is False

    def test_horizon_bucket_boundaries_are_disjoint(self):
        assert self.checker._matches_pattern(
            "Rank(Mean($volume, 10))",
            "Rank(Mean($volume, N_SHORT))",
        )
        assert self.checker._matches_pattern(
            "Rank(Mean($volume, 11))",
            "Rank(Mean($volume, N_MID))",
        )
        assert self.checker._matches_pattern(
            "Rank(Mean($volume, 59))",
            "Rank(Mean($volume, N_MID))",
        )
        assert self.checker._matches_pattern(
            "Rank(Mean($volume, 60))",
            "Rank(Mean($volume, N_LONG))",
        )
        assert self.checker._matches_pattern(
            "Rank(Mean($volume, 61))",
            "Rank(Mean($volume, N_LONG))",
        )
        assert not self.checker._matches_pattern(
            "Rank(Mean($volume, 60))",
            "Rank(Mean($volume, N_MID))",
        )


# ─────────────────────────────────────────────
# 5. End-to-end: verdict → constraint → prefilter
# ─────────────────────────────────────────────

class TestE2EConstraintFlow:
    def test_full_flow_verdict_to_constraint_to_rejection(self):
        from src.agents.judgment import ConstraintExtractor
        from src.agents.prefilter import ConstraintChecker

        pool = _make_pool_inmemory()
        extractor = ConstraintExtractor()
        checker = ConstraintChecker(pool=pool)

        note = _make_note(
            formula="Div($close, Ref($close, 5))",
            island="momentum",
        )
        verdict = _make_failed_verdict(failure_mode="high_turnover")
        constraint = extractor.extract(verdict, note)
        assert constraint is not None
        assert constraint.severity == "hard"
        pool.register_constraint(constraint)

        new_note = _make_note(
            formula="Div($close, Ref($close, 10))",
            island="momentum",
        )
        passed, reason = checker.check(new_note)
        assert passed is False

    def test_full_flow_passed_verdict_produces_no_constraint(self):
        from src.agents.judgment import ConstraintExtractor
        from src.agents.prefilter import ConstraintChecker

        pool = _make_pool_inmemory()
        extractor = ConstraintExtractor()
        checker = ConstraintChecker(pool=pool)

        note = _make_note()
        verdict = _make_passed_verdict()
        constraint = extractor.extract(verdict, note)
        assert constraint is None
        new_note = _make_note()
        passed, _ = checker.check(new_note)
        assert passed is True

    def test_researcher_constraint_section_uses_pool(self):
        from src.agents.researcher import AlphaResearcher

        pool = _make_pool_inmemory()
        c_hard = _make_constraint(island="momentum", severity="hard")
        c_warn = _make_constraint(island="momentum", severity="warning")
        pool.register_constraint(c_hard)
        pool.register_constraint(c_warn)

        researcher = AlphaResearcher(island="momentum", factor_pool=pool)
        section = researcher._build_constraint_section(failed_formulas=None)

        assert "硬约束" in section
        assert "警告" in section

    def test_researcher_fallback_to_text_when_no_pool(self):
        from src.agents.researcher import AlphaResearcher

        researcher = AlphaResearcher(island="momentum", factor_pool=None)
        section = researcher._build_constraint_section(
            failed_formulas=["Div($close, Ref($close, 5))"]
        )
        assert "Div($close, Ref($close, 5))" in section

    def test_researcher_fallback_empty_when_no_pool_no_formulas(self):
        from src.agents.researcher import AlphaResearcher

        researcher = AlphaResearcher(island="momentum", factor_pool=None)
        section = researcher._build_constraint_section(failed_formulas=None)
        assert section == "无"

    def test_researcher_init_does_not_require_openai_key(self):
        from src.agents.researcher import AlphaResearcher
        with patch("src.agents.researcher.build_researcher_llm", side_effect=AssertionError("should not build llm in __init__")):
            researcher = AlphaResearcher(island="momentum", factor_pool=None)
        assert researcher is not None


# ─────────────────────────────────────────────
# From test_composition_constraints.py
# ─────────────────────────────────────────────

def _make_pool_inmemory_cc():
    """Alias for composition constraints tests."""
    return _make_pool_inmemory()


def _make_constraint_cc(
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
        assert "禁止模式" not in ctx

    def test_omitted_pool_arg_same_as_none(self):
        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum")
        assert len(ctx) > 100


class TestBuildFactorAlgebraContextWithPool:

    def test_hard_constraint_injected_into_forbidden_patterns(self):
        pool = _make_pool_inmemory_cc()
        c = _make_constraint_cc(island="momentum", severity="hard", formula_pattern="Div($close, Ref($close, N))")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        assert "Div($close, Ref($close, N))" in ctx

    def test_hard_constraint_appears_in_prompt(self):
        pool = _make_pool_inmemory_cc()
        c = _make_constraint_cc(island="momentum", severity="hard", formula_pattern="Div($close, Ref($close, N))")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        assert "禁止模式" in ctx
        assert "Div($close, Ref($close, N))" in ctx

    def test_multiple_hard_constraints_all_injected(self):
        pool = _make_pool_inmemory_cc()
        patterns = ["Div($close, Ref($close, N))", "Rank(Mean($volume, N))", "Std($close, N_LONG)"]
        for pat in patterns:
            pool.register_constraint(_make_constraint_cc(island="momentum", severity="hard", formula_pattern=pat))

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        for pat in patterns:
            assert pat in ctx

    def test_warning_constraint_not_injected(self):
        pool = _make_pool_inmemory_cc()
        c = _make_constraint_cc(island="momentum", severity="warning", formula_pattern="Rank($pe_ttm)")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        assert "Rank($pe_ttm)" not in registry.composition_constraints.forbidden_patterns
        assert "禁止模式" not in ctx

    def test_hard_constraint_different_island_not_injected(self):
        pool = _make_pool_inmemory_cc()
        c = _make_constraint_cc(island="value", severity="hard", formula_pattern="Rank($roe)")
        pool.register_constraint(c)

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        assert "Rank($roe)" not in registry.composition_constraints.forbidden_patterns
        assert "禁止模式" not in ctx

    def test_deduplication_of_repeated_patterns(self):
        pool = _make_pool_inmemory_cc()
        pat = "Div($close, Ref($close, N))"
        pool.register_constraint(_make_constraint_cc(island="momentum", severity="hard", formula_pattern=pat))
        pool.register_constraint(_make_constraint_cc(island="momentum", severity="hard", formula_pattern=pat))

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=pool)
        assert ctx.count(pat) == 1

    def test_pool_error_degrades_gracefully(self):
        broken_pool = MagicMock()
        broken_pool.query_constraints.side_effect = RuntimeError("DB unavailable")

        registry = SubspaceRegistry.get_default_registry()
        ctx = build_factor_algebra_context(registry, "momentum", pool=broken_pool)
        assert isinstance(ctx, str)
        assert len(ctx) > 100


@pytest.mark.smoke
class TestDispatcherPassesPool:

    def test_dispatcher_factor_algebra_with_pool(self):
        pool = _make_pool_inmemory_cc()
        c = _make_constraint_cc(island="momentum", severity="hard", formula_pattern="Rank($turn)")
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


# ─────────────────────────────────────────────
# From test_mutation.py
# ─────────────────────────────────────────────

@pytest.mark.smoke
class TestQlibFormulaParserBasic:

    def setup_method(self):
        self.parser = QlibFormulaParser()

    def test_parse_field(self):
        node = self.parser.parse("$close")
        assert node is not None
        assert node.op == "$close"
        assert node.args == []

    def test_parse_simple_function(self):
        node = self.parser.parse("Rank($close)")
        assert node is not None
        assert node.op == "Rank"
        assert len(node.args) == 1
        assert node.args[0].op == "$close"

    def test_parse_function_with_window(self):
        node = self.parser.parse("Mean($close, 5)")
        assert node is not None
        assert node.op == "Mean"
        assert len(node.args) == 2
        assert node.args[0].op == "$close"
        assert node.args[1].op == "5"

    def test_parse_nested_function(self):
        node = self.parser.parse("Rank(Mean($close, 20))")
        assert node is not None
        assert node.op == "Rank"
        assert node.args[0].op == "Mean"

    def test_parse_corr_three_args(self):
        node = self.parser.parse("Corr($close, $volume, 10)")
        assert node is not None
        assert node.op == "Corr"
        assert len(node.args) == 3

    def test_roundtrip_simple(self):
        formula = "Mean($close, 5)"
        node = self.parser.parse(formula)
        assert node is not None
        assert node.to_formula() == formula

    def test_roundtrip_nested(self):
        formula = "Rank(Mean($close, 20))"
        node = self.parser.parse(formula)
        assert node is not None
        assert node.to_formula() == formula


@pytest.mark.smoke
class TestQlibFormulaParserInfixDetection:

    def setup_method(self):
        self.parser = QlibFormulaParser()

    def test_infix_plus_returns_none(self):
        assert self.parser.parse("$close + $open") is None

    def test_infix_minus_returns_none(self):
        assert self.parser.parse("$close - $open") is None

    def test_infix_mul_returns_none(self):
        assert self.parser.parse("$close * $volume") is None

    def test_infix_div_returns_none(self):
        assert self.parser.parse("Mean($close, 5) / Mean($close, 20)") is None

    def test_nested_infix_inside_function_not_detected_as_toplevel(self):
        result = self.parser.parse("Rank($close)")
        assert result is not None

    def test_empty_string_returns_none(self):
        assert self.parser.parse("") is None

    def test_whitespace_only_returns_none(self):
        assert self.parser.parse("   ") is None


class TestSwapHorizon:

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_swap_horizon_changes_window(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert result.result_formula != "Mean($close, 5)"
        assert "$close" in result.result_formula

    def test_swap_horizon_20_to_larger(self):
        result = self.mutator.mutate("Mean($close, 20)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert "40" in result.result_formula or "60" in result.result_formula

    def test_swap_horizon_no_window_returns_none(self):
        result = self.mutator.mutate("$close", MutationOperator.SWAP_HORIZON)
        assert result is None

    def test_swap_horizon_infix_returns_none(self):
        result = self.mutator.mutate("$close / $open", MutationOperator.SWAP_HORIZON)
        assert result is None

    def test_swap_horizon_result_is_valid_formula(self):
        result = self.mutator.mutate("Std($close, 10)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        parser = QlibFormulaParser()
        re_parsed = parser.parse(result.result_formula)
        assert re_parsed is not None

    def test_swap_horizon_corr(self):
        result = self.mutator.mutate("Corr($close, $volume, 10)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert "Corr" in result.result_formula


class TestChangeNormalization:

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_rank_to_zscore(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is not None
        assert result.result_formula == "Zscore($close)"

    def test_zscore_to_rank(self):
        result = self.mutator.mutate("Zscore($close)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is not None
        assert result.result_formula == "Rank($close)"

    def test_non_norm_op_returns_none(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is None

    def test_field_returns_none(self):
        result = self.mutator.mutate("$close", MutationOperator.CHANGE_NORMALIZATION)
        assert result is None


class TestRemoveOperator:

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_remove_rank(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "$close"

    def test_remove_mean_keeps_inner(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "$close"

    def test_remove_nested(self):
        result = self.mutator.mutate("Rank(Mean($close, 20))", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "Mean($close, 20)"

    def test_remove_leaf_returns_none(self):
        result = self.mutator.mutate("$close", MutationOperator.REMOVE_OPERATOR)
        assert result is None


class TestAddOperator:

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_add_rank_wrapper(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula.startswith("Rank(")
        assert "Mean($close, 5)" in result.result_formula

    def test_rank_wrapped_in_zscore(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula == "Zscore($close)"

    def test_add_operator_changes_formula(self):
        result = self.mutator.mutate("$close", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula != "$close"


class TestAlterInteraction:

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_add_volume_interaction(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert "Mul" in result.result_formula
        assert "$volume" in result.result_formula

    def test_interaction_wraps_in_mul(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert result.result_formula.startswith("Mul(")

    def test_existing_mul_replaces_second_arg(self):
        result = self.mutator.mutate("Mul($close, $open)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert "$volume" in result.result_formula
        assert result.result_formula != "Mul($close, $open)"


class TestTryAllMutations:

    def test_rank_produces_multiple_mutations(self):
        results = try_all_mutations("Rank($close)")
        assert len(results) >= 2

    def test_mean_with_window_produces_mutations(self):
        results = try_all_mutations("Mean($close, 20)")
        assert len(results) >= 3

    def test_infix_formula_produces_no_mutations(self):
        results = try_all_mutations("$close + $open")
        assert len(results) == 0

    def test_all_results_are_mutation_result_type(self):
        results = try_all_mutations("Mean($close, 5)")
        for r in results:
            assert isinstance(r, MutationResult)

    def test_results_have_valid_operators(self):
        results = try_all_mutations("Rank($close)")
        for r in results:
            assert isinstance(r.operator, MutationOperator)
            assert r.source_formula == "Rank($close)"
            assert r.result_formula != r.source_formula


class TestBuildMutationRecordDict:

    def test_dict_has_required_keys(self):
        results = try_all_mutations("Rank($close)")
        assert results, "需要至少一个变异结果"
        d = build_mutation_record_dict(results[0])
        assert "operator" in d
        assert "source_formula" in d
        assert "result_formula" in d
        assert "description" in d

    def test_operator_is_string(self):
        results = try_all_mutations("Mean($close, 5)")
        assert results
        d = build_mutation_record_dict(results[0])
        assert isinstance(d["operator"], str)


class TestResearcherSymbolicPath:

    def test_symbolic_batch_with_seeds(self):
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "Mean($close, 5)"},
            {"formula": "Rank($close)"},
        ]

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)

        assert batch is not None
        assert len(batch.notes) > 0
        assert batch.island == "momentum"
        for note in batch.notes:
            assert note.exploration_subspace == ExplorationSubspace.SYMBOLIC_MUTATION
            assert note.mutation_record is not None

    def test_symbolic_batch_no_seeds_returns_none(self):
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = []

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)
        assert batch is None

    def test_symbolic_batch_pool_exception_returns_none(self):
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.side_effect = RuntimeError("db error")

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)
        assert batch is None

    def test_symbolic_batch_infix_seeds_returns_none(self):
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "$close + $open"},
            {"formula": "$high - $low"},
        ]

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)
        assert batch is None

    def test_mutation_record_fields_in_note(self):
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "Mean($close, 20)"},
        ]

        researcher = AlphaResearcher(island="value", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=2)

        assert batch is not None
        for note in batch.notes:
            rec = note.mutation_record
            assert rec is not None
            assert "operator" in rec
            assert "source_formula" in rec
            assert "result_formula" in rec
