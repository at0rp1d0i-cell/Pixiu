"""
Unit tests for the FailureConstraint system (Phase 2 sub-task 2.1).

Coverage:
  1. Schema validation (FailureConstraint, FailureMode)
  2. ConstraintExtractor — pattern extraction, failure mode classification,
     constraint generation from a failed CriticVerdict
  3. FactorPool constraint CRUD (register / query / increment_violation)
     in in-memory fallback mode
  4. ConstraintChecker prefilter integration — hard constraint blocks note,
     warning constraint passes note, checker degrades gracefully on error
"""
from __future__ import annotations

import re
import tempfile
import uuid
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

import pytest

from src.schemas.failure_constraint import FailureConstraint, FailureMode
from src.schemas.judgment import CriticVerdict, ThresholdCheck
from src.schemas.research_note import FactorResearchNote


# ─────────────────────────────────────────────
# Helpers / factories
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

@pytest.mark.unit
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
        # constraint_id should be a valid UUID string
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

@pytest.mark.unit
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

    def test_failure_mode_classification_high_turnover(self):
        verdict = _make_failed_verdict(failure_mode="high_turnover")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.failure_mode == FailureMode.HIGH_TURNOVER

    def test_failure_mode_fallback_from_checks(self):
        """If verdict.failure_mode is unknown, fall back to first failed check."""
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
        assert pattern == "Div($close, Ref($close, N))"

    def test_extract_pattern_multiple_numbers(self):
        from src.agents.judgment import ConstraintExtractor
        extractor = ConstraintExtractor()
        pattern = extractor._extract_pattern("Rank(Mean($volume, 10))")
        assert pattern == "Rank(Mean($volume, N))"

    def test_extract_pattern_empty_formula(self):
        from src.agents.judgment import ConstraintExtractor
        extractor = ConstraintExtractor()
        assert extractor._extract_pattern("") == ""

    def test_severity_hard_for_execution_error(self):
        verdict = _make_failed_verdict(failure_mode="execution_error")
        note = _make_note()
        result = self.extractor.extract(verdict, note)
        assert result.severity == "hard"

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
        # Should parse as valid ISO datetime
        datetime.fromisoformat(result.created_at)

    def test_subspace_from_note_exploration_subspace(self):
        from src.schemas.hypothesis import ExplorationSubspace
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

@pytest.mark.unit
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
        # Should find by similarity to a matching formula
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
        # Should log a warning but not raise
        self.pool.increment_violation("nonexistent-constraint-id")

    def test_upsert_overwrites_existing(self):
        c = _make_constraint()
        self.pool.register_constraint(c)
        # Re-register with same ID but different severity
        updated = c.model_copy(update={"severity": "warning"})
        self.pool.register_constraint(updated)
        results = self.pool.query_constraints(island=c.island)
        # Should still be 1 record (upsert)
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

@pytest.mark.unit
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
        # Register a hard constraint whose pattern matches the note's formula
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
        # Warning-level constraints should not block
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
        # Constraint for "value" island should not block "momentum" note
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
        # Verify times_violated incremented
        results = self.pool.query_constraints(island="momentum")
        assert results[0].times_violated == 1

    def test_checker_degrades_on_pool_error(self):
        """ConstraintChecker must not raise even when pool.query_constraints fails."""
        from src.agents.prefilter import ConstraintChecker
        broken_pool = MagicMock()
        broken_pool.query_constraints.side_effect = RuntimeError("DB unavailable")
        checker = ConstraintChecker(pool=broken_pool)
        note = _make_note()
        passed, reason = checker.check(note)
        # Should degrade gracefully and pass
        assert passed is True

    def test_checker_uses_final_formula_when_set(self):
        """ConstraintChecker should use final_formula if available."""
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


# ─────────────────────────────────────────────
# 5. End-to-end: verdict → constraint → prefilter
# ─────────────────────────────────────────────

@pytest.mark.unit
class TestE2EConstraintFlow:
    """Mock E2E: failed verdict → ConstraintExtractor → pool → ConstraintChecker."""

    def test_full_flow_verdict_to_constraint_to_rejection(self):
        from src.agents.judgment import ConstraintExtractor
        from src.agents.prefilter import ConstraintChecker

        pool = _make_pool_inmemory()
        extractor = ConstraintExtractor()
        checker = ConstraintChecker(pool=pool)

        # Stage 5: extract constraint from failed verdict
        note = _make_note(
            formula="Div($close, Ref($close, 5))",
            island="momentum",
        )
        verdict = _make_failed_verdict(failure_mode="high_turnover")
        constraint = extractor.extract(verdict, note)
        assert constraint is not None
        # Force hard severity for this test (high_turnover should already be hard)
        assert constraint.severity == "hard"
        pool.register_constraint(constraint)

        # Stage 3: next round, new note with same formula pattern should be blocked
        new_note = _make_note(
            formula="Div($close, Ref($close, 10))",  # same pattern, different N
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
        # Pool should be empty — next note passes
        new_note = _make_note()
        passed, _ = checker.check(new_note)
        assert passed is True

    def test_researcher_constraint_section_uses_pool(self):
        """AlphaResearcher._build_constraint_section should query pool when available."""
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
        """When factor_pool is None, fall back to failed_formulas text list."""
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
