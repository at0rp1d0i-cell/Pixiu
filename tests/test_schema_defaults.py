from __future__ import annotations

import pytest

from src.schemas.exploration import CompositionConstraints, ExplorationStrategy, SubspaceRegistry
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.hypothesis import Hypothesis, StrategySpec
from src.schemas.judgment import CIOReport, PortfolioAllocation
from src.schemas.research_note import FactorResearchNote

pytestmark = pytest.mark.unit


def test_factor_research_note_list_defaults_are_not_shared():
    left = FactorResearchNote(
        note_id="n1",
        island="momentum",
        iteration=0,
        hypothesis="h",
        economic_intuition="e",
        proposed_formula="Rank($close)",
        risk_factors=["rf"],
        market_context_date="2026-03-19",
    )
    right = FactorResearchNote(
        note_id="n2",
        island="momentum",
        iteration=0,
        hypothesis="h",
        economic_intuition="e",
        proposed_formula="Rank($close)",
        risk_factors=["rf"],
        market_context_date="2026-03-19",
    )

    left.applicable_regimes.append("bull")
    left.exploration_questions.append(
        {
            "question": "q",
            "suggested_analysis": "correlation",
            "required_fields": ["$close"],
        }
    )

    assert right.applicable_regimes == []
    assert right.exploration_questions == []


def test_schema_container_defaults_are_not_shared():
    left_h = Hypothesis(
        hypothesis_id="h1",
        island="momentum",
        mechanism="m",
        economic_rationale="r",
    )
    right_h = Hypothesis(
        hypothesis_id="h2",
        island="momentum",
        mechanism="m",
        economic_rationale="r",
    )
    left_h.inspirations.append("paper")
    assert right_h.inspirations == []

    left_s = StrategySpec(
        spec_id="s1",
        hypothesis_id="h1",
        factor_expression="Rank($close)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )
    right_s = StrategySpec(
        spec_id="s2",
        hypothesis_id="h2",
        factor_expression="Rank($close)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )
    left_s.parameter_notes["window"] = "20"
    assert right_s.parameter_notes == {}

    left_registry = SubspaceRegistry()
    right_registry = SubspaceRegistry()
    left_registry.configs["x"] = {
        "subspace": "factor_algebra",
        "description": "d",
    }
    left_registry.primitives.append(
        {"name": "$close", "category": "price_volume", "qlib_syntax": "$close", "description": "close"}
    )
    assert right_registry.configs == {}
    assert right_registry.primitives == []

    left_constraints = CompositionConstraints()
    right_constraints = CompositionConstraints()
    left_constraints.forbidden_patterns.append("future_ref")
    assert right_constraints.forbidden_patterns == []

    left_strategy = ExplorationStrategy(
        strategy_id="st1",
        subspace="factor_algebra",
        name="s",
        description="d",
    )
    right_strategy = ExplorationStrategy(
        strategy_id="st2",
        subspace="factor_algebra",
        name="s",
        description="d",
    )
    left_strategy.required_context.append("market_context")
    assert right_strategy.required_context == []


def test_judgment_and_factor_pool_defaults_are_not_shared():
    left_alloc = PortfolioAllocation(
        allocation_id="a1",
        timestamp="2026-03-19T00:00:00",
        expected_portfolio_sharpe=1.0,
        expected_portfolio_ic=0.1,
        diversification_score=0.2,
        total_factors=0,
        notes="n",
    )
    right_alloc = PortfolioAllocation(
        allocation_id="a2",
        timestamp="2026-03-19T00:00:00",
        expected_portfolio_sharpe=1.0,
        expected_portfolio_ic=0.1,
        diversification_score=0.2,
        total_factors=0,
        notes="n",
    )
    left_alloc.factor_weights.append(
        {"factor_id": "f1", "island": "momentum", "weight": 1.0, "rationale": "r"}
    )
    assert right_alloc.factor_weights == []

    left_report = CIOReport(
        report_id="r1",
        period="2026-W12",
        total_factors_tested=1,
        new_factors_approved=0,
        current_portfolio=right_alloc,
        portfolio_change_summary="none",
        full_report_markdown="report",
    )
    right_report = CIOReport(
        report_id="r2",
        period="2026-W12",
        total_factors_tested=1,
        new_factors_approved=0,
        current_portfolio=right_alloc,
        portfolio_change_summary="none",
        full_report_markdown="report",
    )
    left_report.highlights.append("h")
    assert right_report.highlights == []

    left_pool = FactorPoolRecord(
        factor_id="f1",
        note_id="n1",
        formula="Rank($close)",
        hypothesis="h",
        economic_rationale="e",
        backtest_report_id="b1",
        verdict_id="v1",
        decision="archive",
        score=0.1,
    )
    right_pool = FactorPoolRecord(
        factor_id="f2",
        note_id="n2",
        formula="Rank($close)",
        hypothesis="h",
        economic_rationale="e",
        backtest_report_id="b2",
        verdict_id="v2",
        decision="archive",
        score=0.1,
    )
    left_pool.tags.append("x")
    assert right_pool.tags == []
