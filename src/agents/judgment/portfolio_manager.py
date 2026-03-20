"""Minimal deterministic portfolio allocator."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.factor_pool.pool import FactorPool
from src.schemas.judgment import FactorWeight, PortfolioAllocation
from src.schemas.state import AgentState


class PortfolioManager:
    """Minimal deterministic portfolio allocator."""

    def __init__(self, factor_pool: FactorPool | None = None):
        self.factor_pool = factor_pool

    async def rebalance(self, state: AgentState) -> PortfolioAllocation:
        passed_ids = {
            verdict.factor_id
            for verdict in state.critic_verdicts
            if verdict.decision == "promote"
        }
        selected_reports = [
            report for report in state.backtest_reports
            if report.factor_id in passed_ids
        ]

        if not selected_reports:
            return PortfolioAllocation(
                allocation_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                factor_weights=[],
                expected_portfolio_sharpe=0.0,
                expected_portfolio_ic=0.0,
                diversification_score=0.0,
                total_factors=0,
                notes="No approved factors available for allocation.",
            )

        weight = 1.0 / len(selected_reports)
        factor_weights = [
            FactorWeight(
                factor_id=report.factor_id,
                island=report.island,
                weight=weight,
                rationale="Equal-weight deterministic MVP allocation.",
            )
            for report in selected_reports
        ]
        unique_islands = {report.island for report in selected_reports}

        return PortfolioAllocation(
            allocation_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            factor_weights=factor_weights,
            expected_portfolio_sharpe=sum(report.metrics.sharpe for report in selected_reports) / len(selected_reports),
            expected_portfolio_ic=sum(report.metrics.ic_mean for report in selected_reports) / len(selected_reports),
            diversification_score=len(unique_islands) / len(selected_reports),
            total_factors=len(selected_reports),
            notes="Equal-weight deterministic MVP allocation.",
        )
